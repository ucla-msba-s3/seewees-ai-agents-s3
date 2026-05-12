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


def _inject_css() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    /* ── Base ─────────────────────────────────────────────────── */
    html, body, .stApp {
        background: #f0f2f6 !important;
        font-family: 'Inter', sans-serif;
    }
    .block-container { padding-top: 1.5rem !important; }

    /* ── Metric cards ─────────────────────────────────────────── */
    [data-testid="metric-container"] {
        background: #ffffff;
        border: 1.5px solid #e2e8f0;
        border-radius: 14px;
        padding: 1rem 1.2rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    [data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 1.1px;
    }
    [data-testid="stMetricValue"] {
        color: #1e40af !important;
        font-size: 1.5rem !important;
        font-weight: 800 !important;
    }

    /* ── Tab strip ────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        background: #ffffff;
        border-radius: 14px;
        padding: 6px 8px;
        gap: 6px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
        margin-bottom: 0.5rem;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: #64748b;
        border-radius: 10px;
        font-weight: 600;
        font-size: 0.87rem;
        padding: 0.45rem 1.4rem !important;
        transition: all 0.18s;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: #f1f5f9;
        color: #1e40af;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #3b82f6, #6366f1) !important;
        color: #ffffff !important;
        box-shadow: 0 3px 10px rgba(99, 102, 241, 0.35);
    }

    /* ── Buttons ──────────────────────────────────────────────── */
    .stButton > button {
        background: linear-gradient(135deg, #3b82f6, #6366f1) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        padding: 0.55rem 1.8rem !important;
        box-shadow: 0 3px 10px rgba(99, 102, 241, 0.3) !important;
        transition: all 0.18s ease !important;
        letter-spacing: 0.2px !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 18px rgba(99, 102, 241, 0.4) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #059669, #10b981) !important;
        box-shadow: 0 3px 10px rgba(16, 185, 129, 0.3) !important;
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 6px 18px rgba(16, 185, 129, 0.4) !important;
    }

    /* ── Inputs ───────────────────────────────────────────────── */
    .stTextInput input, .stTextArea textarea {
        background: #ffffff !important;
        border: 1.5px solid #e2e8f0 !important;
        border-radius: 10px !important;
        color: #1e293b !important;
        font-size: 0.9rem !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12) !important;
    }
    .stTextInput label, .stTextArea label, .stSlider label {
        color: #374151 !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
    }

    /* ── Checkboxes ───────────────────────────────────────────── */
    .stCheckbox label, .stCheckbox label p, .stCheckbox span,
    [data-testid="stCheckbox"] label, [data-testid="stCheckbox"] p,
    [data-testid="stCheckbox"] span { color: #1e293b !important; font-weight: 600 !important; }

    /* ── Slider labels & values ───────────────────────────────── */
    [data-testid="stSlider"] label, [data-testid="stSlider"] p,
    [data-testid="stSlider"] span, .stSlider label, .stSlider p,
    div[data-testid="stSlider"] > div > div > p { color: #1e293b !important; font-weight: 600 !important; }

    /* ── Select/radio labels ──────────────────────────────────── */
    [data-testid="stSelectbox"] label, [data-testid="stRadio"] label,
    [data-testid="stSelectbox"] p, [data-testid="stRadio"] p,
    .stSelectbox label, .stRadio label { color: #1e293b !important; font-weight: 600 !important; }
    [data-testid="stRadio"] span { color: #374151 !important; }

    /* ── Info / warning / alert text ─────────────────────────── */
    [data-testid="stAlert"] p, [data-testid="stAlert"] span,
    [data-testid="stAlert"] li, [data-testid="stAlert"] strong,
    div[role="alert"] p { color: #1e293b !important; }
    .stInfo [data-testid="stMarkdownContainer"] p { color: #1e40af !important; font-weight: 500 !important; }
    .stWarning [data-testid="stMarkdownContainer"] p { color: #92400e !important; font-weight: 500 !important; }

    /* ── Expander ─────────────────────────────────────────────── */
    [data-testid="stExpander"] {
        background: #ffffff !important;
        border: 1.5px solid #e2e8f0 !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
    }
    [data-testid="stExpander"] summary {
        color: #374151 !important;
        font-weight: 600 !important;
    }

    /* ── Caption / helper text ───────────────────────────────── */
    [data-testid="stCaptionContainer"] p,
    [data-testid="stCaptionContainer"],
    .stCaption, .stCaption p,
    small, caption { color: #475569 !important; font-size: 0.8rem !important; }

    /* ── Alerts ───────────────────────────────────────────────── */
    [data-testid="stAlert"] { border-radius: 12px !important; font-weight: 500; }
    .stSuccess { background: #f0fdf4 !important; border-color: #86efac !important; color: #166534 !important; }
    .stInfo    { background: #eff6ff !important; border-color: #93c5fd !important; color: #1e40af !important; }
    .stWarning { background: #fffbeb !important; border-color: #fcd34d !important; color: #92400e !important; }
    .stError   { background: #fef2f2 !important; border-color: #fca5a5 !important; color: #991b1b !important; }

    /* ── Dividers ─────────────────────────────────────────────── */
    hr { border-color: #e2e8f0 !important; }

    /* ── Spinner ──────────────────────────────────────────────── */
    .stSpinner > div > div { border-top-color: #6366f1 !important; }

    /* ── Custom cards ─────────────────────────────────────────── */
    .sw-card {
        background: #ffffff;
        border: 1.5px solid #e2e8f0;
        border-radius: 16px;
        padding: 1.3rem 1.5rem;
        margin-bottom: 0.85rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .sw-card-accent-blue  { border-left: 5px solid #3b82f6; }
    .sw-card-accent-green { border-left: 5px solid #10b981; }
    .sw-card-accent-purple{ border-left: 5px solid #8b5cf6; }
    .sw-card-accent-orange{ border-left: 5px solid #f59e0b; }
    .sw-card-title {
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: #94a3b8;
        margin-bottom: 0.6rem;
    }
    .sw-label {
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.4px;
        color: #94a3b8;
        margin: 1.1rem 0 0.5rem 0;
    }
    /* Status badges */
    .sw-badge {
        display: inline-flex; align-items: center; gap: 0.35rem;
        padding: 0.32rem 1rem;
        border-radius: 99px;
        font-size: 0.83rem; font-weight: 700;
        margin: 0.3rem 0;
    }
    .sw-badge-pass   { background: #dcfce7; color: #15803d; border: 1.5px solid #86efac; }
    .sw-badge-fail   { background: #fee2e2; color: #dc2626; border: 1.5px solid #fca5a5; }
    .sw-badge-warn   { background: #fef9c3; color: #a16207; border: 1.5px solid #fde047; }
    .sw-badge-info   { background: #dbeafe; color: #1d4ed8; border: 1.5px solid #93c5fd; }

    /* Pipeline steps */
    .sw-pipe-step {
        display: flex; align-items: flex-start; gap: 0.9rem;
        padding: 0.7rem 0;
        border-bottom: 1px solid #f1f5f9;
    }
    .sw-pipe-step:last-child { border-bottom: none; }
    .sw-pipe-icon {
        width: 36px; height: 36px;
        border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1rem; flex-shrink: 0;
    }
    .sw-pipe-name { color: #1e293b; font-size: 0.9rem; font-weight: 700; }
    .sw-pipe-desc { color: #64748b; font-size: 0.78rem; margin-top: 0.12rem; }

    /* Violation cards */
    .sw-violation {
        background: #fff1f2;
        border: 1.5px solid #fecdd3;
        border-left: 5px solid #ef4444;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        margin: 0.5rem 0;
    }
    .sw-violation-high {
        background: #fff7ed;
        border: 1.5px solid #fed7aa;
        border-left: 5px solid #f97316;
    }
    .sw-violation-medium {
        background: #fefce8;
        border: 1.5px solid #fef08a;
        border-left: 5px solid #eab308;
    }
    .sw-violation-header {
        display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.45rem;
    }
    .sw-violation-tag {
        font-size: 0.67rem; font-weight: 800;
        text-transform: uppercase; letter-spacing: 1px;
        padding: 0.18rem 0.6rem; border-radius: 99px;
    }
    .sw-vtag-critical { background: #fee2e2; color: #dc2626; }
    .sw-vtag-high     { background: #ffedd5; color: #c2410c; }
    .sw-vtag-medium   { background: #fef9c3; color: #a16207; }
    .sw-violation-rule { color: #374151; font-size: 0.78rem; font-weight: 600; }
    .sw-violation-desc { color: #4b5563; font-size: 0.88rem; margin-bottom: 0.4rem; }
    .sw-violation-fix-label {
        font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.8px; color: #94a3b8; margin-bottom: 0.2rem;
    }
    .sw-violation-fix { color: #1e293b; font-size: 0.87rem; font-weight: 500; }

    /* Feedback box */
    .sw-feedback-box {
        background: #fffbeb;
        border: 1.5px solid #fde68a;
        border-radius: 12px;
        padding: 1rem 1.2rem;
    }
    .sw-feedback-item {
        display: flex; gap: 0.6rem; align-items: flex-start;
        padding: 0.45rem 0;
        border-bottom: 1px solid #fef3c7;
        color: #78350f; font-size: 0.88rem; line-height: 1.5;
    }
    .sw-feedback-item:last-child { border-bottom: none; }
    .sw-feedback-num {
        background: #f59e0b; color: #fff;
        font-size: 0.7rem; font-weight: 800;
        width: 20px; height: 20px; border-radius: 99px;
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0; margin-top: 0.1rem;
    }

    /* Next step chip */
    .sw-next-chip {
        display: inline-flex; align-items: center; gap: 0.4rem;
        background: #eff6ff; border: 1.5px solid #93c5fd;
        border-radius: 10px; padding: 0.42rem 1rem;
        color: #1d4ed8; font-size: 0.87rem; font-weight: 700;
        margin: 0.3rem 0;
    }

    /* Scenario cards */
    .sw-scenario-tag {
        font-size: 0.65rem; font-weight: 800;
        text-transform: uppercase; letter-spacing: 1px;
        padding: 0.18rem 0.6rem; border-radius: 99px;
    }
    .sw-stag-demand   { background: #dbeafe; color: #1d4ed8; }
    .sw-stag-warehouse{ background: #fce7f3; color: #be185d; }
    .sw-stag-staffing { background: #f3e8ff; color: #7c3aed; }
    .sw-stag-route    { background: #fef3c7; color: #b45309; }
    .sw-stag-surge    { background: #fee2e2; color: #dc2626; }

    /* KPI rows */
    .sw-kpi-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 0.38rem 0; border-bottom: 1px solid #f1f5f9;
        font-size: 0.85rem;
    }
    .sw-kpi-row:last-child { border-bottom: none; }
    .sw-kpi-name { color: #64748b; }
    .sw-kpi-val  { font-weight: 700; color: #1e40af; }
    .sw-kpi-neg  { font-weight: 700; color: #dc2626; }
    .sw-kpi-pos  { font-weight: 700; color: #059669; }

    /* Recommendation list */
    .sw-rec { display: flex; gap: 0.5rem; padding: 0.3rem 0; color: #374151; font-size: 0.86rem; }
    .sw-rec-dot { color: #6366f1; font-weight: 800; flex-shrink: 0; }

    /* Test case detail row */
    .sw-detail-row {
        display: flex; align-items: center; gap: 0.6rem;
        padding: 0.5rem 0; border-bottom: 1px solid #f1f5f9;
        font-size: 0.87rem;
    }
    .sw-detail-row:last-child { border-bottom: none; }
    .sw-detail-icon { font-size: 1.1rem; flex-shrink: 0; }
    .sw-detail-label { color: #64748b; font-weight: 600; min-width: 140px; }
    .sw-detail-value { color: #1e293b; font-weight: 500; }

    /* Header gradient bar */
    .sw-header {
        background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 50%, #ec4899 100%);
        border-radius: 16px;
        padding: 1.5rem 1.8rem;
        margin-bottom: 1.4rem;
        box-shadow: 0 4px 20px rgba(99, 102, 241, 0.25);
    }

    /* Hide Streamlit chrome */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    [data-testid="stToolbar"] { display: none; }
    </style>
    """, unsafe_allow_html=True)


def _badge_html(label: str, value: str) -> str:
    v = value.lower()
    if v in {"pass", "success", "go"}:
        cls, icon = "sw-badge-pass", "✅"
    elif v in {"fail", "failed", "critical", "no-go"}:
        cls, icon = "sw-badge-fail", "❌"
    elif v in {"warning", "warn"}:
        cls, icon = "sw-badge-warn", "⚠️"
    else:
        cls, icon = "sw-badge-info", "ℹ️"
    return f'<span class="sw-badge {cls}">{icon}&nbsp;{label}: {value.upper()}</span>'


def _status_badge(label: str, value: str) -> None:
    st.markdown(_badge_html(label, value), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# TAB 1 · OVERVIEW
# ─────────────────────────────────────────────────────────────────

def render_overview() -> None:
    st.markdown("""
    <div class="sw-card sw-card-accent-blue">
        <div class="sw-card-title">About This System</div>
        <p style="color:#1e293b;margin:0;font-size:0.95rem;line-height:1.7;font-weight:400">
        The <strong style="color:#2563eb">SeeWeeS Multi-Agent Dispatch QA System</strong> orchestrates
        seven specialized AI agents to deliver executive-ready dispatch plans for time-critical specialty
        medicine logistics. It enforces safety protocols, simulates operational disruptions, and
        <strong>self-corrects</strong> before any plan reaches leadership.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sw-label">Agent Pipeline</div>', unsafe_allow_html=True)

    agents = [
        ("📋", "#dbeafe", "Context Agent",   "Extracts business rules & safety protocols from the SeeWeeS playbook via RAG"),
        ("📊", "#dcfce7", "Ops Data Agent", "Analyzes incoming shipment data — KPIs, anomalies, trend analysis, data quality"),
        ("🌤", "#fef9c3", "Weather Agent",  "Real-time weather risk scoring across I-95 corridor waypoints (Open-Meteo API)"),
        ("⚡", "#fce7f3", "Scenario Agent", "Simulates what-if disruptions: demand spikes, warehouse closures, driver shortages"),
        ("🧠", "#f3e8ff", "Planner Agent",  "Generates AI-driven dispatch plan grounded in operational constraints"),
        ("🛡", "#ffedd5", "Audit Agent",    "Validates plan against safety rules — loops back to Planner Agent if violations found"),
        ("📝", "#e0f2fe", "Report Agent",   "Produces structured, executive-ready HTML report for leadership decision-making"),
    ]

    rows = "".join(f"""
    <div class="sw-pipe-step">
        <div class="sw-pipe-icon" style="background:{bg}">{icon}</div>
        <div>
            <div class="sw-pipe-name">{name}</div>
            <div class="sw-pipe-desc">{desc}</div>
        </div>
    </div>""" for icon, bg, name, desc in agents)
    st.markdown(f'<div class="sw-card">{rows}</div>', unsafe_allow_html=True)

    st.markdown('<div class="sw-label">System Configuration</div>', unsafe_allow_html=True)
    c = st.columns(4)
    c[0].metric("Built-in Scenarios", "5")
    c[1].metric("Audit Retry Limit", "2")
    c[2].metric("LLM Budget Cap", "Configurable")
    c[3].metric("Email Delivery", "Optional")

    st.info(
        "**Demo tip —** Use the **Scenarios** and **Audit** tabs for live demos without consuming API quota. "
        "**Full Pipeline** requires a valid Gemini or OpenAI key."
    )


# ─────────────────────────────────────────────────────────────────
# TAB 2 · OPS DATA
# ─────────────────────────────────────────────────────────────────

def render_ops_tab() -> None:
    st.markdown("""
    <div class="sw-card sw-card-accent-green">
        <div class="sw-card-title">Ops Data Agent — Contract Validation</div>
        <p style="color:#1e293b;margin:0;font-size:0.92rem;line-height:1.65">
        Runs analysis on incoming shipment data and validates that the Ops Data Agent output
        conforms to the schema expected by the multi-agent backbone.
        </p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("⚙️  Configure Data Source", expanded=False):
        csv_path = st.text_input("Shipment CSV path", DEFAULT_CSV, key="ops_csv")

    if st.button("🔍  Analyze Shipment Data", key="run_ops"):
        csv_path = st.session_state.get("ops_csv", DEFAULT_CSV)
        try:
            with st.spinner("Analyzing shipment data…"):
                analysis = analyze_csv(csv_path)
                ops_result = run_ops_data_agent({"csv_path": csv_path})["ops_data_result"]

            st.markdown('<div class="sw-label">Data Summary</div>', unsafe_allow_html=True)
            c = st.columns(3)
            c[0].metric("Shipment Records",  analysis.summary.get("rows_after_drop_empty", "—"))
            c[1].metric("Data Columns",      analysis.summary.get("cols_original", "—"))
            c[2].metric("Numeric Fields",    len(analysis.numeric_cols))

            st.markdown('<div style="margin-top:0.7rem"></div>', unsafe_allow_html=True)
            _status_badge("Contract Validation", ops_result.get("status", "unknown"))

            summary = ops_result.get("summary", "")
            if summary:
                st.markdown(
                    f'<div class="sw-card sw-card-accent-green" style="margin-top:0.8rem">'
                    f'<div class="sw-card-title">Summary</div>'
                    f'<p style="color:#1e293b;margin:0;font-size:0.92rem;line-height:1.65">{summary}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        except Exception as exc:
            st.exception(exc)


# ─────────────────────────────────────────────────────────────────
# TAB 3 · SCENARIOS
# ─────────────────────────────────────────────────────────────────

def render_scenario_tab() -> None:
    st.markdown("""
    <div class="sw-card sw-card-accent-purple">
        <div class="sw-card-title">What-if Scenario Simulation</div>
        <p style="color:#1e293b;margin:0;font-size:0.92rem;line-height:1.65">
        Simulate operational disruptions to assess KPI impact and generate contingency
        recommendations — <strong>no LLM quota consumed</strong>.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sw-label">Select &amp; Configure Scenarios</div>', unsafe_allow_html=True)

    HINT = "color:#475569;font-size:0.78rem;margin:.15rem 0 .6rem 0;line-height:1.45"

    # ── Row 1: Demand Spike + Driver Shortage ────────────────────
    col_a, col_b = st.columns(2)
    with col_a:
        demand_on = st.checkbox("📈  Demand Spike", value=True, key="sc_demand_on")
        if demand_on:
            demand_pct = st.slider("Spike intensity", 5, 50, 20, 5, format="%d%%", key="sc_demand_pct")
            st.markdown(f'<p style="{HINT}">How much demand exceeds the baseline — higher values push truck and driver capacity toward the limit.</p>', unsafe_allow_html=True)
    with col_b:
        driver_on = st.checkbox("🚚  Driver Shortage", value=True, key="sc_driver_on")
        if driver_on:
            driver_avail = st.slider("Driver availability", 50, 95, 75, 5, format="%d%%", key="sc_driver_pct")
            st.markdown(f'<p style="{HINT}">Percentage of drivers available for dispatch (e.g. 75% = 1 out of 4 drivers absent).</p>', unsafe_allow_html=True)

    # ── Row 2: Warehouse Closure ─────────────────────────────────
    warehouse_on = st.checkbox("🏭  Primary Warehouse Closure", value=True, key="sc_wh_on")
    if warehouse_on:
        st.markdown(f'<p style="{HINT}">Primary warehouse is unavailable — all shipments must reroute through the backup facility, adding an estimated 6-hour delay.</p>', unsafe_allow_html=True)

    st.markdown("<div style='margin-top:0.4rem'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Row 3: I-95 Route Blockage ───────────────────────────────
    blockage_on = st.checkbox("🚧  I-95 Route Blockage", value=False, key="sc_blockage_on")
    if blockage_on:
        col_c, col_d = st.columns(2)
        with col_c:
            wp_options = ["W1 — Newark, NJ", "W2 — Bronx, NY", "W3 — New Haven, CT",
                          "W4 — Providence, RI", "W5 — Boston, MA"]
            st.selectbox("Blocked waypoint", wp_options, index=2, key="sc_blockage_wp")
        with col_d:
            closure_hours = st.slider("Estimated closure (hours)", 1, 12, 4, 1, key="sc_closure_hours")
        st.markdown(f'<p style="{HINT}">Longer closures and mid-route blockages (e.g. W3 adds 80 km detour) increase total delay and Tier-1 SLA breach risk.</p>', unsafe_allow_html=True)

    # ── Row 4: Hospital Emergency Surge ─────────────────────────
    surge_on = st.checkbox("🏥  Hospital Emergency Surge", value=False, key="sc_surge_on")
    if surge_on:
        col_e, col_f = st.columns(2)
        with col_e:
            surge_hospital = st.selectbox(
                "Surge hospital",
                ["Boston-MGH", "Boston-BWH", "Boston-DanaFarber", "Boston-Children"],
                key="sc_surge_hospital",
            )
        with col_f:
            surge_level = st.radio("Severity", ["Moderate", "Severe"], horizontal=True, key="sc_surge_level")
        st.markdown(f'<p style="{HINT}">A surge compresses the delivery window and escalates shipments to Tier-1 priority. Severe = mass-casualty event requiring immediate reallocation.</p>', unsafe_allow_html=True)

    st.markdown("<div style='margin-top:0.6rem'></div>", unsafe_allow_html=True)
    if st.button("⚡  Run Scenario Analysis", key="run_scenario"):
        demand_on    = st.session_state.get("sc_demand_on",   True)
        driver_on    = st.session_state.get("sc_driver_on",   True)
        warehouse_on = st.session_state.get("sc_wh_on",       True)
        blockage_on  = st.session_state.get("sc_blockage_on", False)
        surge_on     = st.session_state.get("sc_surge_on",    False)
        demand_pct   = st.session_state.get("sc_demand_pct",  20)
        driver_avail = st.session_state.get("sc_driver_pct",  75)
        closure_hours  = st.session_state.get("sc_closure_hours",  4)
        surge_hospital = st.session_state.get("sc_surge_hospital", "Boston-MGH")
        surge_level    = st.session_state.get("sc_surge_level",    "Moderate")

        # Parse waypoint code from selectbox label (e.g. "W3 — New Haven, CT" → "W3")
        raw_wp = st.session_state.get("sc_blockage_wp", "W3 — New Haven, CT")
        blocked_wp = raw_wp.split(" — ")[0]

        scenarios: list[dict] = []
        if demand_on:
            scenarios.append({"scenario_name": f"{demand_pct}% demand spike",
                               "type": "demand_spike",
                               "parameters": {"demand_spike_pct": demand_pct / 100}})
        if warehouse_on:
            scenarios.append({"scenario_name": "Primary warehouse closure",
                               "type": "warehouse_closure",
                               "parameters": {"closed_warehouse": "primary"}})
        if driver_on:
            scenarios.append({"scenario_name": "Driver shortage",
                               "type": "driver_shortage",
                               "parameters": {"available_driver_pct": driver_avail / 100}})
        if blockage_on:
            scenarios.append({"scenario_name": f"I-95 blockage at {blocked_wp}",
                               "type": "route_blockage",
                               "parameters": {"blocked_waypoint": blocked_wp,
                                              "closure_hours": float(closure_hours)}})
        if surge_on:
            scenarios.append({"scenario_name": f"{surge_hospital} emergency surge",
                               "type": "hospital_surge",
                               "parameters": {"surge_hospital": surge_hospital,
                                              "surge_level": surge_level.lower()}})

        if not scenarios:
            st.warning("Select at least one scenario to simulate.")
            return

        try:
            with st.spinner("Running scenario simulation…"):
                result = run_scenario_agent({"scenarios": scenarios})["scenario_result"]

            _status_badge("Simulation Status", result.get("status", "unknown"))
            overall = result.get("summary", "")
            if overall:
                st.markdown(
                    f'<div class="sw-card" style="margin-top:0.7rem">'
                    f'<p style="color:#1e293b;margin:0;font-size:0.92rem;line-height:1.65">{overall}</p>'
                    f'</div>', unsafe_allow_html=True)

            st.markdown('<div class="sw-label" style="margin-top:0.8rem">Scenario Results</div>', unsafe_allow_html=True)

            type_meta = {
                "demand_spike":      ("sw-stag-demand",    "📈 Demand"),
                "warehouse_closure": ("sw-stag-warehouse", "🏭 Warehouse"),
                "driver_shortage":   ("sw-stag-staffing",  "🚚 Staffing"),
                "route_blockage":    ("sw-stag-route",     "🚧 Route"),
                "hospital_surge":    ("sw-stag-surge",     "🏥 Surge"),
            }

            for sc in result.get("scenarios", []):
                name    = sc.get("scenario_name", "Scenario")
                sc_type = sc.get("type", "")
                sc_sum  = sc.get("summary", "")
                kpis    = sc.get("kpi_impacts", [])
                recs    = sc.get("recommendations", [])
                tag_cls, tag_label = type_meta.get(sc_type, ("sw-badge-info", sc_type))

                kpi_rows = "".join(
                    f'<div class="sw-kpi-row">'
                    f'<span class="sw-kpi-name">{kpi.get("metric", kpi.get("kpi",""))}</span>'
                    f'<span class="{"sw-kpi-neg" if str(kpi.get("impact","")).startswith("-") else "sw-kpi-val"}">'
                    f'{kpi.get("impact", kpi.get("value","—"))}</span></div>'
                    for kpi in kpis
                )
                rec_rows = "".join(
                    f'<div class="sw-rec"><span class="sw-rec-dot">›</span><span>{r}</span></div>'
                    for r in recs
                )

                body = (
                    f'<div style="display:flex;align-items:center;gap:.55rem;margin-bottom:.4rem">'
                    f'<span class="sw-scenario-tag {tag_cls}">{tag_label}</span>'
                    f'<strong style="color:#1e293b;font-size:.95rem">{name}</strong></div>'
                )
                if sc_sum:
                    body += f'<p style="color:#64748b;font-size:.85rem;margin:.2rem 0 .7rem 0;line-height:1.5">{sc_sum}</p>'
                if kpi_rows:
                    body += f'<div class="sw-card-title" style="margin-top:.3rem">KPI Impact</div>{kpi_rows}'
                if rec_rows:
                    body += f'<div class="sw-label" style="margin-top:.8rem">Recommendations</div>{rec_rows}'

                st.markdown(f'<div class="sw-card">{body}</div>', unsafe_allow_html=True)

        except Exception as exc:
            st.exception(exc)


# ─────────────────────────────────────────────────────────────────
# TAB 4 · AUDIT
# ─────────────────────────────────────────────────────────────────

def render_audit_tab() -> None:
    st.markdown("""
    <div class="sw-card sw-card-accent-orange">
        <div class="sw-card-title">Audit Agent — Quality Gate</div>
        <p style="color:#1e293b;margin:0;font-size:0.92rem;line-height:1.65">
        Tests whether the system correctly <strong>blocks unsafe dispatch plans</strong> before they
        reach leadership. If violations are found, the plan is sent back to the Planner Agent
        for correction (up to 2 retries).
        </p>
    </div>
    """, unsafe_allow_html=True)

    audit_data = _load_json(AUDIT_EXAMPLE)

    # ── Preloaded test case — clear visual breakdown ──────────────
    st.markdown('<div class="sw-label">Preloaded Test Case</div>', unsafe_allow_html=True)

    state = audit_data["state"]
    weather = state.get("weather_risk", {})
    risk_score = weather.get("route_risk_score_0_3", "—")
    worst_wp = weather.get("worst_waypoint", {})
    dq_issues = state.get("ops_data_result", {}).get("data_quality_issues", [])
    dispatch_plan = state.get("dispatch_plan", "")

    risk_color = "#dc2626" if risk_score == 3 else "#f59e0b" if risk_score == 2 else "#059669"
    risk_label = {3: "🔴 Critical (3/3)", 2: "🟡 High (2/3)", 1: "🟢 Low (1/3)", 0: "✅ Clear (0/3)"}.get(risk_score, str(risk_score))

    st.markdown(f"""
    <div class="sw-card">
        <div class="sw-card-title">What's in this test case?</div>
        <div class="sw-detail-row">
            <span class="sw-detail-icon">🌩️</span>
            <span class="sw-detail-label">Weather Risk Score</span>
            <span class="sw-detail-value" style="color:{risk_color};font-weight:700">{risk_label}</span>
        </div>
        <div class="sw-detail-row">
            <span class="sw-detail-icon">📍</span>
            <span class="sw-detail-label">Worst Waypoint</span>
            <span class="sw-detail-value">{worst_wp.get("city","—")}, {worst_wp.get("state","—")} ({worst_wp.get("waypoint","—")})</span>
        </div>
        <div class="sw-detail-row">
            <span class="sw-detail-icon">⚠️</span>
            <span class="sw-detail-label">Data Quality Issues</span>
            <span class="sw-detail-value">{len(dq_issues)} issue(s) flagged by Ops Data Agent</span>
        </div>
        <div class="sw-detail-row">
            <span class="sw-detail-icon">📋</span>
            <span class="sw-detail-label">Dispatch Plan</span>
            <span class="sw-detail-value" style="color:#64748b;font-style:italic">"{dispatch_plan}"</span>
        </div>
        <div class="sw-detail-row" style="border-bottom:none">
            <span class="sw-detail-icon">❗</span>
            <span class="sw-detail-label">Known Problem</span>
            <span class="sw-detail-value" style="color:#dc2626;font-weight:600">Plan missing manager escalation despite critical weather risk</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🛡️  Run Audit Check", key="run_audit"):
        try:
            with st.spinner("Running audit agent…"):
                audit_result = run_audit_agent(state)["audit_result"]
                next_step    = route_after_audit({"audit_result": audit_result, "audit_retry_count": 1})

            # Status row
            col1, col2 = st.columns([1, 1])
            with col1:
                _status_badge("Audit Status", audit_result.get("audit_status", "unknown"))
            with col2:
                step_map = {"planner": "↩️  Return to Planner Agent", "report": "→  Proceed to Report Agent"}
                st.markdown(
                    f'<span class="sw-next-chip">{step_map.get(next_step, next_step)}</span>',
                    unsafe_allow_html=True)

            # Violations
            violations = audit_result.get("violations", [])
            if violations:
                n = len(violations)
                st.markdown(
                    f'<div class="sw-label" style="margin-top:1rem">🚨 {n} Violation{"s" if n>1 else ""} Detected</div>',
                    unsafe_allow_html=True)

                sev_cls   = {"critical": "sw-violation",        "high": "sw-violation sw-violation-high",
                             "medium":   "sw-violation sw-violation-medium"}
                tag_cls   = {"critical": "sw-vtag-critical",    "high": "sw-vtag-high", "medium": "sw-vtag-medium"}
                sev_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡"}

                for v in violations:
                    sev      = v.get("severity", "critical").lower()
                    rule_id  = v.get("rule_id", "")
                    source   = v.get("source", "")
                    issue    = v.get("issue", v.get("description", "Protocol violation"))
                    fix      = v.get("required_fix", "")

                    st.markdown(f"""
                    <div class="{sev_cls.get(sev,'sw-violation')}">
                        <div class="sw-violation-header">
                            <span class="sw-violation-tag {tag_cls.get(sev,'sw-vtag-critical')}">
                                {sev_icons.get(sev,'')} {sev.upper()}
                            </span>
                            <span class="sw-violation-rule">{rule_id} &nbsp;·&nbsp; {source}</span>
                        </div>
                        <div class="sw-violation-desc">🔍 &nbsp;{issue}</div>
                        {f'<div class="sw-violation-fix-label" style="margin-top:.5rem">Required Fix</div>'
                         f'<div class="sw-violation-fix">✏️ &nbsp;{fix}</div>' if fix else ''}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("✅  No violations detected — plan approved for reporting.")

            # Feedback — bullet list
            feedback_raw = audit_result.get("feedback_to_planner", "")
            if feedback_raw:
                st.markdown('<div class="sw-label" style="margin-top:1rem">📬 Feedback to Planner Agent</div>',
                            unsafe_allow_html=True)

                lines = [l.strip().lstrip("-").strip() for l in feedback_raw.splitlines() if l.strip()]
                items_html = "".join(
                    f'<div class="sw-feedback-item">'
                    f'<div class="sw-feedback-num">{i}</div>'
                    f'<div>{line}</div></div>'
                    for i, line in enumerate(lines, 1)
                )
                st.markdown(f'<div class="sw-feedback-box">{items_html}</div>', unsafe_allow_html=True)

        except Exception as exc:
            st.exception(exc)


# ─────────────────────────────────────────────────────────────────
# TAB 5 · FULL PIPELINE
# ─────────────────────────────────────────────────────────────────

def render_full_pipeline_tab() -> None:
    st.markdown("""
    <div class="sw-card sw-card-accent-blue">
        <div class="sw-card-title">Full Multi-Agent Pipeline</div>
        <p style="color:#1e293b;margin:0;font-size:0.92rem;line-height:1.65">
        Runs the complete agent graph end-to-end: context retrieval, ops analysis, weather scoring,
        scenario simulation, dispatch planning, audit, and report generation.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.warning("⚠️  This run calls Gemini / OpenAI and the Open-Meteo weather API. Use it sparingly.")

    with st.expander("⚙️  Configure Data Sources", expanded=False):
        pdf_path = st.text_input("Playbook PDF path", DEFAULT_PDF, key="full_pdf")
        csv_path = st.text_input("Shipment CSV path", DEFAULT_CSV, key="full_csv")

    st.markdown("<div style='margin-top:0.6rem'></div>", unsafe_allow_html=True)
    if st.button("🚀  Launch Full Pipeline", type="primary", key="run_full"):
        pdf_path = st.session_state.get("full_pdf", DEFAULT_PDF)
        csv_path = st.session_state.get("full_csv", DEFAULT_CSV)
        default_scenarios = _load_json(SCENARIO_EXAMPLE).get("scenarios", [])

        try:
            state = {"pdf_path": pdf_path, "csv_path": csv_path, "scenarios": default_scenarios}

            with st.spinner("Running multi-agent graph — this may take 30–90 seconds…"):
                app   = build_graph()
                final = app.invoke(state)

            OUTPUT_DIR.mkdir(exist_ok=True)
            report_html = final.get("report_html", "")
            (OUTPUT_DIR / "report.html").write_text(report_html, encoding="utf-8")

            audit_result    = final.get("audit_result",    {})
            scenario_result = final.get("scenario_result", {})

            col1, col2 = st.columns([1, 1])
            with col1:
                _status_badge("Audit Status", audit_result.get("audit_status", "unknown"))
            with col2:
                st.success("✅  Report saved → outputs/report.html")

            sc_list = scenario_result.get("scenarios", [])
            if sc_list:
                with st.expander("📊  Scenario Simulation Results", expanded=False):
                    for sc in sc_list:
                        st.markdown(f"**{sc.get('scenario_name','')}** — {sc.get('summary','')}")

            viols = audit_result.get("violations", [])
            if viols:
                with st.expander("🚨  Audit Violations", expanded=False):
                    for v in viols:
                        st.markdown(f"- **{v.get('rule_id','')}** [{v.get('severity','')}] {v.get('required_fix','')}")

            if report_html:
                st.markdown('<div class="sw-label" style="margin-top:1rem">Generated Report</div>', unsafe_allow_html=True)
                st.components.v1.html(report_html, height=700, scrolling=True)

        except Exception as exc:
            st.exception(exc)


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv(ROOT / ".env")
    st.set_page_config(
        page_title="SeeWeeS Dispatch Quality Assurance",
        page_icon="🏥",
        layout="wide",
    )

    _inject_css()

    # Header
    st.markdown("""
    <div class="sw-header">
        <div style="font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:2px;
                    color:rgba(255,255,255,0.7);margin-bottom:.35rem">
            SeeWeeS Specialty Distribution
        </div>
        <h1 style="margin:0;font-size:1.75rem;font-weight:800;color:#ffffff;letter-spacing:-.3px">
            🏥 Dispatch Quality Assurance Command Center
        </h1>
        <p style="margin:.3rem 0 0 0;color:rgba(255,255,255,0.75);font-size:.9rem;font-weight:500">
            Multi-agent dispatch planning &nbsp;·&nbsp; Scenario simulation &nbsp;·&nbsp; Audit-loop self-correction
        </p>
    </div>
    """, unsafe_allow_html=True)

    tabs = st.tabs([
        "🏠  Overview",
        "📊  Ops Data",
        "⚡  Scenarios",
        "🛡  Audit",
        "🚀  Full Pipeline",
    ])

    with tabs[0]: render_overview()
    with tabs[1]: render_ops_tab()
    with tabs[2]: render_scenario_tab()
    with tabs[3]: render_audit_tab()
    with tabs[4]: render_full_pipeline_tab()


if __name__ == "__main__":
    main()
