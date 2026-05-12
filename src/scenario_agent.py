from __future__ import annotations

from typing import Any, Dict, List


DEFAULT_SCENARIOS: List[Dict[str, Any]] = [
    {
        "scenario_name": "20% demand spike",
        "type": "demand_spike",
        "parameters": {"demand_spike_pct": 0.20},
    },
    {
        "scenario_name": "Primary warehouse closure",
        "type": "warehouse_closure",
        "parameters": {"closed_warehouse": "primary"},
    },
    {
        "scenario_name": "Driver shortage",
        "type": "driver_shortage",
        "parameters": {"available_driver_pct": 0.75},
    },
]


def _severity(value: float, medium: float, high: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= high:
        return "high"
    if value >= medium:
        return "medium"
    return "low"


def _demand_spike_result(scenario: Dict[str, Any]) -> Dict[str, Any]:
    spike = float(scenario.get("parameters", {}).get("demand_spike_pct", 0.20))
    baseline_utilization = 0.78
    simulated_utilization = min(1.25, baseline_utilization * (1 + spike))
    severity = _severity(simulated_utilization, medium=0.85, high=0.90, critical=1.0)

    return {
        "scenario_name": scenario.get("scenario_name", "Demand spike"),
        "type": "demand_spike",
        "status": "success",
        "summary": f"Demand spike of {spike:.0%} raises simulated capacity utilization from {baseline_utilization:.0%} to {simulated_utilization:.0%}.",
        "kpi_impacts": [
            {
                "kpi": "capacity_utilization",
                "baseline": baseline_utilization,
                "simulated": simulated_utilization,
                "change": simulated_utilization - baseline_utilization,
                "severity": severity,
            }
        ],
        "constraints": [
            {
                "id": "scenario_capacity_001",
                "rule": "If simulated capacity utilization exceeds 90%, planner must recommend backup capacity or shipment prioritization.",
                "severity": "high",
                "source": "ScenarioAgent",
            }
        ] if simulated_utilization > 0.90 else [],
        "recommendations": [
            "Prioritize hospital-critical shipments.",
            "Reserve backup cold-chain capacity.",
            "Move non-critical shipments to a later dispatch window if utilization exceeds capacity.",
        ],
    }


def _warehouse_closure_result(scenario: Dict[str, Any]) -> Dict[str, Any]:
    closed = scenario.get("parameters", {}).get("closed_warehouse", "primary")
    baseline_delay_hours = 0.0
    simulated_delay_hours = 6.0

    return {
        "scenario_name": scenario.get("scenario_name", "Warehouse closure"),
        "type": "warehouse_closure",
        "status": "success",
        "summary": f"Closure of the {closed} warehouse creates an estimated {simulated_delay_hours:.1f} hour routing delay.",
        "kpi_impacts": [
            {
                "kpi": "estimated_delay_hours",
                "baseline": baseline_delay_hours,
                "simulated": simulated_delay_hours,
                "change": simulated_delay_hours - baseline_delay_hours,
                "severity": "high",
            }
        ],
        "constraints": [
            {
                "id": "scenario_warehouse_001",
                "rule": "If a warehouse is closed, planner must include rerouting, alternate staging, or delayed dispatch options.",
                "severity": "high",
                "source": "ScenarioAgent",
            }
        ],
        "recommendations": [
            "Reroute affected shipments through the alternate staging location.",
            "Escalate critical shipments for manual release approval.",
            "Notify customer success of any SLA-risk shipments.",
        ],
    }


def _driver_shortage_result(scenario: Dict[str, Any]) -> Dict[str, Any]:
    available_pct = float(scenario.get("parameters", {}).get("available_driver_pct", 0.75))
    shortage_pct = max(0.0, 1.0 - available_pct)
    baseline_coverage = 1.0
    simulated_coverage = available_pct
    severity = _severity(shortage_pct, medium=0.10, high=0.20, critical=0.35)

    return {
        "scenario_name": scenario.get("scenario_name", "Driver shortage"),
        "type": "driver_shortage",
        "status": "success",
        "summary": f"Driver availability falls to {available_pct:.0%}, leaving a simulated {shortage_pct:.0%} coverage gap.",
        "kpi_impacts": [
            {
                "kpi": "driver_coverage",
                "baseline": baseline_coverage,
                "simulated": simulated_coverage,
                "change": simulated_coverage - baseline_coverage,
                "severity": severity,
            }
        ],
        "constraints": [
            {
                "id": "scenario_driver_001",
                "rule": "If driver coverage falls below 85%, planner must recommend backup staffing, carrier support, or route prioritization.",
                "severity": "high",
                "source": "ScenarioAgent",
            }
        ] if available_pct < 0.85 else [],
        "recommendations": [
            "Assign drivers to hospital-priority and cold-chain shipments first.",
            "Use backup carrier support for lower-priority routes.",
            "Consolidate non-critical deliveries where SLA impact is acceptable.",
        ],
    }


def _simulate_one(scenario: Dict[str, Any]) -> Dict[str, Any]:
    scenario_type = scenario.get("type")
    if scenario_type == "demand_spike":
        return _demand_spike_result(scenario)
    if scenario_type == "warehouse_closure":
        return _warehouse_closure_result(scenario)
    if scenario_type == "driver_shortage":
        return _driver_shortage_result(scenario)

    return {
        "scenario_name": scenario.get("scenario_name", "Unknown scenario"),
        "type": scenario_type or "unknown",
        "status": "unsupported",
        "summary": "Unsupported scenario type. No KPI impact simulated.",
        "kpi_impacts": [],
        "constraints": [],
        "recommendations": [],
    }


def run_scenario_agent(state: dict) -> dict:
    scenarios = state.get("scenarios") or DEFAULT_SCENARIOS
    scenario_results = [_simulate_one(scenario) for scenario in scenarios]

    all_constraints = [
        constraint
        for result in scenario_results
        for constraint in result.get("constraints", [])
    ]
    all_recommendations = [
        recommendation
        for result in scenario_results
        for recommendation in result.get("recommendations", [])
    ]

    highest_severity = "low"
    severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    for result in scenario_results:
        for impact in result.get("kpi_impacts", []):
            severity = impact.get("severity", "low")
            if severity_rank.get(severity, 0) > severity_rank[highest_severity]:
                highest_severity = severity

    return {
        "scenario_result": {
            "agent_name": "ScenarioAgent",
            "status": "success",
            "summary": f"Simulated {len(scenario_results)} what-if scenarios; highest KPI impact severity is {highest_severity}.",
            "scenarios": scenario_results,
            "constraints": all_constraints,
            "recommendations": all_recommendations,
            "data": {
                "scenario_count": len(scenario_results),
                "highest_severity": highest_severity,
            },
        }
    }
