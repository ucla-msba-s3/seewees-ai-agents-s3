from scenario_agent import run_scenario_agent


def test_scenario_agent_simulates_default_scenarios():
    result = run_scenario_agent({})["scenario_result"]

    assert result["status"] == "success"
    assert result["data"]["scenario_count"] == 3
    assert result["constraints"]
    assert result["recommendations"]


def test_demand_spike_generates_capacity_constraint():
    result = run_scenario_agent(
        {
            "scenarios": [
                {
                    "scenario_name": "30% demand spike",
                    "type": "demand_spike",
                    "parameters": {"demand_spike_pct": 0.30},
                }
            ]
        }
    )["scenario_result"]

    constraint_ids = [constraint["id"] for constraint in result["constraints"]]

    assert "scenario_capacity_001" in constraint_ids
    assert result["scenarios"][0]["kpi_impacts"][0]["severity"] in {"high", "critical"}
