from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from tools.csv_tools import analyze_csv


def run_ops_data_agent(state: dict) -> dict:
    csv_path: str = state.get("csv_path", "data/Incoming_shipment_03_06.csv")

    try:
        analysis = analyze_csv(csv_path)
        df = pd.read_csv(csv_path)
        df.columns = [c.strip() for c in df.columns]
    except Exception as exc:
        return {"ops_data_result": {
            "agent_name": "OpsDataAgent",
            "status": "error",
            "summary": f"Failed to load CSV: {exc}",
            "trend_analysis": {"period_type": "none", "metrics": []},
            "data_quality_issues": [],
            "item_master_matches": [],
            "constraints": [],
            "recommendations": [],
            "data": {},
        }}

    # ── Data quality checks ──────────────────────────────────────
    data_quality_issues = []
    missingness = analysis.summary.get("missingness_top", {})
    for field, missing_rate in missingness.items():
        if missing_rate > 0:
            affected = int(missing_rate * analysis.summary["rows_after_drop_empty"])
            severity = "high" if missing_rate >= 0.1 else "medium" if missing_rate >= 0.05 else "low"
            data_quality_issues.append({
                "field": field,
                "issue": "Missing values detected",
                "affected_records": affected,
                "missing_rate": round(missing_rate, 4),
                "severity": severity,
            })

    # ── Dispatch volume analysis (item-level) ────────────────────
    item_counts = df.groupby("item_name").size().reset_index(name="shipment_count")
    total_items = len(df)
    item_metrics = []
    for _, row in item_counts.iterrows():
        pct = round(row["shipment_count"] / total_items, 4)
        item_metrics.append({
            "metric_name": f"shipment_volume_{row['item_name'].replace(' ', '_').lower()}",
            "current_period": int(row["shipment_count"]),
            "share_of_total": pct,
            "trend_direction": "stable",
            "severity": "high" if pct >= 0.20 else "medium" if pct >= 0.10 else "low",
        })

    # ── Dispatch volume analysis (location-level) ────────────────
    loc_counts = df.groupby("dispatch_location").size().reset_index(name="shipment_count")
    location_metrics = []
    for _, row in loc_counts.iterrows():
        pct = round(row["shipment_count"] / total_items, 4)
        location_metrics.append({
            "metric_name": f"volume_{row['dispatch_location'].replace('-', '_').lower()}",
            "current_period": int(row["shipment_count"]),
            "share_of_total": pct,
            "trend_direction": "stable",
            "severity": "high" if pct >= 0.35 else "medium" if pct >= 0.20 else "low",
        })

    trend_metrics = item_metrics + location_metrics

    # ── Anomaly summary ──────────────────────────────────────────
    anomaly_count = len(analysis.anomalies)
    if anomaly_count > 0:
        data_quality_issues.append({
            "field": "multivariate_numeric",
            "issue": f"{anomaly_count} statistical anomaly record(s) detected via Isolation Forest",
            "affected_records": anomaly_count,
            "missing_rate": round(anomaly_count / total_items, 4),
            "severity": "medium",
        })

    # ── Item Master cross-reference ──────────────────────────────
    item_master_matches = []
    known_critical = {
        "Remdesivir 100mg":           {"class": "antiviral",      "priority": "critical"},
        "Remdesivir 200mg":           {"class": "antiviral",      "priority": "critical"},
        "Pembrolizumab":              {"class": "immunotherapy",  "priority": "critical"},
        "Insulin Lispro":             {"class": "endocrine",      "priority": "high"},
        "Epinephrine Auto-Injector":  {"class": "emergency",      "priority": "critical"},
        "Morphine Sulfate":           {"class": "analgesic",      "priority": "high"},
        "Heparin Sodium":             {"class": "anticoagulant",  "priority": "high"},
        "Albuterol Inhaler":          {"class": "respiratory",    "priority": "medium"},
        "Experimental Oncology Drug": {"class": "investigational","priority": "critical"},
    }
    for item_name in df["item_name"].dropna().unique():
        meta = known_critical.get(item_name)
        if meta:
            item_master_matches.append({
                "item_name": item_name,
                "item_id": int(df.loc[df["item_name"] == item_name, "item_id"].iloc[0]),
                "product_class": meta["class"],
                "dispatch_priority": meta["priority"],
            })

    # ── Derived constraints ──────────────────────────────────────
    constraints = []
    if data_quality_issues:
        high_sev = [i for i in data_quality_issues if i["severity"] in {"high", "medium"}]
        if high_sev:
            constraints.append({
                "id": "ops_quality_001",
                "rule": "Planner must acknowledge material data quality issues before final report generation.",
                "severity": "medium",
                "source": "OpsDataAgent",
            })

    critical_items = [m for m in item_master_matches if m["dispatch_priority"] == "critical"]
    if critical_items:
        constraints.append({
            "id": "ops_priority_001",
            "rule": (
                "At least one critical-priority item is in this shipment batch. "
                "Dispatch plan must explicitly address cold-chain and on-time delivery for critical items."
            ),
            "severity": "high",
            "source": "OpsDataAgent",
        })

    high_vol_locations = [m for m in location_metrics if m["severity"] == "high"]
    if high_vol_locations:
        loc_names = [m["metric_name"] for m in high_vol_locations]
        constraints.append({
            "id": "ops_volume_001",
            "rule": (
                f"High dispatch concentration detected at: {', '.join(loc_names)}. "
                "Planner should verify sufficient truck and driver capacity for these locations."
            ),
            "severity": "medium",
            "source": "OpsDataAgent",
        })

    # ── Recommendations ──────────────────────────────────────────
    recommendations = []
    uid_issue = next((i for i in data_quality_issues if i["field"] == "unique_item_id"), None)
    if uid_issue:
        recommendations.append(
            f"Resolve {uid_issue['affected_records']} missing unique_item_id record(s) "
            "before dispatch confirmation to ensure full item traceability."
        )
    if critical_items:
        names = ", ".join(m["item_name"] for m in critical_items)
        recommendations.append(
            f"Prioritize cold-chain validation for critical items: {names}."
        )
    top_loc = max(location_metrics, key=lambda x: x["current_period"])
    recommendations.append(
        f"Highest dispatch volume to {top_loc['metric_name']} "
        f"({int(top_loc['share_of_total'] * 100)}% of batch). "
        "Confirm vehicle availability for this destination."
    )

    # ── Build summary ────────────────────────────────────────────
    quality_ok = all(i["severity"] == "low" for i in data_quality_issues) if data_quality_issues else True
    status = "success" if quality_ok else "warning"

    dq_parts = []
    for i in data_quality_issues:
        if i["severity"] in {"high", "medium"}:
            dq_parts.append(f"{i['field']} has {i['affected_records']} missing value(s)")
    anomaly_part = f"{anomaly_count} anomalous record(s) flagged." if anomaly_count else ""
    summary_parts = [f"Analyzed {total_items} shipment records across {df['dispatch_location'].nunique()} locations."]
    if dq_parts:
        summary_parts.append("Data quality issues: " + "; ".join(dq_parts) + ".")
    if anomaly_part:
        summary_parts.append(anomaly_part)
    summary_parts.append(
        f"{len(critical_items)} critical-priority item type(s) identified requiring expedited handling."
    )

    result: Dict[str, Any] = {
        "agent_name": "OpsDataAgent",
        "status": status,
        "summary": " ".join(summary_parts),
        "trend_analysis": {
            "period_type": "current_batch",
            "metrics": trend_metrics,
        },
        "data_quality_issues": data_quality_issues,
        "item_master_matches": item_master_matches,
        "constraints": constraints,
        "recommendations": recommendations,
        "data": {
            "total_records": total_items,
            "unique_items": int(df["item_name"].nunique()),
            "dispatch_locations": int(df["dispatch_location"].nunique()),
            "numeric_cols": analysis.numeric_cols,
        },
    }

    return {"ops_data_result": result}
