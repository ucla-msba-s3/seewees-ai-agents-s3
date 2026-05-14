from __future__ import annotations

import re
from typing import Any, Dict, List


DEFAULT_BUFFER_POLICY = {
    0: 0,
    1: 10,
    2: 25,
    3: 40,
}


def _extract_buffer_policy(text: str) -> Dict[int, int]:
    policy = dict(DEFAULT_BUFFER_POLICY)
    normalized = re.sub(r"\s+", " ", text)

    # Supports both "risk_score 2 -> 25% buffer" and "risk score 2 ... 25% buffer".
    pattern = re.compile(
        r"risk[_\s-]*score\s*(\d)\D{0,80}?(\d{1,3})\s*%\s*buffer",
        re.IGNORECASE,
    )
    for score, pct in pattern.findall(normalized):
        try:
            policy[int(score)] = int(pct)
        except ValueError:
            continue

    return policy


def extract_playbook_constraints(snippets: str, business_context: str = "") -> List[Dict[str, Any]]:
    """
    Convert retrieved playbook text into structured constraints.

    This keeps AuditAgent grounded in PDF-derived rules without depending on
    fragile LLM JSON parsing. If the retrieved snippets are incomplete, the
    known SeeWeeS buffer policy is used as a deterministic fallback.
    """
    text = f"{snippets}\n\n{business_context}"
    buffer_policy = _extract_buffer_policy(text)

    constraints: List[Dict[str, Any]] = [
        {
            "id": "playbook_weather_buffer_001",
            "rule_type": "weather_buffer_policy",
            "rule": (
                "Planner must apply the SeeWeeS weather buffer policy: "
                "risk_score 0 -> 0%, 1 -> 10%, 2 -> 25%, 3 -> 40% buffer."
            ),
            "severity": "high",
            "source": "SeeWeeS Dispatch Playbook §5.2",
            "parameters": {
                "buffer_pct_by_risk_score": buffer_policy,
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

    if re.search(r"precipitation_sum\s*[≥>=]\s*15", text, re.IGNORECASE):
        constraints.append(
            {
                "id": "playbook_weather_trigger_001",
                "rule_type": "weather_trigger_reference",
                "rule": "Heavy precipitation risk is triggered when precipitation_sum is at least 15.0 mm/day.",
                "severity": "medium",
                "source": "SeeWeeS Dispatch Playbook §5.1",
                "parameters": {
                    "precipitation_sum_mm_day_threshold": 15.0,
                },
            }
        )

    if re.search(r"wind_gusts_10m_max\s*[≥>=]\s*45", text, re.IGNORECASE):
        constraints.append(
            {
                "id": "playbook_weather_trigger_002",
                "rule_type": "weather_trigger_reference",
                "rule": "High wind risk is triggered when wind_gusts_10m_max is at least 45.0 km/h.",
                "severity": "medium",
                "source": "SeeWeeS Dispatch Playbook §5.1",
                "parameters": {
                    "wind_gusts_10m_max_kmh_threshold": 45.0,
                },
            }
        )

    if re.search(r"temperature_2m_min\s*[≤<=]\s*0", text, re.IGNORECASE):
        constraints.append(
            {
                "id": "playbook_weather_trigger_003",
                "rule_type": "weather_trigger_reference",
                "rule": "Freezing risk is triggered when temperature_2m_min is at most 0.0 C.",
                "severity": "medium",
                "source": "SeeWeeS Dispatch Playbook §5.1",
                "parameters": {
                    "temperature_2m_min_c_threshold": 0.0,
                },
            }
        )

    return constraints
