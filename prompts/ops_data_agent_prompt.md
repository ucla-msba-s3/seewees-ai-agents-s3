# OpsDataAgent — Enhanced LLM Synthesis Prompt (Direction #3)

**File:** `prompts/ops_data_agent_prompt.md`
**Used in:** `src/ops_data_agent.py` → `_llm_synthesis()`
**LLM budget:** 1 call per run (budget-safe — skips gracefully if exhausted)

## Purpose

OpsDataAgent performs all deterministic analysis (data quality checks, Item Master
cross-reference with substitution scoring, Playbook §8 dosage validation, volume
distribution, and — when dates are present — Period-over-Period KPI deltas) entirely
in Python. The LLM is invoked only for the final narrative synthesis step.

This separation keeps the analytics auditable and reproducible while still producing
human-quality language for the dispatch planner.

## Direction #3 enhancements reflected in this prompt

The prompt now surfaces three new signals that the deterministic layer feeds in:

1. **Item Master substitution** — when an unknown item_id has a high-confidence match
   in the Playbook (e.g., item_id 10071 → 10070, same name, same medicine_type),
   the substitution is given to the LLM with its confidence band.
2. **Playbook §8 dosage validation** — when an item_id has multiple distinct names,
   the prompt explains whether they are all valid Playbook variants (MEDIUM
   severity, dosage ambiguity) or a genuine name mismatch (HIGH severity).
3. **Period-over-Period mode** — when the CSV has dates + KPI columns, PoP deltas
   (OTDR, fill rate, risk score) are added to the FINDINGS block.

## Prompt template

```text
You are OpsDataAgent, a pharmaceutical logistics analyst for SeeWeeS Specialty Distribution.

You have just completed an analysis of an incoming shipment batch.
Synthesize the structured findings below into:
  1. A 3–4 sentence executive summary for the dispatch planner.
  2. A prioritized list of the top 3 risks (with business impact and recommended action).
  3. An overall dispatch confidence level: "high", "medium", or "low".

FINDINGS
========
Total shipment rows    : {total_rows}
Analysis mode          : {analysis_mode}                 # cross_sectional | period_over_period
Dispatch locations     : {location_summary}
Data quality issues    : {dq_count} issue(s) detected
  {dq_bullets}
Item Master matches    : {im_match_summary}              # NEW: ranked substitutes with confidence
Period-over-Period     : {pop_summary}                   # NEW: only present if PoP mode active
Location concentration : {concentration_level} (HHI = {hhi:.3f})
Dominant facility      : {dominant_location} ({dominant_pct:.1f}% of shipment)

Respond ONLY with valid JSON in this exact schema:
{
  "executive_summary": "<3-4 sentences>",
  "top_risks": [
    {"rank": 1, "finding": "...", "business_impact": "...", "recommended_action": "..."},
    {"rank": 2, "finding": "...", "business_impact": "...", "recommended_action": "..."},
    {"rank": 3, "finding": "...", "business_impact": "...", "recommended_action": "..."}
  ],
  "dispatch_confidence": "high" | "medium" | "low"
}
```

## Variable substitutions

| Variable | Source | Example |
|---|---|---|
| `{total_rows}` | `len(df)` | `87` |
| `{analysis_mode}` | `cross_sectional` or `period_over_period` | `cross_sectional` |
| `{location_summary}` | location counts and pct | `Boston-MGH: 36 (41.4%), Boston-BWH: 29 (33.3%), ...` |
| `{dq_count}` | `len(data_quality_issues)` | `3` |
| `{dq_bullets}` | formatted DQ list | `- [HIGH] Missing unique_item_id: 5 rows null ...` |
| `{im_match_summary}` | `item_master_matches` with substitution info | `item_id 10071 → 10070 ('Albuterol Inhaler', Bronchodilator, Room Temp), confidence 1.0 (HIGH)` |
| `{pop_summary}` | PoP deltas if computed | `W20 → W21: OTDR -10.0%, Risk Score +12.6%, Fill Rate -2.1%` |
| `{concentration_level}` | HHI classification | `medium` |
| `{hhi}` | HHI index | `0.315` |
| `{dominant_location}` | location with highest share | `Boston-MGH` |
| `{dominant_pct}` | dominant share % | `41.4` |

## Dispatch confidence semantics

| Level | Conditions |
|---|---|
| `"high"` | No high-severity DQ issues, no unknown items, low concentration, all PoP deltas within ±5% |
| `"medium"` | Medium-severity DQ issues OR unknown items with HIGH-confidence substitutes OR moderate concentration OR PoP delta between -10% and -5% |
| `"low"` | Any HIGH-severity DQ issue OR unknown items with LOW-confidence substitutes OR high HHI OR PoP delta worse than -10% OR risk score increase >10% |

## Worked example (real CSV — cross-sectional mode)

```text
FINDINGS
========
Total shipment rows    : 87
Analysis mode          : cross_sectional
Dispatch locations     : Boston-MGH: 36 (41.4%), Boston-BWH: 29 (33.3%), Boston-DanaFarber: 12 (13.8%), Boston-Children: 10 (11.5%)
Data quality issues    : 3 issue(s) detected
  - [HIGH]   Missing unique_item_id: 5 rows null (item_ids affected: [10021, 10022, 10035]).
  - [HIGH]   Duplicate unique_item_id across locations: 5 IDs at >1 facility.
  - [MEDIUM] item_id 10021 dosage ambiguity (all names valid per Playbook §8).
Item Master matches    : item_id 10071 → 10070 (Albuterol Inhaler, Bronchodilator, Room Temp 20-25C), confidence 1.0 (HIGH).
Period-over-Period     : N/A (no date column)
Location concentration : medium (HHI = 0.315)
Dominant facility      : Boston-MGH (41.4% of shipment)
```

Expected LLM response shape:

```json
{
  "executive_summary": "Incoming shipment of 87 units across 4 Boston facilities has 2 high-severity data quality issues (5 unique-ID nulls, 5 cross-location duplicates) and 1 unregistered item (10071) that the Item Master substitution scorer matched at high confidence to 10070 ('Albuterol Inhaler'). Boston-MGH receives 41% of the shipment, raising contingency-routing concerns. Recommend HOLD on the affected 10 units pending Inventory verification.",
  "top_risks": [
    {
      "rank": 1,
      "finding": "5 unique_item_ids appear at >1 dispatch facility",
      "business_impact": "End-to-end traceability is broken; risk of double-shipment or missed delivery",
      "recommended_action": "Pull affected units; re-label or correct manifest before scanning out"
    },
    {
      "rank": 2,
      "finding": "item_id 10071 is unregistered but matches 10070 at confidence 1.0",
      "business_impact": "Likely duplicate-ID data entry; unregistered items legally cannot be tracked or billed",
      "recommended_action": "Confirm with Inventory whether 10071 should be merged into 10070 in the master record; HOLD until resolved"
    },
    {
      "rank": 3,
      "finding": "Boston-MGH holds 41% of the shipment",
      "business_impact": "Single-facility receiving disruption affects the largest single share of this batch",
      "recommended_action": "Add contingency routing step for MGH in the dispatch plan"
    }
  ],
  "dispatch_confidence": "low"
}
```

## Worked example (augmented CSV — PoP mode)

```text
FINDINGS
========
Total shipment rows    : 312
Analysis mode          : period_over_period
Period-over-Period     : 2026-W20 → 2026-W21 (8 periods available): OTDR -10.0%, Risk Score +12.6%, Fill Rate -2.1%
Product trends         : 3 declining (SWS-001, SWS-007, ...), 3 stable, 1 improving
Data quality issues    : 2 issue(s) detected
  - [MEDIUM] OTDR dropped 10.0% period-over-period
  - [HIGH]   Average Risk Score up 12.6% — escalation may be required
```

In PoP mode the prompt prioritizes trend signals in the executive summary, and
`dispatch_confidence` should reflect the magnitude of recent deltas. A risk score
increase of 12.6% per Playbook §5.2 triggers escalation logic on its own.

## Prompt-engineering notes

- **Chain-of-thought is implicit in the output schema.** Summary → ranked risks → confidence
  mirrors an analyst's natural reasoning order without explicit CoT tags.
- **JSON-only enforcement.** The system message says "Respond ONLY with valid JSON";
  the agent code also strips backtick fences defensively before `json.loads()`.
- **Temperature.** `LLM_TEMPERATURE=0.2` keeps outputs consistent while allowing
  natural language variation.
- **Budget safety.** The call is wrapped in `try/except RuntimeError` that catches
  `_check_call_budget()` exhaustion. On exhaust, `dispatch_confidence` defaults to
  `"low"` and a message is surfaced in `executive_summary`.
