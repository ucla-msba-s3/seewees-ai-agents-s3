from pathlib import Path

from playbook_rules import extract_playbook_constraints


def test_graph_builds_without_api_calls():
    from graph import build_graph

    app = build_graph()

    assert app is not None


def test_env_example_documents_required_runtime_settings():
    text = Path(".env.example").read_text(encoding="utf-8")

    required_keys = [
        "LLM_PROVIDER",
        "LLM_MODEL",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
        "GEMINI_FREE_TIER_ONLY",
        "LLM_MAX_CALLS_PER_RUN",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
    ]

    for key in required_keys:
        assert key in text


def test_project_methodology_doc_exists():
    doc = Path("docs/project_background.md")

    assert doc.exists()
    assert "Missing Link" in doc.read_text(encoding="utf-8")


def test_audit_demo_case_exists():
    case = Path("examples/audit_fail_case.json")

    assert case.exists()


def test_scenario_input_example_exists():
    case = Path("examples/scenario_input.json")

    assert case.exists()


def test_ops_data_agent_sample_output_exists():
    case = Path("examples/ops_data_agent_sample_output.json")

    assert case.exists()


def test_ops_data_agent_pop_sample_output_exists():
    case = Path("examples/ops_data_agent_sample_output_pop.json")

    assert case.exists()


def test_playbook_constraints_extract_buffer_and_escalation_rules():
    snippets = """
    Travel Time Buffer Policy:
    risk_score 0 -> 0% buffer
    risk_score 1 -> 10% buffer
    risk_score 2 -> 25% buffer
    risk_score 3 -> 40% buffer + escalation
    """

    constraints = extract_playbook_constraints(snippets)
    rule_types = [constraint["rule_type"] for constraint in constraints]
    buffer_rule = next(c for c in constraints if c["rule_type"] == "weather_buffer_policy")

    assert "weather_escalation_policy" in rule_types
    assert buffer_rule["parameters"]["buffer_pct_by_risk_score"][2] == 25
