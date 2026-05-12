from pathlib import Path


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
