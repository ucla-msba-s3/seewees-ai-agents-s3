# Demo Plan

This demo is written for an audience that has not seen the codebase before. The goal is to show the product as an audited dispatch decision system, not just a collection of agents.

## One-Sentence Product Pitch

SeeWeeS Multi-Agent Dispatch QA turns incomplete logistics data into an audited, executive-ready dispatch recommendation for time-critical specialty medicine deliveries.

## Demo A: Product Walkthrough

Purpose: Explain what the system does before running anything.

Steps:

1. Start with the business scenario.
   - SeeWeeS delivers time-sensitive specialty medicine.
   - A bad dispatch decision can cause SLA failure, spoilage risk, or unsafe routing.
   - Executives need a clear recommendation, not raw PDF/CSV/weather data.

2. Show the inputs.
   - `data/SeeWeeS Specialty Dispatch Playbook.pdf`
   - `data/Incoming_shipment_03_06.csv`
   - Weather risk from I-95 corridor waypoints.

3. Show the agent pipeline.

   ```text
   ContextAgent -> OpsDataAgent -> WeatherAgent -> PlannerAgent -> AuditAgent -> ReportAgent
                                                    ↑              |
                                                    | fail         | pass
                                                    +--------------+
   ```

4. Explain each agent in one sentence.
   - ContextAgent extracts business rules, constraints, thresholds, and escalation policies from the PDF.
   - OpsDataAgent analyzes shipment data, missing fields, trends, item mappings, and planning constraints.
   - WeatherAgent converts corridor forecasts into route-level risk scores.
   - PlannerAgent combines the evidence into a dispatch recommendation.
   - AuditAgent checks the plan against safety rules and operational constraints.
   - ReportAgent creates an executive-ready HTML decision packet.

5. Briefly show `docs/project_background.md`.
   - Point to missing links.
   - Point to KPI definitions.
   - Point to the data augmentation strategy.

Talk track:

```text
The core value is not only that we generate a report. The system identifies missing operational links, augments the data, turns them into KPIs and constraints, and blocks unsafe recommendations before leadership sees them.
```

## Demo B: Stable Audit Failure Case

Purpose: Show the self-correction logic without relying on live LLM or network calls.

This demo is deterministic and does not spend Gemini/OpenAI quota.

Command:

```bash
PYTHONPATH=src python - <<'PY'
import json
from audit_agent import run_audit_agent
from graph import route_after_audit

with open("examples/audit_fail_case.json", encoding="utf-8") as f:
    case = json.load(f)

result = run_audit_agent(case["state"])["audit_result"]
next_step = route_after_audit({
    "audit_result": result,
    "audit_retry_count": 1,
})

print("Audit status:", result["audit_status"])
print("Next graph step:", next_step)
print("\nViolations:")
for violation in result["violations"]:
    print(f"- {violation['rule_id']} | {violation['severity']} | {violation['required_fix']}")

print("\nFeedback to Planner:")
print(result["feedback_to_planner"])
PY
```

Expected result:

```text
Audit status: fail
Next graph step: planner
Violations:
- safety_weather_001
- pdf_context_escalation_001
- ops_quality_001
```

What to say:

```text
This is the system handling failure. The route risk score is critical, but the draft plan forgot manager escalation. Instead of sending that plan to executives, AuditAgent returns structured feedback and LangGraph routes back to PlannerAgent.
```

## Demo C: Full Product Run

Purpose: Show the complete product experience.

Before running:

1. Confirm `.env` exists and contains a valid key:

   ```env
   LLM_PROVIDER=gemini
   GOOGLE_API_KEY=...
   GEMINI_FREE_TIER_ONLY=true
   LLM_MAX_CALLS_PER_RUN=6
   REPORT_EMAIL_TO=
   ```

2. Keep `REPORT_EMAIL_TO=` empty unless the team intentionally wants to test email delivery.

3. Run tests first:

   ```bash
   PYTHONPATH=src python -m pytest -q
   ```

Full run:

```bash
python src/main.py
```

What the run demonstrates:

- PDF rules and constraints are retrieved.
- CSV operations data is summarized.
- Weather risk is calculated.
- PlannerAgent proposes a dispatch plan.
- AuditAgent checks the plan.
- ReportAgent produces an executive HTML report.

Backup plan:

- If live API quota, weather network, or latency becomes a problem, use Demo B and a saved/sample report screenshot or HTML output.
- The presentation should not depend entirely on a live LLM call.

What to say after the run:

```text
The final output is not a raw model answer. It is an executive decision packet: decision, top risks, recommended actions, KPI snapshot, and audit status.
```

## Closing Comparison Against Baseline

Baseline:

```text
Retrieve -> Analyze -> Plan -> Report
```

Enhanced system:

```text
Retrieve -> Analyze -> Plan -> Audit -> Correct -> Report
```

Closing line:

```text
We redesigned the pipeline so SeeWeeS can move from simple reporting to audited operational decision support for high-stakes medical logistics.
```
