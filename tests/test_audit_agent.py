from audit_agent import run_audit_agent


def test_audit_fails_when_risk_score_3_without_escalation():
    state = {
        "dispatch_plan": "Use a 40% weather buffer and dispatch on the primary route.",
        "weather_risk": {"risk_score_0_3": 3},
    }

    result = run_audit_agent(state)["audit_result"]

    assert result["audit_status"] == "fail"
    assert result["violations"][0]["rule_id"] == "safety_weather_001"
    assert "manager escalation" in result["feedback_to_planner"]


def test_audit_passes_when_risk_score_3_has_escalation():
    state = {
        "dispatch_plan": "Use a 40% buffer and escalate to manager review before dispatch.",
        "weather_risk": {"route_risk_score_0_3": 3},
    }

    result = run_audit_agent(state)["audit_result"]

    assert result["audit_status"] == "pass"
    assert result["violations"] == []
