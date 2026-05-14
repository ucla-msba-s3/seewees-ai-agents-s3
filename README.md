# MSBA AI Agents Demo (LangGraph + LangChain)

Multi-agent system for operations/dispatch planning:
- Reads business context & KPI definitions from a PDF (RAG)
- Analyzes ops data from CSV (KPIs + anomaly detection)
- Pulls weather forecast and derives dispatch risk
- Extracts structured playbook constraints for AuditAgent enforcement
- Simulates what-if disruptions such as demand spike, warehouse closure, and driver shortage
- Enforces a self-correction Audit Loop before report generation
- Produces a leadership-ready report
- Emails the report via Gmail SMTP (app password)

## Project Structure
- `data/` input PDF + CSV
- `docs/` project background, methodology, demo flow, and testing summary
- `examples/` demo inputs for audit and scenario simulation
- `src/` application code
- `chroma_db/` local vector store (not committed)
- `.env` secrets (not committed)

## Architecture

```text
pdf_context -> csv_analysis / OpsDataAgent -> weather -> scenario -> planner -> audit -> report -> email
```

The audit node creates the non-linear self-correction loop:

```text
PlannerAgent -> AuditAgent
Audit pass -> ReportAgent
Audit fail -> PlannerAgent with feedback
```

See `docs/project_background.md` for the business problem, missing-link analysis, KPI definitions, data augmentation strategy, and technical methodology.

## Playbook-Grounded Audit

The PDF context step produces structured `playbook_constraints`, including:

- Weather buffer policy: risk score `0 -> 0%`, `1 -> 10%`, `2 -> 25%`, `3 -> 40%`.
- Critical risk escalation: risk score `3` requires manager escalation or review.

AuditAgent enforces these constraints at runtime. For example, if weather risk is `2` but PlannerAgent only recommends a `10%` buffer, AuditAgent fails the plan and loops back to PlannerAgent with corrective feedback.

## What-If Scenarios

ScenarioAgent supports disruption simulation through `state["scenarios"]`. If no scenarios are provided, it runs three defaults:

- 20% demand spike
- Primary warehouse closure
- Driver shortage

Example input lives in `examples/scenario_input.json`. Scenario outputs include KPI impacts, constraints, and contingency recommendations that flow into PlannerAgent, AuditAgent, and ReportAgent.

## Setup
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
windows: python -m pip install -r requirements.txt

cp .env.example .env
# For free-tier Gemini testing, fill GOOGLE_API_KEY from Google AI Studio.
# For OpenAI fallback, set LLM_PROVIDER=openai and fill OPENAI_API_KEY.
windows:  python src/main.py
```

## Tests

```bash
PYTHONPATH=src python -m pytest -q
```

The current tests cover graph construction, audit pass/fail routing, playbook rule extraction, scenario simulation, OpsDataAgent contract behavior, and demo input availability.

See `docs/project_background.md` for the pre-launch testing summary, including unit, integration, end-to-end, failure-mode, and mock stress/load testing.

## UI Command Center

Run the Streamlit UI:

```bash
streamlit run src/ui_app.py
```

The UI includes:

- Overview: product story and agent pipeline.
- OpsData: local CSV summary and OpsDataAgent contract output.
- Scenarios: what-if disruption simulation without LLM quota.
- Audit: deterministic audit failure/success testing without LLM quota.
- Full Pipeline: complete graph run with PDF RAG, weather, PlannerAgent, AuditAgent, and ReportAgent.

The Full Pipeline tab can call Gemini/OpenAI and weather APIs. Use the other tabs for safe live demos if API quota or network reliability is a concern.

## Demo

Use `docs/demo_plan.md` for the full presentation flow.

Recommended sequence:

1. Demo A: Product walkthrough for a non-technical audience.
2. Demo B: Stable audit failure case that does not spend API quota.
3. Demo C: What-if scenario simulation that does not spend API quota.
4. Demo D: UI command center walkthrough.
5. Demo E: Full product run with Gemini/OpenAI key.

Stable audit demo:

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
for violation in result["violations"]:
    print(f"- {violation['rule_id']} | {violation['severity']} | {violation['required_fix']}")
PY
```

What-if scenario demo:

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
    print("Summary:", scenario["summary"])
    for impact in scenario["kpi_impacts"]:
        print(f"- {impact['kpi']}: {impact['baseline']} -> {impact['simulated']} ({impact['severity']})")
PY
```

Full product run:

```bash
python src/main.py
```

## LLM Provider and Cost Guardrails

The app can run with either OpenAI or Gemini:

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-001
GOOGLE_API_KEY=your_google_ai_studio_key
```

For student/free testing, keep:

```env
GEMINI_FREE_TIER_ONLY=true
LLM_MAX_CALLS_PER_RUN=6
```

`GEMINI_FREE_TIER_ONLY=true` makes the app refuse Vertex AI / paid-mode settings. `LLM_MAX_CALLS_PER_RUN` stops runaway graph loops from making too many LLM calls in one process.

Important: the code cannot verify whether your Google project has billing enabled. To stay inside the free tier, create the key in Google AI Studio, do not upgrade the project to paid billing, and keep Google-side quotas/billing disabled.
