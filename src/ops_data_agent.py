from __future__ import annotations

"""
OpsDataAgent — Cross-sectional shipment analysis and Item Master cross-reference.

Called inside node_csv_analysis() in graph.py immediately after analyze_csv().
State keys consumed: csv_path, business_context
State keys produced: ops_data_result (full dict)

Design notes
------------
* The incoming CSV (Incoming_shipment_03_06.csv) has NO date column, so true
  period-over-period analysis is impossible.  We substitute a cross-sectional
  volume-distribution analysis that answers the same business question:
  "What does demand concentration and data quality look like right now, and
  what should the planner know before committing to dispatch?"
* One LLM call is made for narrative synthesis (using get_llm() from agents.py).
  It is wrapped in a budget-safe try/except so the graph never crashes if the
  call-budget is already exhausted by earlier nodes.
* Constraint rule text is phrased to match the exact substrings that
  audit_agent.py scans for when evaluating the planner's response.
"""

import re
import json
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Optional backward-compatibility import for analyze_csv (starter helper).
# The starter OpsDataAgent depended on tools.csv_tools.analyze_csv for:
#   - Multivariate anomaly detection via Isolation Forest
#   - numeric_cols list
#   - missingness_top dict
# Our enhanced agent does its own DQ checks and doesn't NEED these, but the
# graph runs analyze_csv() upstream and downstream code may read these fields
# from our output for parity. We import it defensively so this file remains
# usable in isolation (e.g., unit tests with a stubbed environment).
# ─────────────────────────────────────────────────────────────────────────────
try:
    from tools.csv_tools import analyze_csv  # type: ignore[import]
    _HAS_CSV_TOOLS = True
except ImportError:
    analyze_csv = None  # type: ignore[assignment]
    _HAS_CSV_TOOLS = False

# ─────────────────────────────────────────────────────────────────────────────
# Playbook §8 Medicine Master Reference — RICH truth table
# ─────────────────────────────────────────────────────────────────────────────
# Replaces the original flat _CATALOG_IDS set. Each entry carries the full
# Playbook §8 row so downstream logic can:
#   1. Distinguish valid dosage variants from real name-mismatch issues
#   2. Identify substitutes within the same medicine_type / temp_control class
#   3. Detect unsafe substitutions (correct family but wrong storage class)
#
# Source: SeeWeeS Operations Playbook §8, Medicine Master Reference (truth table).
# Parsed dynamically from business_context when available; falls back to this
# hard-coded copy if PDF parsing yields fewer than 3 entries (defensive).
# ─────────────────────────────────────────────────────────────────────────────
_PLAYBOOK_TRUTH_TABLE: Dict[int, Dict[str, Any]] = {
    10021: {"valid_names": ["Remdesivir 100mg", "Remdesivir 200mg"],
            "medicine_type": "Antiviral", "temp_control": "Cold (2-8C)"},
    10022: {"valid_names": ["Insulin Lispro"],
            "medicine_type": "Hormone", "temp_control": "Cold (2-8C)"},
    10035: {"valid_names": ["Pembrolizumab"],
            "medicine_type": "Monoclonal Antibody", "temp_control": "Cold (2-8C)"},
    10040: {"valid_names": ["Epinephrine Auto-Injector"],
            "medicine_type": "Emergency Drug", "temp_control": "Room Temp (20-25C)"},
    10050: {"valid_names": ["Heparin Sodium"],
            "medicine_type": "Anticoagulant", "temp_control": "Room Temp (20-25C)"},
    10060: {"valid_names": ["Morphine Sulfate"],
            "medicine_type": "Opioid Analgesic", "temp_control": "Controlled Storage"},
    10070: {"valid_names": ["Albuterol Inhaler"],
            "medicine_type": "Bronchodilator", "temp_control": "Room Temp (20-25C)"},
    99999: {"valid_names": ["Experimental Oncology Drug"],
            "medicine_type": "Clinical Trial Drug", "temp_control": "Strict Cold Chain (-20C)"},
}

# Legacy aliases — kept for backward compatibility with the original code paths.
# Anything that USED to reference _CATALOG_IDS or _CATALOG_NAMES still works.
_CATALOG_IDS: set = set(_PLAYBOOK_TRUTH_TABLE.keys())
_CATALOG_NAMES: Dict[int, str] = {
    iid: row["valid_names"][0] for iid, row in _PLAYBOOK_TRUTH_TABLE.items()
}


def _parse_playbook_truth_table(business_context: str) -> Dict[int, Dict[str, Any]]:
    """
    Best-effort parse of Playbook §8 from business_context (PDF-derived text).
    Returns the hard-coded table if fewer than 3 entries are recovered.
    """
    if not business_context:
        return _PLAYBOOK_TRUTH_TABLE

    parsed: Dict[int, Dict[str, Any]] = {}
    # Pattern matches §8 rows like: "10021 Remdesivir 100mg Antiviral Cold (2-8C)"
    pattern = re.compile(
        r"(\d{5})\s+([A-Za-z][\w\s\-,]+?)\s+([A-Za-z][\w\s]+?)\s+"
        r"(Cold\s*\(2-8C\)|Room Temp\s*\(20-25C\)|Controlled Storage|"
        r"Strict Cold Chain\s*\(-20C\))",
        re.IGNORECASE,
    )
    for match in pattern.finditer(business_context):
        try:
            item_id = int(match.group(1))
            name = match.group(2).strip()
            med_type = match.group(3).strip()
            temp = match.group(4).strip()
            if item_id not in parsed:
                parsed[item_id] = {
                    "valid_names": [name],
                    "medicine_type": med_type,
                    "temp_control": temp,
                }
            else:
                if name not in parsed[item_id]["valid_names"]:
                    parsed[item_id]["valid_names"].append(name)
        except (ValueError, IndexError):
            continue

    return parsed if len(parsed) >= 3 else _PLAYBOOK_TRUTH_TABLE

# ─────────────────────────────────────────────────────────────────────────────
# LLM prompt (canonical version lives in prompts/ops_data_agent_prompt.md)
# ─────────────────────────────────────────────────────────────────────────────
_PROMPT_TEMPLATE = """\
You are OpsDataAgent, a pharmaceutical logistics analyst for SeeWeeS Specialty Distribution.

You have just completed a cross-sectional analysis of an incoming shipment batch.
Synthesize the structured findings below into:
  1. A 3–4 sentence executive summary for the dispatch planner.
  2. A prioritized list of the top 3 risks (with business impact and recommended action).
  3. An overall dispatch confidence level: "high", "medium", or "low".

FINDINGS
========
Total shipment rows   : {total_rows}
Dispatch locations    : {location_summary}
Data quality issues   : {dq_count} issue(s) detected
  {dq_bullets}
Unknown item IDs      : {unknown_ids}
Location concentration: {concentration_level} (HHI = {hhi:.3f})
Dominant facility     : {dominant_location} ({dominant_pct:.1f}% of shipment)

Respond ONLY with valid JSON in this exact schema (no markdown fences, no extra keys):
{{
  "executive_summary": "<3-4 sentences>",
  "top_risks": [
    {{"rank": 1, "finding": "...", "business_impact": "...", "recommended_action": "..."}},
    {{"rank": 2, "finding": "...", "business_impact": "...", "recommended_action": "..."}},
    {{"rank": 3, "finding": "...", "business_impact": "...", "recommended_action": "..."}}
  ],
  "dispatch_confidence": "high" | "medium" | "low"
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# Helper: extract known IDs from PDF-derived business_context
# ─────────────────────────────────────────────────────────────────────────────
def _extract_catalog_ids(business_context: str) -> set:
    """Pull 5-digit numeric item IDs from PDF context. Kept for backward compatibility."""
    found = {int(m.group()) for m in re.finditer(r"\b1\d{4}\b", business_context)}
    return found if found else _CATALOG_IDS


# ─────────────────────────────────────────────────────────────────────────────
# Helper: load CSV
# ─────────────────────────────────────────────────────────────────────────────
def _load_csv(csv_path: str) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(csv_path)
    except Exception as exc:
        print(f"[OpsDataAgent] CSV load failed: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Data-quality checks
# ─────────────────────────────────────────────────────────────────────────────
def _check_data_quality(
    df: pd.DataFrame,
    truth_table: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Data quality checks with optional Playbook §8 grounding.

    When `truth_table` is provided, the item_id → multi-name check distinguishes:
      - Valid Playbook variants (e.g., Remdesivir 100mg AND 200mg both legal for 10021)
        → flagged as MEDIUM severity ("dosage ambiguity") because the CSV doesn't say
          which one was actually shipped per row
      - Real mismatches (CSV name not in Playbook valid_names list)
        → flagged as HIGH severity ("name does not match master record")
    """
    if truth_table is None:
        truth_table = _PLAYBOOK_TRUTH_TABLE
    issues: List[Dict[str, Any]] = []
    total = len(df)

    # ── 1. Null unique_item_id ────────────────────────────────────────────────
    if "unique_item_id" in df.columns:
        null_count = int(df["unique_item_id"].isna().sum())
        if null_count > 0:
            affected_ids = df.loc[df["unique_item_id"].isna(), "item_id"].unique().tolist()
            issues.append({
                "field": "unique_item_id",
                "issue": "Missing unique item identifiers",
                "affected_records": null_count,
                "missing_rate": round(null_count / total, 4),
                "severity": "high" if null_count / total > 0.04 else "medium",
                "detail": (
                    f"{null_count} rows have a null unique_item_id "
                    f"(item_ids affected: {affected_ids}). "
                    "These units cannot be individually tracked or verified at point of delivery."
                ),
            })

    # ── 2. Duplicate unique_item_id across different dispatch locations ────────
    if "unique_item_id" in df.columns and "dispatch_location" in df.columns:
        uid_col = df.dropna(subset=["unique_item_id"])
        loc_count_per_uid = uid_col.groupby("unique_item_id")["dispatch_location"].nunique()
        cross_loc = loc_count_per_uid[loc_count_per_uid > 1]
        if not cross_loc.empty:
            examples = cross_loc.index[:5].tolist()
            issues.append({
                "field": "unique_item_id",
                "issue": "Duplicate unique_item_id assigned across multiple dispatch locations",
                "affected_records": int(cross_loc.sum()),
                "missing_rate": None,
                "severity": "high",
                "detail": (
                    f"{len(cross_loc)} unique IDs appear at >1 facility. "
                    f"Examples: {examples}. "
                    "A single serialized unit cannot be at two locations — "
                    "indicates a barcode/labeling error or a data entry mistake."
                ),
            })

    # ── 3. item_id → name discrepancies (Playbook-grounded) ──────────────────
    if "item_id" in df.columns and "item_name" in df.columns:
        names_per_id = df.groupby("item_id")["item_name"].nunique()
        multi_name_ids = names_per_id[names_per_id > 1]
        for iid, n_names in multi_name_ids.items():
            try:
                iid_int = int(iid)
            except (ValueError, TypeError):
                continue
            name_list = sorted(df.loc[df["item_id"] == iid, "item_name"].unique().tolist())
            playbook_row = truth_table.get(iid_int)

            if playbook_row is None:
                # ID not in Playbook — can't validate. High severity (unregistered).
                issues.append({
                    "field": "item_name",
                    "issue": f"item_id {iid_int} maps to {n_names} distinct names "
                             "(item not in Playbook §8 for validation)",
                    "affected_records": int((df["item_id"] == iid).sum()),
                    "missing_rate": None,
                    "severity": "high",
                    "detail": (
                        f"Names found for item_id {iid_int}: {name_list}. "
                        "Item is not registered in Playbook §8 — cannot determine "
                        "whether these are valid variants or a real mismatch. "
                        "Escalate to Inventory before dispatch."
                    ),
                })
                continue

            valid_names = {n.lower() for n in playbook_row["valid_names"]}
            csv_names_lower = {n.lower() for n in name_list}
            invalid_names = [n for n in name_list if n.lower() not in valid_names]
            extra_valid = csv_names_lower & valid_names

            if invalid_names:
                # Real mismatch: at least one CSV name is NOT in Playbook valid_names
                issues.append({
                    "field": "item_name",
                    "issue": f"item_id {iid_int} has CSV name(s) NOT in Playbook §8",
                    "affected_records": int((df["item_id"] == iid).sum()),
                    "missing_rate": None,
                    "severity": "high",
                    "detail": (
                        f"CSV names for item_id {iid_int}: {name_list}. "
                        f"Playbook §8 valid names: {playbook_row['valid_names']}. "
                        f"Invalid names that need investigation: {invalid_names}. "
                        f"This is a real master-record mismatch, not a dosage variant."
                    ),
                })
            elif len(extra_valid) > 1:
                # All names are valid per Playbook (e.g., Remdesivir 100mg AND 200mg)
                # but the CSV doesn't disambiguate which dosage per row.
                issues.append({
                    "field": "item_name",
                    "issue": f"item_id {iid_int} dosage ambiguity (all names valid per Playbook §8)",
                    "affected_records": int((df["item_id"] == iid).sum()),
                    "missing_rate": None,
                    "severity": "medium",
                    "detail": (
                        f"Names found for item_id {iid_int}: {name_list}. "
                        f"All names are valid Playbook §8 variants ({playbook_row['medicine_type']}, "
                        f"{playbook_row['temp_control']}), but the CSV rows do not distinguish "
                        f"which specific variant was shipped. Confirm with the warehouse which "
                        f"dosage was actually packed before dispatch."
                    ),
                })

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# Substitution scoring helpers (used by enhanced cross-reference)
# ─────────────────────────────────────────────────────────────────────────────
def _name_similarity(a: str, b: str) -> float:
    """
    Lightweight name-similarity score in [0, 1].
    No external dependency. Combines:
      - Token overlap (Jaccard on lowercase word tokens)
      - Prefix match (does either name start with the same first word?)
    Good enough for "Albuterol Inhaler" vs "Albuterol Inhaler" → 1.0,
    "Albuterol Inhaler" vs "Insulin Lispro" → 0.0.
    """
    if not a or not b:
        return 0.0
    a_tokens = set(re.findall(r"[a-z0-9]+", a.lower()))
    b_tokens = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not a_tokens or not b_tokens:
        return 0.0
    jaccard = len(a_tokens & b_tokens) / len(a_tokens | b_tokens)
    # Bonus if first word matches (catches "Albuterol Inhaler" vs "Albuterol HFA")
    first_a = next(iter(re.findall(r"[a-z0-9]+", a.lower())), "")
    first_b = next(iter(re.findall(r"[a-z0-9]+", b.lower())), "")
    prefix_bonus = 0.2 if first_a and first_a == first_b else 0.0
    return min(1.0, jaccard + prefix_bonus)


def _find_substitute_candidates(
    unknown_id: int,
    csv_name: str,
    truth_table: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Score every Playbook §8 entry as a possible substitute for an unknown item.
    Returns the top 3 candidates sorted by score descending.

    Scoring:
      * Adjacent item_id (within ±2) → +0.3   (data-entry typo signal)
      * Name-token similarity (Jaccard + prefix bonus) → 0.0–1.2
      * No score floor — returns whatever's best; caller decides confidence band.
    """
    if not truth_table:
        return []

    candidates: List[Dict[str, Any]] = []
    for known_id, row in truth_table.items():
        # Compare CSV name to every Playbook valid_name for this ID
        best_name_score = max(
            (_name_similarity(csv_name, vn) for vn in row["valid_names"]),
            default=0.0,
        )
        proximity = 0.3 if 0 < abs(known_id - unknown_id) <= 2 else 0.0
        total_score = round(best_name_score + proximity, 3)
        if total_score <= 0.0:
            continue
        candidates.append({
            "candidate_id": known_id,
            "candidate_name": row["valid_names"][0],
            "medicine_type": row["medicine_type"],
            "temp_control": row["temp_control"],
            "score": total_score,
            "score_breakdown": {
                "name_similarity": round(best_name_score, 3),
                "id_proximity": proximity,
            },
        })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:3]


# ─────────────────────────────────────────────────────────────────────────────
# Item Master cross-reference — ENHANCED with real substitution logic
# ─────────────────────────────────────────────────────────────────────────────
def _item_master_cross_reference(
    df: pd.DataFrame,
    catalog_ids: set,
    truth_table: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    For each item_id present in the CSV but missing from the catalog:
      1. Look it up by name in the Playbook truth table
      2. Score nearby IDs (data-entry typo candidates)
      3. Return ranked substitute candidates with confidence band

    Confidence bands:
      HIGH (>= 0.85)  — likely the same product; strong substitute or duplicate ID
      MEDIUM (>= 0.50)— plausible, requires Inventory verification
      LOW (< 0.50)    — escalate; no defensible substitution

    Returns: (item_master_matches, missing_ids)
    """
    if "item_id" not in df.columns:
        return [], []
    if truth_table is None:
        truth_table = _PLAYBOOK_TRUTH_TABLE

    shipment_ids = set(df["item_id"].dropna().astype(int).unique())
    unknown_ids = shipment_ids - catalog_ids

    matches: List[Dict[str, Any]] = []
    for uid in sorted(unknown_ids):
        rows = df[df["item_id"] == uid]
        item_name = rows["item_name"].iloc[0] if not rows.empty else "Unknown"
        candidates = _find_substitute_candidates(uid, item_name, truth_table)

        if candidates and candidates[0]["score"] >= 0.85:
            top = candidates[0]
            confidence = round(min(1.0, top["score"]), 3)
            confidence_band = "HIGH"
            note = (
                f"item_id {uid} ('{item_name}') is not in the Item Master. "
                f"Strong substitute candidate: item_id {top['candidate_id']} "
                f"('{top['candidate_name']}', {top['medicine_type']}, {top['temp_control']}) "
                f"with score {confidence}. Likely a duplicate ID or typo — verify with Inventory."
            )
        elif candidates and candidates[0]["score"] >= 0.50:
            top = candidates[0]
            confidence = round(top["score"], 3)
            confidence_band = "MEDIUM"
            note = (
                f"item_id {uid} ('{item_name}') is not in the Item Master. "
                f"Plausible substitute: item_id {top['candidate_id']} "
                f"('{top['candidate_name']}', {top['medicine_type']}, {top['temp_control']}) "
                f"with score {confidence}. Inventory verification required before substitution."
            )
        else:
            top = None
            confidence = 0.0
            confidence_band = "LOW"
            note = (
                f"item_id {uid} ('{item_name}') is not in the Item Master and no "
                f"defensible substitute was found. Escalate to the Inventory team for "
                f"verification before dispatch."
            )

        matches.append({
            "missing_identifier": str(uid),
            "item_name_in_csv": item_name,
            "matched_item_id": top["candidate_id"] if top else None,
            "matched_product_class": top["medicine_type"] if top else "UNKNOWN",
            "matched_temp_control": top["temp_control"] if top else "UNKNOWN",
            "confidence": confidence,
            "confidence_band": confidence_band,
            "alternative_candidates": [
                {"id": c["candidate_id"], "name": c["candidate_name"], "score": c["score"]}
                for c in candidates[1:]  # everything past the top pick
            ],
            "source": "Item Master Appendix (Playbook §8)",
            "note": note,
        })

    return matches, [str(uid) for uid in sorted(unknown_ids)]


def _has_time_series_columns(df: pd.DataFrame) -> bool:
    """True if CSV has a date column plus at least one KPI column."""
    has_date = "delivery_date" in df.columns or "date" in df.columns
    kpi_cols = {"on_time", "units_ordered", "units_delivered", "temp_compliant", "risk_score"}
    has_kpi = bool(kpi_cols & set(df.columns))
    return has_date and has_kpi


def _assign_period_key(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach a 'period_key' column for PoP grouping.
    Prefers an existing 'week' column; otherwise derives ISO-week from a date column.
    """
    df = df.copy()
    if "week" in df.columns:
        df["period_key"] = df["week"].astype(str)
        return df

    date_col = "delivery_date" if "delivery_date" in df.columns else "date"
    if date_col not in df.columns:
        return df
    try:
        df["_parsed_date"] = pd.to_datetime(df[date_col], errors="coerce")
        wk = df["_parsed_date"].dt.isocalendar().week.astype(str).str.zfill(2)
        yr = df["_parsed_date"].dt.year.astype(str)
        df["period_key"] = yr + "-W" + wk
        df = df.drop(columns=["_parsed_date"])
    except Exception as exc:
        print(f"[OpsDataAgent] period assignment failed: {exc}")
    return df


def _compute_period_kpis(group: pd.DataFrame) -> Dict[str, Any]:
    """KPIs for a single period slice (used by PoP)."""
    n = len(group)
    if n == 0:
        return {"deliveries": 0, "otdr": None, "fill_rate": None,
                "temp_compliance_rate": None, "avg_risk_score": None}

    otdr = group["on_time"].sum() / n if "on_time" in group.columns else None
    if "units_ordered" in group.columns and "units_delivered" in group.columns:
        ordered = group["units_ordered"].sum()
        fill_rate = group["units_delivered"].sum() / ordered if ordered > 0 else None
    else:
        fill_rate = None
    temp = group["temp_compliant"].sum() / n if "temp_compliant" in group.columns else None
    risk = group["risk_score"].mean() if "risk_score" in group.columns else None

    def _round(v, ndigits):
        return round(float(v), ndigits) if v is not None and pd.notna(v) else None

    return {
        "deliveries": int(n),
        "otdr": _round(otdr, 4),
        "fill_rate": _round(fill_rate, 4),
        "temp_compliance_rate": _round(temp, 4),
        "avg_risk_score": _round(risk, 2),
    }


def _pop_delta(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Percentage change. None if either operand is missing or denominator is 0."""
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 2)


def _compute_pop_metrics(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Period-over-Period analysis.
    Returns None if the CSV doesn't have time-series shape.
    """
    if not _has_time_series_columns(df):
        return None

    df = _assign_period_key(df)
    if "period_key" not in df.columns:
        return None

    periods = sorted(df["period_key"].dropna().unique())
    if len(periods) < 2:
        return {
            "period_type": "period_over_period",
            "status": "insufficient_history",
            "periods_available": list(periods),
            "note": "Only one period in CSV — PoP comparison requires ≥2 periods.",
        }

    current_period = periods[-1]
    previous_period = periods[-2]
    current_kpis = _compute_period_kpis(df[df["period_key"] == current_period])
    previous_kpis = _compute_period_kpis(df[df["period_key"] == previous_period])

    deltas = {
        "otdr_pct_change": _pop_delta(current_kpis["otdr"], previous_kpis["otdr"]),
        "fill_rate_pct_change": _pop_delta(current_kpis["fill_rate"], previous_kpis["fill_rate"]),
        "temp_compliance_pct_change": _pop_delta(
            current_kpis["temp_compliance_rate"], previous_kpis["temp_compliance_rate"]),
        "risk_score_pct_change": _pop_delta(
            current_kpis["avg_risk_score"], previous_kpis["avg_risk_score"]),
    }

    # Per-product trend direction (OTDR slope across last 2 periods)
    product_trends: Dict[str, str] = {}
    if "product_id" in df.columns:
        for pid, grp in df.groupby("product_id"):
            grp_periods = sorted(grp["period_key"].unique())
            if len(grp_periods) < 2:
                product_trends[str(pid)] = "insufficient_data"
                continue
            cur = _compute_period_kpis(grp[grp["period_key"] == grp_periods[-1]])
            prv = _compute_period_kpis(grp[grp["period_key"] == grp_periods[-2]])
            d = _pop_delta(cur["otdr"], prv["otdr"])
            if d is None:
                product_trends[str(pid)] = "insufficient_data"
            elif d > 2:
                product_trends[str(pid)] = "improving"
            elif d < -2:
                product_trends[str(pid)] = "declining"
            else:
                product_trends[str(pid)] = "stable"

    # Risk flags from PoP signals (Playbook-aligned thresholds)
    pop_flags: List[Dict[str, Any]] = []
    otdr_chg = deltas["otdr_pct_change"]
    if otdr_chg is not None and otdr_chg < -5:
        pop_flags.append({
            "kpi": "OTDR",
            "flag": f"OTDR dropped {abs(otdr_chg):.1f}% period-over-period",
            "severity": "high" if otdr_chg < -10 else "medium",
        })
    risk_chg = deltas["risk_score_pct_change"]
    if risk_chg is not None and risk_chg > 10:
        pop_flags.append({
            "kpi": "Risk Score",
            "flag": f"Average Risk Score up {risk_chg:.1f}% — escalation may be required",
            "severity": "high",
        })
    fill_chg = deltas["fill_rate_pct_change"]
    if fill_chg is not None and fill_chg < -3:
        pop_flags.append({
            "kpi": "Fill Rate",
            "flag": f"Fill Rate declined {abs(fill_chg):.1f}% period-over-period",
            "severity": "high" if fill_chg < -8 else "medium",
        })

    return {
        "period_type": "period_over_period",
        "status": "computed",
        "current_period": current_period,
        "previous_period": previous_period,
        "periods_available": list(periods),
        "current": current_kpis,
        "previous": previous_kpis,
        "deltas": deltas,
        "product_trend_direction": product_trends,
        "pop_risk_flags": pop_flags,
        "note": f"PoP analysis: {previous_period} → {current_period} ({len(periods)} periods in CSV).",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cross-sectional volume distribution (PoP substitute — no date column)
# ─────────────────────────────────────────────────────────────────────────────
def _volume_distribution(df: pd.DataFrame) -> Dict[str, Any]:
    if "dispatch_location" not in df.columns:
        return {
            "period_type": "cross_sectional_volume_distribution",
            "error": "dispatch_location column not found",
            "metrics": [],
        }

    total = len(df)
    loc_counts = df["dispatch_location"].value_counts().to_dict()
    loc_pct = {k: round(v / total, 4) for k, v in loc_counts.items()}

    # Herfindahl–Hirschman Index for concentration risk
    hhi = round(sum(p ** 2 for p in loc_pct.values()), 4)
    concentration = "high" if hhi > 0.40 else "medium" if hhi > 0.25 else "low"
    dominant_location = max(loc_pct, key=loc_pct.get)
    dominant_pct = round(loc_pct[dominant_location] * 100, 1)

    # Item diversity per location
    item_diversity: Dict[str, int] = {}
    top_item_per_loc: Dict[str, Any] = {}
    if "item_id" in df.columns and "item_name" in df.columns:
        for loc, grp in df.groupby("dispatch_location"):
            item_diversity[loc] = int(grp["item_id"].nunique())
            top_id = grp["item_id"].value_counts().idxmax()
            top_name = grp.loc[grp["item_id"] == top_id, "item_name"].iloc[0]
            top_item_per_loc[loc] = {
                "item_id": int(top_id),
                "item_name": top_name,
                "units": int(grp["item_id"].value_counts().max()),
            }

    # Null unique_item_id rate (key data quality metric)
    null_uid_rate = None
    if "unique_item_id" in df.columns:
        null_uid_rate = round(df["unique_item_id"].isna().mean(), 4)

    return {
        "period_type": "cross_sectional_volume_distribution",
        "note": (
            "CSV has no date column; analysis is cross-sectional over the full "
            "incoming shipment batch (single snapshot)."
        ),
        "total_shipment_rows": total,
        "location_distribution": {
            "counts": {k: int(v) for k, v in loc_counts.items()},
            "percentages": loc_pct,
        },
        "concentration_risk": {
            "hhi_index": hhi,
            "level": concentration,
            "dominant_location": dominant_location,
            "dominant_share_pct": dominant_pct,
            "interpretation": (
                f"{dominant_location} holds {dominant_pct}% of this shipment. "
                "A single-facility disruption would affect the majority of deliveries."
                if concentration == "high"
                else f"{dominant_location} is the largest recipient at {dominant_pct}%."
            ),
        },
        "item_diversity_per_location": item_diversity,
        "top_item_per_location": top_item_per_loc,
        "metrics": [
            {
                "metric_name": "location_concentration_hhi",
                "value": hhi,
                "trend_direction": "N/A — single snapshot",
                "severity": concentration,
            },
            {
                "metric_name": "null_unique_item_id_rate",
                "value": null_uid_rate,
                "trend_direction": "N/A — single snapshot",
                "severity": "high" if null_uid_rate and null_uid_rate > 0.04 else "low",
            },
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Constraint builder — rule text matches audit_agent.py trigger substrings
# ─────────────────────────────────────────────────────────────────────────────
def _build_constraints(
    data_quality_issues: List[Dict],
    item_master_matches: List[Dict],
) -> List[Dict[str, Any]]:
    constraints: List[Dict[str, Any]] = []

    has_high_dq = any(i.get("severity") == "high" for i in data_quality_issues)
    has_unknown_items = len(item_master_matches) > 0

    if has_high_dq or has_unknown_items:
        # Trigger phrase audit_agent.py checks: "must acknowledge material data quality issues"
        constraints.append({
            "id": "ops_quality_001",
            "rule": (
                "Planner must acknowledge material data quality issues "
                "and explain how they affect dispatch confidence before finalizing the plan."
            ),
            "severity": "high",
            "source": "OpsDataAgent",
        })

    # Trigger phrase audit_agent.py checks: "planner must explain the dispatch impact"
    constraints.append({
        "id": "ops_trend_001",
        "rule": (
            "Planner must explain the dispatch impact of volume concentration "
            "and any period-over-period or cross-sectional trend anomalies identified "
            "by OpsDataAgent."
        ),
        "severity": "high",
        "source": "OpsDataAgent",
    })

    return constraints


# ─────────────────────────────────────────────────────────────────────────────
# Recommendations builder
# ─────────────────────────────────────────────────────────────────────────────
def _build_recommendations(
    data_quality_issues: List[Dict],
    item_master_matches: List[Dict],
    concentration_level: str,
    dominant_location: str,
    dominant_pct: float,
) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []

    for issue in data_quality_issues:
        if issue["field"] == "unique_item_id" and issue["issue"] == "Missing unique item identifiers":
            recs.append({
                "type": "data_remediation",
                "priority": "high",
                "recommendation": (
                    f"Resolve {issue['affected_records']} null unique_item_id records "
                    f"({issue.get('missing_rate', 0)*100:.1f}% of shipment) before dispatch. "
                    "Contact the warehouse team to assign barcodes or pull from backup manifest."
                ),
            })
        if issue["field"] == "unique_item_id" and "Duplicate" in issue["issue"]:
            recs.append({
                "type": "data_remediation",
                "priority": "high",
                "recommendation": (
                    "Investigate the cross-location unique_item_id duplicates. "
                    "Confirm correct destination for each unit and re-label if necessary "
                    "to prevent misrouting."
                ),
            })
        if issue["field"] == "item_name":
            recs.append({
                "type": "verification",
                "priority": "high",
                "recommendation": (
                    f"Resolve item_name discrepancy for item_id {issue['affected_records']} records. "
                    "A dosage mismatch (e.g., 100mg vs 200mg) is a patient-safety risk — "
                    "hold affected units pending confirmation from the clinical pharmacist."
                ),
            })

    if item_master_matches:
        ids = [m["missing_identifier"] for m in item_master_matches]
        recs.append({
            "type": "item_master_escalation",
            "priority": "high",
            "recommendation": (
                f"Escalate unknown item_ids {ids} to the Inventory team for Item Master registration. "
                "Do not dispatch unregistered items until they are validated."
            ),
        })

    if concentration_level == "high":
        recs.append({
            "type": "planning_adjustment",
            "priority": "medium",
            "recommendation": (
                f"{dominant_location} holds {dominant_pct:.1f}% of this shipment. "
                "Add a contingency routing step in the dispatch plan for this facility "
                "in case of access or capacity issues."
            ),
        })

    return recs


# ─────────────────────────────────────────────────────────────────────────────
# LLM synthesis (single call, budget-safe)
# ─────────────────────────────────────────────────────────────────────────────
def _llm_synthesis(
    total_rows: int,
    loc_counts: Dict[str, int],
    data_quality_issues: List[Dict],
    unknown_ids: List[str],
    hhi: float,
    concentration_level: str,
    dominant_location: str,
    dominant_pct: float,
) -> Dict[str, Any]:
    """Call the LLM for narrative synthesis. Fails gracefully on budget exhaustion."""
    try:
        # Import here to avoid circular imports at module load time
        from agents import get_llm, _check_call_budget  # type: ignore[import]
        _check_call_budget()
    except RuntimeError as budget_err:
        return {
            "executive_summary": f"LLM synthesis skipped: {budget_err}",
            "top_risks": [],
            "dispatch_confidence": "low",
            "_skipped": True,
        }
    except ImportError:
        return {
            "executive_summary": "LLM synthesis unavailable (agents module not found).",
            "top_risks": [],
            "dispatch_confidence": "medium",
            "_skipped": True,
        }

    location_summary = ", ".join(
        f"{loc}: {cnt} units ({cnt/total_rows*100:.1f}%)"
        for loc, cnt in sorted(loc_counts.items(), key=lambda x: -x[1])
    )
    dq_bullets = "\n  ".join(
        f"- [{i.get('severity','').upper()}] {i.get('issue','')}: {i.get('detail','')}"
        for i in data_quality_issues
    ) or "None"

    prompt = _PROMPT_TEMPLATE.format(
        total_rows=total_rows,
        location_summary=location_summary,
        dq_count=len(data_quality_issues),
        dq_bullets=dq_bullets,
        unknown_ids=unknown_ids if unknown_ids else "None",
        concentration_level=concentration_level,
        hhi=hhi,
        dominant_location=dominant_location,
        dominant_pct=dominant_pct,
    )

    try:
        llm = get_llm()
        raw = llm.invoke(prompt).content
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw.strip())
        return json.loads(raw)
    except json.JSONDecodeError:
        # Return the raw text wrapped in the expected structure
        return {
            "executive_summary": raw if "raw" in dir() else "LLM returned non-JSON response.",
            "top_risks": [],
            "dispatch_confidence": "medium",
        }
    except Exception as exc:
        return {
            "executive_summary": f"LLM synthesis failed: {type(exc).__name__}: {exc}",
            "top_risks": [],
            "dispatch_confidence": "medium",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────
def run_ops_data_agent(state: dict) -> dict:
    """
    Analyze the incoming shipment CSV for cross-sectional volume distribution,
    data quality issues, and Item Master mismatches.

    Returns:
        {"ops_data_result": { ... }}  — shape matches examples/ops_data_agent_sample_output.json
    """
    csv_path: str = state.get("csv_path", "")
    business_context: str = state.get("business_context", "")

    # ── Load CSV ──────────────────────────────────────────────────────────────
    df = _load_csv(csv_path)
    if df is None or df.empty:
        return {
            "ops_data_result": {
                "agent_name": "OpsDataAgent",
                "status": "failed",
                "summary": f"Could not load CSV at path: {csv_path!r}",
                "trend_analysis": {"period_type": "error", "metrics": []},
                "data_quality_issues": [],
                "item_master_matches": [],
                "constraints": [],
                "recommendations": [],
                "data": {},
            }
        }

    # ── Optional: run starter's analyze_csv for backward-compat fields ────────
    # Provides numeric_cols + anomaly count + missingness_top, which downstream
    # code (graph.py, ui_app.py, report templates) may read from our output.
    starter_analysis: Dict[str, Any] = {}
    if _HAS_CSV_TOOLS and analyze_csv is not None:
        try:
            ana = analyze_csv(csv_path)
            anomalies_df = getattr(ana, "anomalies", None)
            anomalies_count = len(anomalies_df) if anomalies_df is not None else 0
            starter_analysis = {
                "numeric_cols": getattr(ana, "numeric_cols", []),
                "anomalies_count": anomalies_count,
                "missingness_top": getattr(ana, "summary", {}).get("missingness_top", {}),
                "rows_after_drop_empty": getattr(ana, "summary", {}).get(
                    "rows_after_drop_empty", len(df)
                ),
            }
        except Exception as exc:
            # Non-fatal: log and continue. Our agent doesn't depend on this.
            print(f"[OpsDataAgent] starter analyze_csv failed (non-fatal): {exc}")
            starter_analysis = {"error": str(exc)}

    # ── Derive catalog from PDF context (or use hard-coded fallback) ──────────
    truth_table = _parse_playbook_truth_table(business_context)
    catalog_ids = set(truth_table.keys())

    # ── Run deterministic analyses ────────────────────────────────────────────
    data_quality_issues = _check_data_quality(df, truth_table)
    item_master_matches, missing_ids = _item_master_cross_reference(df, catalog_ids, truth_table)
    trend_analysis = _volume_distribution(df)

    # ── NEW: Period-over-Period analysis (fires only if CSV has dates+KPIs) ──
    pop_result = _compute_pop_metrics(df)
    if pop_result is not None:
        trend_analysis["pop_metrics"] = pop_result
        # Promote PoP risk flags into the top-level data_quality_issues feed
        # so the audit loop / planner sees them without needing to dig.
        for flag in pop_result.get("pop_risk_flags", []):
            data_quality_issues.append({
                "field": flag["kpi"].lower(),
                "issue": flag["flag"],
                "affected_records": pop_result["current"].get("deliveries", 0),
                "missing_rate": None,
                "severity": flag["severity"],
                "detail": (
                    f"Period-over-period signal from {pop_result['previous_period']} → "
                    f"{pop_result['current_period']}. {flag['flag']}."
                ),
            })

    # Pull out concentration figures for downstream use
    conc = trend_analysis.get("concentration_risk", {})
    hhi = conc.get("hhi_index", 0.0)
    concentration_level = conc.get("level", "unknown")
    dominant_location = conc.get("dominant_location", "unknown")
    dominant_pct = conc.get("dominant_share_pct", 0.0)
    loc_counts = trend_analysis.get("location_distribution", {}).get("counts", {})
    total_rows = len(df)

    # ── Build constraints and recommendations ─────────────────────────────────
    constraints = _build_constraints(data_quality_issues, item_master_matches)
    recommendations = _build_recommendations(
        data_quality_issues,
        item_master_matches,
        concentration_level,
        dominant_location,
        dominant_pct,
    )

    # ── LLM narrative synthesis (1 call, budget-safe) ─────────────────────────
    llm_insights = _llm_synthesis(
        total_rows=total_rows,
        loc_counts=loc_counts,
        data_quality_issues=data_quality_issues,
        unknown_ids=missing_ids,
        hhi=hhi,
        concentration_level=concentration_level,
        dominant_location=dominant_location,
        dominant_pct=dominant_pct,
    )

    # ── Derive overall status ─────────────────────────────────────────────────
    has_high_issues = any(i.get("severity") == "high" for i in data_quality_issues)
    has_unknown = len(missing_ids) > 0
    status = "warning" if (has_high_issues or has_unknown) else "success"

    # ── Assemble summary line ─────────────────────────────────────────────────
    pop_summary = ""
    if pop_result and pop_result.get("status") == "computed":
        d = pop_result["deltas"]
        otdr_d = d.get("otdr_pct_change")
        risk_d = d.get("risk_score_pct_change")
        bits = []
        if otdr_d is not None:
            bits.append(f"OTDR {otdr_d:+.1f}%")
        if risk_d is not None:
            bits.append(f"Risk Score {risk_d:+.1f}%")
        if bits:
            pop_summary = (
                f" PoP ({pop_result['previous_period']}→{pop_result['current_period']}): "
                + ", ".join(bits) + "."
            )

    analysis_mode = (
        "period_over_period" if pop_result and pop_result.get("status") == "computed"
        else "cross_sectional"
    )
    summary = (
        f"Analyzed {total_rows} shipment rows across {len(loc_counts)} locations. "
        f"Found {len(data_quality_issues)} data quality issue(s) and "
        f"{len(missing_ids)} unknown item ID(s). "
        f"Location concentration: {concentration_level} (HHI={hhi:.3f}). "
        f"Analysis mode: {analysis_mode}.{pop_summary}"
    )

    result: dict = {
        "agent_name": "OpsDataAgent",
        "status": status,
        "summary": summary,
        "trend_analysis": trend_analysis,
        "data_quality_issues": data_quality_issues,
        "item_master_matches": item_master_matches,
        "constraints": constraints,
        "recommendations": recommendations,
        "data": {
            "missing_ids": missing_ids,
            "llm_insights": llm_insights,
            "analysis_metadata": {
                "total_rows": total_rows,
                "columns": df.columns.tolist(),
                "has_date_column": _has_time_series_columns(df),
                "analysis_mode": analysis_mode,
                "catalog_ids_used": sorted(catalog_ids),
                "unique_locations": list(loc_counts.keys()),
                "playbook_table_size": len(truth_table),
            },
            # ── Backward-compatibility surface for starter analyze_csv ──
            # Downstream code (graph.py, ui_app.py, report templates) may
            # read these fields. We keep them populated for parity with the
            # original OpsDataAgent contract even though our deterministic
            # checks supersede them.
            "numeric_cols": starter_analysis.get("numeric_cols", []),
            "anomalies_count": starter_analysis.get("anomalies_count", 0),
            "missingness_top": starter_analysis.get("missingness_top", {}),
            "rows_after_drop_empty": starter_analysis.get("rows_after_drop_empty", total_rows),
        },
    }

    return {"ops_data_result": result}
