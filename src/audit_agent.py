from __future__ import annotations

from typing import Any, Dict, List


def _risk_score(weather_risk: Dict[str, Any]) -> int | None:
    score = weather_risk.get("route_risk_score_0_3", weather_risk.get("risk_score_0_3"))
    try:
        return int(score)
    except (TypeError, ValueError):
        return None


def _plan_mentions_escalation(dispatch_plan: str) -> bool:
    lowered = dispatch_plan.lower()
    return any(term in lowered for term in ("escalat", "manager", "review", "approval"))


def run_audit_agent(state: dict) -> dict:
    dispatch_plan = state.get("dispatch_plan", "")
    weather_risk = state.get("weather_risk", {})
    ops_data_result = state.get("ops_data_result", {})
    business_context = state.get("business_context", "")

    violations: List[Dict[str, Any]] = []
    score = _risk_score(weather_risk)

    if score == 3 and not _plan_mentions_escalation(dispatch_plan):
        violations.append(
            {
                "rule_id": "safety_weather_001",
                "rule": "Must escalate if Risk Score is 3.",
                "issue": "Planner produced a risk_score=3 dispatch plan without manager escalation or review language.",
                "required_fix": "Revise the dispatch plan to include manager escalation before final report generation.",
                "source": "PDF safety protocol / weather risk contract",
            }
        )

    for constraint in ops_data_result.get("constraints", []):
        rule_text = constraint.get("rule", "")
        if "must acknowledge material data quality issues" in rule_text.lower():
            if "missing" not in dispatch_plan.lower() and "data quality" not in dispatch_plan.lower():
                violations.append(
                    {
                        "rule_id": constraint.get("id", "ops_quality_001"),
                        "rule": rule_text,
                        "issue": "Planner did not acknowledge material data quality issues from OpsDataAgent.",
                        "required_fix": "Add a concise data quality caveat and explain how it affects dispatch confidence.",
                        "source": constraint.get("source", "OpsDataAgent"),
                    }
                )

        if "planner must explain the dispatch impact" in rule_text.lower():
            if "trend" not in dispatch_plan.lower() and "period" not in dispatch_plan.lower():
                violations.append(
                    {
                        "rule_id": constraint.get("id", "ops_trend_001"),
                        "rule": rule_text,
                        "issue": "Planner did not explain the dispatch impact of high-change trend metrics.",
                        "required_fix": "Explain how the trend analysis changes buffer, resource allocation, monitoring, or contingency triggers.",
                        "source": constraint.get("source", "OpsDataAgent"),
                    }
                )

    if "escalate" in business_context.lower() and score == 3 and not _plan_mentions_escalation(dispatch_plan):
        violations.append(
            {
                "rule_id": "pdf_context_escalation_001",
                "rule": "PDF context contains escalation language for high-risk conditions.",
                "issue": "Planner appears to omit escalation language despite high-risk context.",
                "required_fix": "Add explicit escalation and approval steps.",
                "source": "ContextAgent",
            }
        )

    audit_status = "pass" if not violations else "fail"
    feedback = ""
    if violations:
        feedback = "\n".join(
            f"- {v['required_fix']} (rule: {v['rule']})"
            for v in violations
        )

    return {
        "audit_result": {
            "agent_name": "AuditAgent",
            "audit_status": audit_status,
            "violations": violations,
            "feedback_to_planner": feedback,
        }
    }
