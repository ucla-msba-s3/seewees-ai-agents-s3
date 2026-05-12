from __future__ import annotations

from typing import Any, Callable, Dict, List


RuleCheck = Callable[[dict], Dict[str, Any] | None]


def _risk_score(weather_risk: Dict[str, Any]) -> int | None:
    score = weather_risk.get("route_risk_score_0_3", weather_risk.get("risk_score_0_3"))
    try:
        return int(score)
    except (TypeError, ValueError):
        return None


def _plan_contains_any(dispatch_plan: str, terms: tuple[str, ...]) -> bool:
    lowered = dispatch_plan.lower()
    return any(term in lowered for term in terms)


def _violation(
    *,
    rule_id: str,
    rule: str,
    issue: str,
    required_fix: str,
    source: str,
    severity: str,
) -> Dict[str, Any]:
    return {
        "rule_id": rule_id,
        "rule": rule,
        "issue": issue,
        "required_fix": required_fix,
        "source": source,
        "severity": severity,
    }


def _check_critical_weather_escalation(state: dict) -> Dict[str, Any] | None:
    dispatch_plan = state.get("dispatch_plan", "")
    score = _risk_score(state.get("weather_risk", {}))

    if score == 3 and not _plan_contains_any(dispatch_plan, ("escalat", "manager", "review", "approval")):
        return _violation(
            rule_id="safety_weather_001",
            rule="Must escalate if Risk Score is 3.",
            issue="Planner produced a risk_score=3 dispatch plan without manager escalation or review language.",
            required_fix="Revise the dispatch plan to include manager escalation before final report generation.",
            source="PDF safety protocol / weather risk contract",
            severity="critical",
        )
    return None


def _check_pdf_escalation_context(state: dict) -> Dict[str, Any] | None:
    dispatch_plan = state.get("dispatch_plan", "")
    business_context = state.get("business_context", "")
    score = _risk_score(state.get("weather_risk", {}))

    if (
        score == 3
        and "escalate" in business_context.lower()
        and not _plan_contains_any(dispatch_plan, ("escalat", "manager", "review", "approval"))
    ):
        return _violation(
            rule_id="pdf_context_escalation_001",
            rule="PDF context contains escalation language for high-risk conditions.",
            issue="Planner appears to omit escalation language despite high-risk context.",
            required_fix="Add explicit escalation and approval steps.",
            source="ContextAgent",
            severity="critical",
        )
    return None


def _check_data_quality_acknowledgement(state: dict) -> Dict[str, Any] | None:
    dispatch_plan = state.get("dispatch_plan", "")
    ops_data_result = state.get("ops_data_result", {})

    has_quality_issue = bool(ops_data_result.get("data_quality_issues"))
    has_quality_constraint = any(
        "data quality" in constraint.get("rule", "").lower()
        or "missing" in constraint.get("rule", "").lower()
        for constraint in ops_data_result.get("constraints", [])
    )

    if (has_quality_issue or has_quality_constraint) and not _plan_contains_any(
        dispatch_plan,
        ("data quality", "missing", "assumption", "confidence", "caveat"),
    ):
        return _violation(
            rule_id="ops_quality_001",
            rule="Planner must acknowledge material data quality issues before final report generation.",
            issue="Planner did not acknowledge missing or unreliable data flagged by OpsDataAgent.",
            required_fix="Add a concise data quality caveat and explain how it affects dispatch confidence.",
            source="OpsDataAgent",
            severity="medium",
        )
    return None


def _check_trend_impact_explained(state: dict) -> Dict[str, Any] | None:
    dispatch_plan = state.get("dispatch_plan", "")
    ops_data_result = state.get("ops_data_result", {})

    metrics = ops_data_result.get("trend_analysis", {}).get("metrics", [])
    has_high_trend = any(metric.get("severity") in {"high", "critical"} for metric in metrics)
    has_trend_constraint = any(
        "trend" in constraint.get("rule", "").lower()
        or "period-over-period" in constraint.get("rule", "").lower()
        for constraint in ops_data_result.get("constraints", [])
    )

    if (has_high_trend or has_trend_constraint) and not _plan_contains_any(
        dispatch_plan,
        ("trend", "period", "change", "buffer", "resource", "capacity", "monitor"),
    ):
        return _violation(
            rule_id="ops_trend_001",
            rule="Planner must explain dispatch impact when operational trend risk is high.",
            issue="Planner did not explain how high-change trend metrics affect dispatch buffers, resource allocation, or monitoring.",
            required_fix="Explain how the trend analysis changes buffer, resource allocation, monitoring, or contingency triggers.",
            source="OpsDataAgent",
            severity="high",
        )
    return None


AUDIT_RULES: List[Dict[str, Any]] = [
    {
        "id": "safety_weather_001",
        "description": "Critical weather risk requires explicit escalation.",
        "source": "PDF safety protocol / weather risk contract",
        "check": _check_critical_weather_escalation,
    },
    {
        "id": "pdf_context_escalation_001",
        "description": "PDF-derived escalation context must be reflected in the plan.",
        "source": "ContextAgent",
        "check": _check_pdf_escalation_context,
    },
    {
        "id": "ops_quality_001",
        "description": "Material data quality issues must be acknowledged.",
        "source": "OpsDataAgent",
        "check": _check_data_quality_acknowledgement,
    },
    {
        "id": "ops_trend_001",
        "description": "High trend risk must change planning or monitoring.",
        "source": "OpsDataAgent",
        "check": _check_trend_impact_explained,
    },
]


def run_audit_agent(state: dict) -> dict:
    violations: List[Dict[str, Any]] = []
    evaluated_rules: List[Dict[str, str]] = []

    for rule in AUDIT_RULES:
        evaluated_rules.append(
            {
                "rule_id": rule["id"],
                "description": rule["description"],
                "source": rule["source"],
            }
        )
        violation = rule["check"](state)
        if violation:
            violations.append(violation)

    audit_status = "pass" if not violations else "fail"
    feedback = ""
    if violations:
        feedback = "\n".join(
            f"- [{v['severity'].upper()}] {v['required_fix']} (rule: {v['rule']})"
            for v in violations
        )

    return {
        "audit_result": {
            "agent_name": "AuditAgent",
            "audit_status": audit_status,
            "evaluated_rules": evaluated_rules,
            "violations": violations,
            "feedback_to_planner": feedback,
        }
    }
