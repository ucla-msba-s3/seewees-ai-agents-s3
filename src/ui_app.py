from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import streamlit as st
from dotenv import load_dotenv

from audit_agent import run_audit_agent
from graph import build_graph, route_after_audit
from ops_data_agent import run_ops_data_agent
from scenario_agent import run_scenario_agent
from tools.csv_tools import analyze_csv


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = "data/SeeWeeS Specialty Dispatch Playbook.pdf"
DEFAULT_CSV = "data/Incoming_shipment_03_06.csv"
SCENARIO_EXAMPLE = ROOT / "examples" / "scenario_input.json"
AUDIT_EXAMPLE = ROOT / "examples" / "audit_fail_case.json"
OUTPUT_DIR = ROOT / "outputs"


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_box(label: str, value: Any) -> None:
    st.caption(label)
    st.json(value, expanded=False)


def _status_badge(label: str, value: str) -> None:
    value_l = value.lower()
    if value_l in {"pass", "success", "go"}:
        st.success(f"{label}: {value}")
    elif value_l in {"fail", "failed", "critical"}:
        st.error(f"{label}: {value}")
    else:
        st.info(f"{label}: {value}")


def render_overview() -> None:
    st.subheader("SeeWeeS Multi-Agent Dispatch QA")
    st.write(
        "This UI simulates how an operations user would evaluate a time-critical specialty medicine dispatch plan."
    )

    st.markdown(
        """
        **Agent flow**

        `ContextAgent -> OpsDataAgent -> WeatherAgent -> ScenarioAgent -> PlannerAgent -> AuditAgent -> ReportAgent`

        **What leadership sees**

        - Executive decision
        - Top operational risks
        - Scenario-based contingency recommendations
        - KPI snapshot
        - Audit status before final report
        """
    )

    st.divider()
    cols = st.columns(4)
    cols[0].metric("Default scenarios", "3")
    cols[1].metric("Audit retry limit", "2")
    cols[2].metric("LLM cap", "env-configured")
    cols[3].metric("Email", "optional")

    st.info(
        "Use the Scenario and Audit tabs for stable no-quota demos. Use Full Pipeline only when a valid Gemini/OpenAI key is configured."
    )


def render_ops_tab() -> None:
    st.subheader("OpsDataAgent Contract Test")
    st.write("This tab lets function owners verify the output shape expected by the backbone.")

    csv_path = st.text_input("CSV path", DEFAULT_CSV, key="ops_csv")

    if st.button("Run local CSV summary + OpsDataAgent contract", key="run_ops"):
        try:
            analysis = analyze_csv(csv_path)
            ops_result = run_ops_data_agent({"csv_path": csv_path})["ops_data_result"]

            cols = st.columns(3)
            cols[0].metric("Rows", analysis.summary.get("rows_after_drop_empty"))
            cols[1].metric("Columns", analysis.summary.get("cols_original"))
            cols[2].metric("Numeric columns", len(analysis.numeric_cols))

            _status_badge("OpsDataAgent status", ops_result.get("status", "unknown"))
            _json_box("OpsDataAgent output", ops_result)
        except Exception as exc:
            st.exception(exc)


def render_scenario_tab() -> None:
    st.subheader("What-if Scenario Simulation")
    st.write("Simulate demand, warehouse, or driver disruptions without spending LLM quota.")

    default_text = SCENARIO_EXAMPLE.read_text(encoding="utf-8")
    scenario_text = st.text_area("Scenario JSON", default_text, height=260)

    if st.button("Run ScenarioAgent", key="run_scenario"):
        try:
            state = json.loads(scenario_text)
            result = run_scenario_agent(state)["scenario_result"]

            _status_badge("ScenarioAgent status", result.get("status", "unknown"))
            st.write(result.get("summary", ""))

            for scenario in result.get("scenarios", []):
                with st.expander(scenario.get("scenario_name", "Scenario"), expanded=True):
                    st.write(scenario.get("summary", ""))
                    st.table(scenario.get("kpi_impacts", []))
                    st.write("Recommendations")
                    for rec in scenario.get("recommendations", []):
                        st.markdown(f"- {rec}")

            _json_box("Raw scenario_result", result)
        except Exception as exc:
            st.exception(exc)


def render_audit_tab() -> None:
    st.subheader("AuditAgent Failure Handling")
    st.write("Test whether the system blocks unsafe or incomplete plans before leadership reporting.")

    default_state = _load_json(AUDIT_EXAMPLE)["state"]
    state_text = st.text_area("Audit test state JSON", json.dumps(default_state, indent=2), height=360)

    if st.button("Run AuditAgent", key="run_audit"):
        try:
            state = json.loads(state_text)
            audit_result = run_audit_agent(state)["audit_result"]
            next_step = route_after_audit({"audit_result": audit_result, "audit_retry_count": 1})

            _status_badge("Audit status", audit_result.get("audit_status", "unknown"))
            st.info(f"Next graph step: {next_step}")

            violations = audit_result.get("violations", [])
            if violations:
                st.table(
                    [
                        {
                            "rule_id": v.get("rule_id"),
                            "severity": v.get("severity"),
                            "source": v.get("source"),
                            "required_fix": v.get("required_fix"),
                        }
                        for v in violations
                    ]
                )
            else:
                st.success("No violations detected.")

            st.write("Feedback to Planner")
            st.code(audit_result.get("feedback_to_planner", "") or "(none)")
            _json_box("Raw audit_result", audit_result)
        except Exception as exc:
            st.exception(exc)


def render_full_pipeline_tab() -> None:
    st.subheader("Full Product Run")
    st.warning(
        "This runs the full graph and may call Gemini/OpenAI embeddings, chat models, and weather APIs. Use it sparingly for demo."
    )

    pdf_path = st.text_input("PDF path", DEFAULT_PDF, key="full_pdf")
    csv_path = st.text_input("CSV path", DEFAULT_CSV, key="full_csv")
    scenario_text = st.text_area(
        "Optional scenarios JSON",
        SCENARIO_EXAMPLE.read_text(encoding="utf-8"),
        height=220,
        key="full_scenario",
    )

    if st.button("Run Full Pipeline", type="primary", key="run_full"):
        try:
            scenarios_state = json.loads(scenario_text)
            state = {
                "pdf_path": pdf_path,
                "csv_path": csv_path,
                "scenarios": scenarios_state.get("scenarios", []),
            }

            with st.spinner("Running multi-agent graph..."):
                app = build_graph()
                final = app.invoke(state)

            report_html = final.get("report_html", "")
            OUTPUT_DIR.mkdir(exist_ok=True)
            output_path = OUTPUT_DIR / "report.html"
            output_path.write_text(report_html, encoding="utf-8")

            audit_result = final.get("audit_result", {})
            scenario_result = final.get("scenario_result", {})

            _status_badge("Audit status", audit_result.get("audit_status", "unknown"))
            st.write(f"Saved report to `{output_path}`")

            with st.expander("Scenario result", expanded=False):
                st.json(scenario_result)
            with st.expander("Audit result", expanded=False):
                st.json(audit_result)

            st.components.v1.html(report_html, height=700, scrolling=True)
        except Exception as exc:
            st.exception(exc)


def main() -> None:
    load_dotenv(ROOT / ".env")
    st.set_page_config(page_title="SeeWeeS Dispatch QA", layout="wide")

    st.title("SeeWeeS Dispatch QA Command Center")
    st.caption("Multi-agent dispatch planning with scenario simulation and audit-loop self-correction")

    tabs = st.tabs(
        [
            "Overview",
            "OpsData",
            "Scenarios",
            "Audit",
            "Full Pipeline",
        ]
    )

    with tabs[0]:
        render_overview()
    with tabs[1]:
        render_ops_tab()
    with tabs[2]:
        render_scenario_tab()
    with tabs[3]:
        render_audit_tab()
    with tabs[4]:
        render_full_pipeline_tab()


if __name__ == "__main__":
    main()
