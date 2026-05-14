from audit_agent import run_audit_agent
from scenario_agent import run_scenario_agent


PLAYBOOK_CONSTRAINTS = [
    {
        "id": "playbook_weather_buffer_001",
        "rule_type": "weather_buffer_policy",
        "rule": "Planner must apply the SeeWeeS weather buffer policy.",
        "severity": "high",
        "source": "SeeWeeS Dispatch Playbook §5.2",
        "parameters": {
            "buffer_pct_by_risk_score": {0: 0, 1: 10, 2: 25, 3: 40},
        },
    },
    {
        "id": "playbook_weather_escalation_001",
        "rule_type": "weather_escalation_policy",
        "rule": "Planner must require manager escalation or review when weather risk_score is 3.",
        "severity": "critical",
        "source": "SeeWeeS Dispatch Playbook §5.2",
        "parameters": {
            "escalation_required_scores": [3],
        },
    },
]


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


def test_audit_fails_when_scenario_constraint_not_addressed():
    state = {
        "dispatch_plan": "Proceed with dispatch as planned.",
        "weather_risk": {"risk_score_0_3": 1},
        "scenario_result": {
            "constraints": [
                {
                    "id": "scenario_capacity_001",
                    "rule": "If simulated capacity utilization exceeds 90%, planner must recommend backup capacity or shipment prioritization.",
                    "severity": "high",
                    "source": "ScenarioAgent",
                }
            ]
        },
    }

    result = run_audit_agent(state)["audit_result"]
    rule_ids = [violation["rule_id"] for violation in result["violations"]]

    assert result["audit_status"] == "fail"
    assert "scenario_contingency_001" in rule_ids


def test_audit_fails_when_playbook_buffer_policy_not_met():
    state = {
        "dispatch_plan": "Proceed with a 10% weather buffer.",
        "weather_risk": {"risk_score_0_3": 2},
        "playbook_constraints": PLAYBOOK_CONSTRAINTS,
    }

    result = run_audit_agent(state)["audit_result"]
    rule_ids = [violation["rule_id"] for violation in result["violations"]]

    assert result["audit_status"] == "fail"
    assert "playbook_weather_buffer_001" in rule_ids


def test_audit_passes_when_playbook_buffer_policy_is_met():
    state = {
        "dispatch_plan": "Proceed with the playbook-required 25% weather buffer.",
        "weather_risk": {"risk_score_0_3": 2},
        "playbook_constraints": PLAYBOOK_CONSTRAINTS,
    }

    result = run_audit_agent(state)["audit_result"]

    assert result["audit_status"] == "pass"
    assert result["violations"] == []


def test_mock_prelaunch_repeated_audit_and_scenario_runs():
    bad_plan_state = {
        "dispatch_plan": "Proceed with a 10% weather buffer.",
        "weather_risk": {"risk_score_0_3": 2},
        "playbook_constraints": PLAYBOOK_CONSTRAINTS,
    }

    for _ in range(50):
        audit_result = run_audit_agent(bad_plan_state)["audit_result"]
        scenario_result = run_scenario_agent({})["scenario_result"]

        assert audit_result["audit_status"] == "fail"
        assert scenario_result["status"] == "success"
