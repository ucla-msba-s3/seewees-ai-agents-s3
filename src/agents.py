from __future__ import annotations
import os
from typing import Any, Dict
from prompts import PDF_CONTEXT_PROMPT, OPS_ANALYSIS_PROMPT, PLANNER_PROMPT, REPORT_PROMPT

_llm: Any | None = None
_llm_calls = 0


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _guard_free_tier_settings(provider: str) -> None:
    if provider != "gemini":
        return

    if not _env_bool("GEMINI_FREE_TIER_ONLY", True):
        raise RuntimeError(
            "GEMINI_FREE_TIER_ONLY is disabled. Refusing to run so the project does not accidentally use paid Gemini API access."
        )

    if _env_bool("GOOGLE_GENAI_USE_VERTEXAI", False):
        raise RuntimeError(
            "GOOGLE_GENAI_USE_VERTEXAI is enabled. Free-tier guard only allows the Gemini Developer API via Google AI Studio."
        )


def _check_call_budget() -> None:
    global _llm_calls
    max_calls = int(os.getenv("LLM_MAX_CALLS_PER_RUN", "6"))
    if _llm_calls >= max_calls:
        raise RuntimeError(
            f"LLM call budget exceeded: {max_calls} calls in this process. "
            "Increase LLM_MAX_CALLS_PER_RUN only when you intentionally want more calls."
        )
    _llm_calls += 1


def reset_call_budget() -> None:
    """Reset the per-run LLM call counter. Call once at the start of each pipeline run."""
    global _llm_calls
    _llm_calls = 0


def get_llm() -> Any:
    global _llm
    if _llm is None:
        provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
        _guard_free_tier_settings(provider)

        if provider == "gemini":
            if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
                raise RuntimeError(
                    "Gemini provider selected but no GOOGLE_API_KEY or GEMINI_API_KEY is set. "
                    "Create a free-tier key in Google AI Studio and add it to .env."
                )

            from langchain_google_genai import ChatGoogleGenerativeAI

            _llm = ChatGoogleGenerativeAI(
                model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
                max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
            )
        elif provider == "openai":
            from langchain_openai import ChatOpenAI

            _llm = ChatOpenAI(
                model=os.getenv("LLM_MODEL", "gpt-4.1-mini"),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
                tags=["msba-demo", "multi-agent"],
                metadata={"repo": "MSBA_AI_Agents_Demo"},
            )
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER={provider!r}. Use 'openai' or 'gemini'.")
    return _llm


def run_context_agent(snippets: str) -> str:
    _check_call_budget()
    return get_llm().invoke(PDF_CONTEXT_PROMPT.format_messages(snippets=snippets)).content

def run_ops_agent(summary: Dict[str, Any], kpis: Dict[str, Any], anomalies_md: str) -> str:
    _check_call_budget()
    return get_llm().invoke(OPS_ANALYSIS_PROMPT.format_messages(
        summary=summary, kpis=kpis, anomalies_md=anomalies_md
    )).content

def run_planner_agent(
    business_context: str,
    ops_insights: str,
    weather_risk: Dict[str, Any],
    ops_data_result: Dict[str, Any] | None = None,
    scenario_result: Dict[str, Any] | None = None,
    playbook_constraints: list[Dict[str, Any]] | None = None,
    audit_feedback: str = "",
) -> str:
    _check_call_budget()
    return get_llm().invoke(PLANNER_PROMPT.format_messages(
        business_context=business_context,
        ops_insights=ops_insights,
        ops_data_result=ops_data_result or {},
        weather_risk=weather_risk,
        scenario_result=scenario_result or {},
        playbook_constraints=playbook_constraints or [],
        audit_feedback=audit_feedback or "(none)",
    )).content

def run_report_agent(
    business_context: str,
    kpis: Dict[str, Any],
    anomaly_highlights: str,
    weather_risk: Dict[str, Any],
    dispatch_plan: str,
    audit_result: Dict[str, Any] | None = None,
    scenario_result: Dict[str, Any] | None = None,
    playbook_constraints: list[Dict[str, Any]] | None = None,
) -> str:
    _check_call_budget()
    return get_llm().invoke(REPORT_PROMPT.format_messages(
        business_context=business_context,
        kpis=kpis,
        anomaly_highlights=anomaly_highlights,
        weather_risk=weather_risk,
        dispatch_plan=dispatch_plan,
        audit_result=audit_result or {},
        scenario_result=scenario_result or {},
        playbook_constraints=playbook_constraints or [],
    )).content
