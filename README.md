# SeeWeeS Multi-Agent Dispatch QA System

> Multi-agent AI pipeline that turns incomplete logistics data into an **audited, executive-ready dispatch recommendation** for time-critical specialty medicine deliveries.

---

## Business Problem

SeeWeeS handles time-critical specialty medicine distribution. The original flow is linear — retrieve documents, analyze shipment data, check weather, produce a report. A linear flow is risky in medical logistics because a weak dispatch plan can reach an executive report without being challenged against safety protocols, data quality gaps, or operational constraints.

This system redesigns the workflow as a **rule-grounded multi-agent pipeline with a self-correction audit loop**. The PlannerAgent must pass an AuditAgent quality gate before the ReportAgent can generate the final HTML report. If the audit finds a violated safety rule or ignored constraint, the graph loops back to the PlannerAgent with corrective feedback.

---

## Agent Pipeline

```
ContextAgent → OpsDataAgent → WeatherAgent → ScenarioAgent → PlannerAgent → AuditAgent → ReportAgent → Email
                                                                    ↑               │
                                                                    │   fail (≤2×)  │ pass
                                                                    └───────────────┘
```

| Agent | Purpose |
|-------|---------|
| **ContextAgent** | Retrieves business rules, KPI thresholds, SLAs, and escalation policies from the PDF playbook via RAG (ChromaDB). Converts key rules into structured `playbook_constraints` for runtime enforcement. |
| **OpsDataAgent** | Analyzes incoming shipment CSV for data quality issues (null IDs, duplicates, name mismatches), Item Master cross-reference, volume distribution, and period-over-period trends. Emits constraints for AuditAgent. |
| **WeatherAgent** | Fetches live forecasts from Open-Meteo for each I-95 corridor waypoint (W1–W5) and rolls up to a route-level risk score (0–3). |
| **ScenarioAgent** | Simulates what-if operational disruptions (demand spike, warehouse closure, driver shortage, route blockage, hospital surge). Produces KPI impacts and contingency constraints. Deterministic — no LLM quota. |
| **PlannerAgent** | Synthesizes all upstream evidence into a dispatch recommendation grounded in playbook constraints, operational data, weather risk, and scenario contingencies. |
| **AuditAgent** | Validates the dispatch plan against 7 deterministic rules covering weather buffer policy, critical-risk escalation, data quality acknowledgement, trend impact, and scenario contingencies. Routes back to PlannerAgent on failure (up to 2 retries). Deterministic — no LLM quota. |
| **ReportAgent** | Produces a structured executive HTML report: decision, top risks, recommended actions, KPI snapshot, weather detail table, and audit status. |

---

## Data Augmentation Strategy

The source data does not contain every variable needed for realistic dispatch planning. Missing links are derived or simulated:

| Missing Link | Why It Matters | Source / Derivation | Used By |
|---|---|---|---|
| Corridor weather risk score (0–3) | Medical shipments are vulnerable to severe weather. | Waypoint coordinates + Open-Meteo forecast → max across W1–W5. | Planner, Audit, Report |
| Manager escalation requirement | High-risk shipments need oversight before dispatch. | Rule derived from PDF: risk score 3 → escalation required. | Audit |
| Data quality confidence | Missing shipment fields reduce planning reliability. | CSV missingness + OpsDataAgent DQ checks. | Ops, Planner, Audit |
| Period-over-period operational trend | A single snapshot can miss worsening conditions. | Cross-sectional volume distribution (single-snapshot CSV). | Ops, Planner |
| Item Master identifier mapping | Missing item/SKU fields hide product class and cold-chain needs. | Playbook §8 truth table cross-referenced against CSV item_ids. | Ops, Planner |
| What-if disruption parameters | Leadership needs contingency plans before disruptions occur. | User-provided scenario JSON or 3 built-in defaults. | Scenario, Planner, Audit, Report |

---

## KPI Definitions

| KPI | Calculation | Threshold |
|-----|-------------|-----------|
| Route Risk Score | Max weather risk across I-95 waypoints. | 0–1 normal · 2 elevated · 3 critical (→ escalation) |
| Dispatch Buffer | Travel time buffer by risk score. | 0→0% · 1→10% · 2→25% · 3→40% + escalation |
| Data Quality Issue Count | High/medium severity DQ issues in shipment CSV. | Any HIGH issue must be acknowledged in plan. |
| Audit Pass Rate | Plan passes all 7 AuditAgent rules. | Report generated only after pass or retry-limit warning. |
| Scenario KPI Impact | Baseline vs. simulated KPI under disruption. | HIGH/CRITICAL impacts require contingency recommendations. |

---

## Audit Rules (AuditAgent)

The AuditAgent enforces 7 deterministic rules — no LLM involved:

| Rule ID | Source | What It Checks |
|---------|--------|----------------|
| `playbook_weather_buffer_001` | Dispatch Playbook | Plan includes the correct buffer % for the current risk score. |
| `playbook_weather_escalation_001` | Dispatch Playbook | Plan includes escalation language when risk score = 3. |
| `safety_weather_001` | PDF safety protocol | Plan does not dispatch at risk score 3 without manager review. |
| `pdf_context_escalation_001` | ContextAgent | Plan reflects escalation language found in PDF context. |
| `ops_quality_001` | OpsDataAgent | Plan acknowledges high-severity data quality issues. |
| `ops_trend_001` | OpsDataAgent | Plan explains dispatch impact of high trend/concentration risk. |
| `scenario_contingency_001` | ScenarioAgent | Plan addresses capacity, rerouting, or driver shortage contingencies. |

---

## Project Structure

```
MSBA_AI_Agents_Demo/
├── data/
│   ├── SeeWeeS Specialty Dispatch Playbook.pdf   # source of business rules
│   └── Incoming_shipment_03_06.csv               # incoming shipment batch
├── examples/
│   ├── audit_fail_case.json                      # preloaded audit demo input
│   └── scenario_input.json                       # preloaded scenario demo input
├── src/
│   ├── ui_app.py          # Streamlit UI (5 tabs)
│   ├── graph.py           # LangGraph state machine
│   ├── agents.py          # LLM provider setup + budget guard
│   ├── ops_data_agent.py  # OpsDataAgent logic
│   ├── audit_agent.py     # AuditAgent deterministic rules
│   ├── scenario_agent.py  # ScenarioAgent simulation
│   ├── playbook_rules.py  # Playbook constraint extractor
│   ├── prompts.py         # LLM prompt templates
│   ├── main.py            # CLI entry point
│   └── tools/
│       ├── csv_tools.py      # CSV analysis + anomaly detection
│       ├── pdf_tools.py      # PDF RAG (ChromaDB)
│       ├── weather_tools.py  # Open-Meteo API + risk scoring
│       └── email_tools.py    # SMTP report delivery
├── .streamlit/
│   └── config.toml        # forces light mode
├── chroma_db/             # local vector store (not committed)
├── outputs/               # generated report.html
├── .env                   # secrets (not committed)
└── .env.example
```

---

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in GOOGLE_API_KEY from Google AI Studio (free tier)
# Or set LLM_PROVIDER=openai and fill OPENAI_API_KEY
```

### `.env` Reference

```env
LLM_PROVIDER=gemini                  # or openai
LLM_MODEL=gemini-2.0-flash           # gemini-2.0-flash has 1500 RPD free tier
LLM_TEMPERATURE=0.2
LLM_MAX_CALLS_PER_RUN=6             # budget guard — stops runaway loops
GEMINI_FREE_TIER_ONLY=true          # refuses Vertex AI / paid-mode settings

EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-001

GOOGLE_API_KEY=your_google_ai_studio_key

# OpenAI fallback (only used when LLM_PROVIDER=openai)
OPENAI_API_KEY=

# Optional email delivery
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=
SMTP_PASSWORD=
REPORT_EMAIL_TO=
```

> **Quota note:** Each Full Pipeline run makes ~6–7 LLM API calls (one per agent). With `gemini-2.5-flash` (20 RPD free tier), 3 full runs exhaust the daily quota. Use `gemini-2.0-flash` (1500 RPD) for development. Quota resets daily at 08:00 Taiwan time (UTC midnight).

---

## UI Command Center

```bash
streamlit run src/ui_app.py
```

The app runs in **light mode** (enforced via `.streamlit/config.toml`).

### Tab Overview

| Tab | Quota Used | Purpose |
|-----|-----------|---------|
| **Overview** | None | Agent pipeline diagram and system configuration summary. |
| **Ops Data** | None | Runs OpsDataAgent deterministically (no LLM). Shows data quality issues, Item Master cross-reference, and recommended remediation actions. |
| **Scenarios** | None | Runs ScenarioAgent with configurable disruption parameters. Shows KPI impacts and contingency recommendations per scenario. |
| **Audit** | None | Tests the AuditAgent against a preloaded fail case. Shows violation cards with Policy Violated and Suggested Solution. |
| **Full Pipeline** | ~6–7 LLM calls | Runs the complete graph end-to-end. Shows weather waypoint risk table, scenario cards, audit violation cards, and executive report. |

### File Upload

The Ops Data and Full Pipeline tabs include `st.file_uploader` widgets. Default data (`Incoming_shipment_03_06.csv` and `SeeWeeS Specialty Dispatch Playbook.pdf`) is pre-loaded — upload only if testing with different data.

---

## Tests

```bash
PYTHONPATH=src python -m pytest -q
```

Current result: **24 passed, 1 skipped, 1 warning**

| Category | What Is Tested |
|----------|---------------|
| Unit | AuditAgent catches wrong buffer %, missing escalation, missing DQ acknowledgement. |
| Integration | OpsDataAgent and ScenarioAgent constraints trigger correct AuditAgent violations. |
| Graph | LangGraph compiles, all nodes reachable, conditional routing correct. |
| Failure-mode | Risk score 3 without escalation routes back to PlannerAgent. |
| Contract | OpsDataAgent and ScenarioAgent output schemas match downstream expectations. |
| Demo inputs | `audit_fail_case.json` and `scenario_input.json` load and produce expected results. |

The skipped test activates only if `data/augmented_ops_data.csv` is present (optional PoP mode). The warning is a LangGraph dependency warning, not a project failure.

---

## Demo Flow

### Demo A — Product Walkthrough (no API needed)

Explain the system before running anything.

1. Start with the business scenario — SeeWeeS delivers time-sensitive specialty medicine. A bad dispatch decision can cause SLA failure, spoilage, or unsafe routing.
2. Show the inputs: playbook PDF, shipment CSV, and I-95 corridor weather data.
3. Walk through the agent pipeline diagram in the Overview tab.
4. Explain the audit loop: PlannerAgent → AuditAgent → (fail → back to Planner) / (pass → ReportAgent).

Talk track:
> *"The core value is not just generating a report. The system identifies missing operational links, augments the data, turns them into KPIs and constraints, and blocks unsafe recommendations before leadership sees them."*

### Demo B — Stable Audit Failure Case (no API, no quota)

Shows the self-correction logic deterministically.

**UI method:** Open the **Audit** tab → click **Run Audit Check**. Expected: `FAIL`, 3 violations with Policy Violated + Suggested Solution cards, routing back to PlannerAgent.

**CLI method:**
```bash
PYTHONPATH=src python - <<'PY'
import json
from audit_agent import run_audit_agent
from graph import route_after_audit

with open("examples/audit_fail_case.json", encoding="utf-8") as f:
    case = json.load(f)

result = run_audit_agent(case["state"])["audit_result"]
next_step = route_after_audit({"audit_result": result, "audit_retry_count": 1})

print("Audit status:", result["audit_status"])
print("Next graph step:", next_step)
for v in result["violations"]:
    print(f"  - {v['rule_id']} | {v['severity']} | {v['required_fix']}")
print("\nFeedback to Planner:")
print(result["feedback_to_planner"])
PY
```

Expected output:
```
Audit status: fail
Next graph step: planner
  - safety_weather_001 | critical | ...
  - pdf_context_escalation_001 | critical | ...
  - ops_quality_001 | medium | ...
```

Talk track:
> *"This is the system handling failure. The route risk score is critical, but the draft plan forgot manager escalation. Instead of sending that plan to executives, AuditAgent returns structured feedback and LangGraph routes back to PlannerAgent."*

### Demo C — What-If Scenario Simulation (no API, no quota)

Shows business complexity beyond a single current-state report.

**UI method:** Open the **Scenarios** tab → configure disruptions → click **Run Scenario Analysis**.

**CLI method:**
```bash
PYTHONPATH=src python - <<'PY'
import json
from scenario_agent import run_scenario_agent

with open("examples/scenario_input.json", encoding="utf-8") as f:
    state = json.load(f)

result = run_scenario_agent(state)["scenario_result"]
print(result["summary"])
for scenario in result["scenarios"]:
    print(f"\nScenario: {scenario['scenario_name']}")
    for impact in scenario["kpi_impacts"]:
        print(f"  - {impact['kpi']}: {impact['baseline']} → {impact['simulated']} ({impact['severity']})")
PY
```

Talk track:
> *"This is how the product handles hypothetical disruption. The scenario agent converts disruptions into KPI impacts and constraints, so PlannerAgent must produce contingency recommendations rather than a generic dispatch plan."*

### Demo D — UI Command Center (no API, no quota)

Open each tab in order: Overview → Ops Data → Scenarios → Audit.  
Reserve Full Pipeline for Demo E only.

Talk track:
> *"This UI lets an operations user test each agent independently before trusting the full pipeline. It also gives function owners a shared surface to verify their outputs during integration."*

### Demo E — Full Pipeline Run (requires API key)

Before running, confirm `.env` has a valid key and quota is available.

```bash
# Option 1: UI
streamlit run src/ui_app.py   # → Full Pipeline tab → Launch Full Pipeline

# Option 2: CLI
python src/main.py
```

Expected sequence: PDF rules retrieved → CSV analyzed → Weather scored → Scenarios simulated → Plan generated → Audit checked → Report produced.

**Backup plan:** If quota, weather API, or latency becomes a problem, use Demos B–D and a saved `outputs/report.html`.

Talk track after the run:
> *"The final output is not a raw model answer. It is an executive decision packet: decision, top risks, recommended actions, KPI snapshot, and audit status."*

### Closing Comparison

| Baseline | Enhanced |
|----------|----------|
| Retrieve → Analyze → Plan → Report | Retrieve → Analyze → Plan → **Audit → Correct →** Report |

> *"We redesigned the pipeline so SeeWeeS can move from simple reporting to audited operational decision support for high-stakes medical logistics."*

---

## CLI Run

```bash
python src/main.py
```

Runs the full graph non-interactively. Report is saved to `outputs/report.html`. If `REPORT_EMAIL_TO` is set in `.env`, the report is emailed via Gmail SMTP.
