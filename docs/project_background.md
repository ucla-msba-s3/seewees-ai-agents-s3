# SeeWeeS Multi-Agent Dispatch QA System

## Business Problem

SeeWeeS handles time-critical specialty medicine distribution. The baseline system can retrieve documents, analyze shipment data, check weather, and produce a report, but the original flow is linear. A linear flow is risky in medical logistics because a weak dispatch plan can move directly into an executive report without being challenged against safety protocols, data quality gaps, or operational constraints.

Our enhancement redesigns the workflow as a rule-grounded multi-agent system. The PlannerAgent must pass an AuditAgent quality gate before the ReportAgent can generate the final executive HTML report. If the audit finds a violated safety rule or ignored constraint, the graph loops back to the PlannerAgent with corrective feedback.

## Data Augmentation Strategy

The current data and documents do not contain every variable needed for realistic dispatch planning. We therefore identify missing links, define how they connect to existing data, and either derive or simulate them when needed.

| Missing Link | Why It Matters | Connection to Existing Data | Derive or Simulate | Used By |
| --- | --- | --- | --- | --- |
| Corridor weather risk score `0-3` | Medical shipments are vulnerable to severe weather and corridor disruption. | Route waypoints from the playbook plus weather forecast data. | Derived from precipitation, wind gust, temperature, and route-level max risk. | PlannerAgent, AuditAgent, ReportAgent |
| Manager escalation requirement | High-risk shipments should not be finalized without oversight. | Weather risk score and PDF safety rules. | Derived rule: risk score `3` requires escalation. | AuditAgent |
| Data quality confidence | Missing shipment fields reduce reliability of planning recommendations. | CSV missingness and OpsDataAgent quality checks. | Derived from missing fields, affected records, and severity. | OpsDataAgent, PlannerAgent, AuditAgent |
| Period-over-period operational trend | A single anomaly snapshot can miss worsening operating conditions. | Current shipment CSV plus date/time or row-order periods. | Function owner will calculate trend metrics and severity. | OpsDataAgent, PlannerAgent, AuditAgent |
| Item Master identifier mapping | Missing item or SKU fields can hide product class and cold-chain needs. | Shipment CSV plus Item Master Appendix snippets from playbook. | Function owner will cross-reference or simulate mapping confidence. | OpsDataAgent, PlannerAgent |
| Hospital priority level | Not all destinations carry equal clinical urgency. | Destination, product class, customer type, or simulated priority table. | Simulate priority level if not provided. | PlannerAgent, ReportAgent |
| Cold-chain capacity / truck availability | Recommendations are unrealistic without resource limits. | Shipment volume, product class, and simulated fleet assumptions. | Simulate capacity constraints if no fleet table exists. | PlannerAgent, AuditAgent |
| What-if disruption parameters | Leadership needs contingency plans before disruptions happen. | User-provided scenario JSON or default scenario assumptions. | Simulate demand spike, warehouse closure, or driver shortage. | ScenarioAgent, PlannerAgent, AuditAgent, ReportAgent |

## KPI Definitions

| KPI | Calculation | Data Dependencies | Risk / Success Threshold |
| --- | --- | --- | --- |
| Route Risk Score | Maximum weather risk across route waypoints. | Waypoint coordinates, daily forecast metrics. | `0-1` normal, `2` elevated, `3` critical and requires escalation. |
| Dispatch Buffer | Percent time buffer added to planned dispatch. | Route risk score. | `0 -> 0%`, `1 -> 10%`, `2 -> 25%`, `3 -> 40% + escalation`. |
| Data Quality Issue Count | Count of material missing or unreliable fields. | Shipment CSV, OpsDataAgent checks. | Any high-severity issue must be acknowledged in plan. |
| Trend Risk Severity | Period-over-period change in operational metric. | Shipment metrics split by week, month, date, or row-order periods. | `>=25%` medium, `>=50%` high, `>=75%` critical. |
| Audit Pass Rate | Whether the plan passes rule checks before report generation. | Dispatch plan, weather risk, PDF constraints, Ops constraints. | Final report should be generated only after pass or retry-limit warning. |
| Scenario KPI Impact | Difference between baseline and simulated KPI under a disruption. | Scenario type and parameters, capacity assumptions, resource assumptions. | High/critical impacts require contingency recommendations. |

## Technical Methodology

The graph uses LangGraph with a shared state object. The current architecture is:

```text
pdf_context -> csv_analysis / OpsDataAgent -> weather -> ScenarioAgent -> planner -> audit -> report -> email
```

The audit node adds non-linear behavior:

```text
PlannerAgent -> AuditAgent
Audit pass -> ReportAgent
Audit fail -> PlannerAgent with feedback
```

The retry limit prevents infinite loops. If the retry limit is reached, the system still produces a report, but the audit result and remaining caveats are passed into the ReportAgent so leadership can see the unresolved risk.

## What-If Scenario Simulation

The ScenarioAgent evaluates hypothetical operational disruptions before final planning. The default scenarios are:

- 20% demand spike.
- Primary warehouse closure.
- Driver shortage.

Each scenario produces KPI impacts, constraints, and contingency recommendations. This connects missing operational variables, such as available drivers, warehouse status, and capacity limits, to executive decisions. It also gives AuditAgent additional constraints to enforce so the final report cannot ignore high-impact disruptions.

## Quality Assurance Logic

The AuditAgent acts as the quality gate. It enforces:

- Safety rules extracted from the playbook and weather risk contract.
- Constraints emitted by OpsDataAgent, including data quality and trend-impact requirements.
- Constraints emitted by ScenarioAgent, including capacity, rerouting, warehouse, and driver shortage contingencies.
- Executive readiness checks, such as requiring escalation language for critical risk.

This design prevents bad information from moving directly to leadership and demonstrates how the system handles failure rather than only summarizing successful cases.

## Executive Storytelling Standard

The final report should be concise and decision-oriented. It should include:

- Executive decision: go, delay, reroute, escalate, or hold for review.
- Top risks with evidence and business impact.
- Concrete actions, owner, and timing.
- KPI snapshot and threshold interpretation.
- Audit status, corrections made, and any remaining caveats.

The goal is not just to summarize data. The report should explain what leadership should do, why it matters, and which operational constraints support the recommendation.
