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


def _route_blockage_result(scenario: Dict[str, Any]) -> Dict[str, Any]:
    params = scenario.get("parameters", {})
    waypoint = params.get("blocked_waypoint", "W3")
    closure_hours = float(params.get("closure_hours", 4.0))

    reroute_km_map = {"W1": 30, "W2": 45, "W3": 80, "W4": 55, "W5": 20}
    reroute_km = reroute_km_map.get(waypoint, 60)

    reroute_delay = reroute_km / 60.0
    total_delay = round(closure_hours * 0.5 + reroute_delay, 1)
    sla_at_risk_pct = round(min(1.0, total_delay / 6.0), 2)
    severity = _severity(total_delay, medium=2.0, high=4.0, critical=6.0)

    city_map = {"W1": "Newark NJ", "W2": "Bronx NY", "W3": "New Haven CT",
                "W4": "Providence RI", "W5": "Boston MA"}
    city = city_map.get(waypoint, waypoint)

    return {
        "scenario_name": scenario.get("scenario_name", f"I-95 blockage at {waypoint}"),
        "type": "route_blockage",
        "status": "success",
        "summary": (
            f"I-95 blockage at {waypoint} ({city}) for {closure_hours:.0f}h forces a {reroute_km}km reroute, "
            f"adding ~{total_delay}h delay. {int(sla_at_risk_pct * 100)}% of Tier-1 SLA window consumed by delay alone."
        ),
        "kpi_impacts": [
            {"kpi": "estimated_delay_hours",  "baseline": 0.0, "simulated": total_delay,
             "change": total_delay,       "severity": severity},
            {"kpi": "reroute_distance_km",    "baseline": 0,   "simulated": reroute_km,
             "change": reroute_km,        "severity": "medium"},
            {"kpi": "tier1_sla_consumed_pct", "baseline": 0.0, "simulated": sla_at_risk_pct,
             "change": sla_at_risk_pct,   "severity": severity},
        ],
        "constraints": [
            {
                "id": "scenario_route_001",
                "rule": (
                    "If I-95 blockage causes delay > 2h, planner must specify rerouting options, "
                    "alternate staging, and SLA-risk notifications for affected hospitals."
                ),
                "severity": "high",
                "source": "ScenarioAgent",
            }
        ] if total_delay > 2.0 else [],
        "recommendations": [
            f"Reroute shipments around {waypoint} ({city}) via the nearest alternate highway.",
            "Prioritize Tier-1 drugs (Epinephrine, Remdesivir) on first available clear route.",
            "Stage non-critical shipments at nearest depot until corridor reopens.",
            "Proactively notify all destination hospitals of revised ETA.",
        ],
    }


def _hospital_surge_result(scenario: Dict[str, Any]) -> Dict[str, Any]:
    params = scenario.get("parameters", {})
    hospital = params.get("surge_hospital", "Boston-MGH")
    surge_level = params.get("surge_level", "moderate").lower()

    compression_h    = {"moderate": 3,    "severe": 5   }.get(surge_level, 3)
    priority_count   = {"moderate": 8,    "severe": 15  }.get(surge_level, 8)
    conflict_pct     = {"moderate": 0.25, "severe": 0.50}.get(surge_level, 0.25)
    sev              = "critical" if surge_level == "severe" else "high"

    return {
        "scenario_name": scenario.get("scenario_name", f"{hospital} emergency surge"),
        "type": "hospital_surge",
        "status": "success",
        "summary": (
            f"{surge_level.capitalize()} emergency surge at {hospital}: "
            f"{priority_count} shipments escalated to Tier-1 priority. "
            f"Delivery window compressed by {compression_h}h; "
            f"{int(conflict_pct * 100)}% of normal dispatch schedule conflicts with surge demand."
        ),
        "kpi_impacts": [
            {"kpi": "priority_shipments_escalated", "baseline": 0,   "simulated": priority_count,
             "change": priority_count,  "severity": sev},
            {"kpi": "sla_compression_hours",        "baseline": 0,   "simulated": compression_h,
             "change": compression_h,   "severity": sev},
            {"kpi": "schedule_conflict_pct",        "baseline": 0.0, "simulated": conflict_pct,
             "change": conflict_pct,    "severity": "high"},
        ],
        "constraints": [
            {
                "id": "scenario_surge_001",
                "rule": (
                    f"Emergency surge at {hospital} requires immediate driver reallocation and "
                    "priority escalation. Planner must address expedited delivery and backup stock."
                ),
                "severity": "critical",
                "source": "ScenarioAgent",
            }
        ],
        "recommendations": [
            f"Immediately escalate all {hospital} shipments to Tier-1 priority.",
            "Reallocate drivers from lower-priority routes to cover surge demand.",
            f"Notify {hospital} pharmacy team of expedited delivery window.",
            "Trigger backup stock request if on-hand inventory cannot meet surge volume.",
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
    if scenario_type == "route_blockage":
        return _route_blockage_result(scenario)
    if scenario_type == "hospital_surge":
        return _hospital_surge_result(scenario)

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
