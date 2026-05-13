"""
test_ops_data_agent.py — Smoke tests for the enhanced OpsDataAgent (Direction #3).

Verifies:
  1. Function returns the contract-required output schema
  2. Real CSV (no dates) → cross_sectional mode + 1 high-confidence substitution match
  3. Augmented CSV (8 weeks, if present) → period_over_period mode + PoP deltas

Run from repo root:
    PYTHONPATH=src python -m pytest tests/test_ops_data_agent.py -v
"""
import json
import os
import sys
import types
from pathlib import Path

# pytest collects this file from tests/ — make src/ importable
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Stub the LLM so tests don't burn API budget. The agent's _llm_synthesis()
# wraps the call in try/except RuntimeError for budget exhaustion — we trigger
# that path so the deterministic analysis still runs and returns a valid result.
if "agents" not in sys.modules:
    fake_agents = types.ModuleType("agents")
    fake_agents.get_llm = lambda: None
    def _check_budget(): raise RuntimeError("LLM disabled for test")
    fake_agents._check_call_budget = _check_budget
    sys.modules["agents"] = fake_agents

import ops_data_agent as agent

REAL_CSV = REPO_ROOT / "data" / "Incoming_shipment_03_06.csv"
AUG_CSV = REPO_ROOT / "data" / "augmented_ops_data.csv"

REQUIRED_KEYS = {
    "agent_name", "status", "summary", "trend_analysis",
    "data_quality_issues", "item_master_matches", "constraints",
    "recommendations", "data",
}


def test_function_signature_returns_dict_with_ops_data_result():
    """Contract: run_ops_data_agent(state: dict) -> dict with 'ops_data_result' key."""
    result = agent.run_ops_data_agent({"csv_path": str(REAL_CSV), "business_context": ""})
    assert isinstance(result, dict)
    assert "ops_data_result" in result


def test_real_csv_returns_contract_schema():
    """All 9 required keys present in the ops_data_result dict."""
    result = agent.run_ops_data_agent({"csv_path": str(REAL_CSV), "business_context": ""})
    opa = result["ops_data_result"]
    missing = REQUIRED_KEYS - set(opa.keys())
    assert not missing, f"Missing contract keys: {missing}"
    assert opa["agent_name"] == "OpsDataAgent"


def test_real_csv_cross_sectional_mode():
    """Real CSV has no dates → analysis_mode should be cross_sectional."""
    result = agent.run_ops_data_agent({"csv_path": str(REAL_CSV), "business_context": ""})
    opa = result["ops_data_result"]
    assert opa["data"]["analysis_metadata"]["analysis_mode"] == "cross_sectional"
    assert opa["data"]["analysis_metadata"]["has_date_column"] is False


def test_item_master_substitution_finds_10071_match():
    """Enhancement A: item_id 10071 should match to 10070 with high confidence."""
    result = agent.run_ops_data_agent({"csv_path": str(REAL_CSV), "business_context": ""})
    opa = result["ops_data_result"]
    matches = opa["item_master_matches"]
    assert len(matches) >= 1, "Expected at least one Item Master match for the real CSV"

    match_10071 = next((m for m in matches if m["missing_identifier"] == "10071"), None)
    assert match_10071 is not None, "item_id 10071 should be flagged as missing"
    assert match_10071["matched_item_id"] == 10070, (
        f"Expected 10071 to match 10070, got {match_10071['matched_item_id']}"
    )
    assert match_10071["confidence_band"] == "HIGH"
    assert match_10071["confidence"] >= 0.85


def test_playbook_grounded_dosage_classification():
    """Enhancement C: Remdesivir 100/200mg dosage variance → MEDIUM (not HIGH)."""
    result = agent.run_ops_data_agent({"csv_path": str(REAL_CSV), "business_context": ""})
    opa = result["ops_data_result"]
    dq_issues = opa["data_quality_issues"]

    remdesivir_issue = next(
        (i for i in dq_issues if "10021" in str(i.get("issue", ""))),
        None,
    )
    assert remdesivir_issue is not None, "Expected a DQ issue for item_id 10021"
    assert remdesivir_issue["severity"] == "medium", (
        f"Playbook §8 lists both Remdesivir 100mg and 200mg as valid for item_id 10021. "
        f"This is dosage ambiguity (MEDIUM), not a real mismatch (HIGH). "
        f"Got severity={remdesivir_issue['severity']!r}"
    )


def test_constraints_have_audit_trigger_phrases():
    """Constraint rule text must contain phrases the audit agent scans for."""
    result = agent.run_ops_data_agent({"csv_path": str(REAL_CSV), "business_context": ""})
    constraints = result["ops_data_result"]["constraints"]
    rules = " ".join(c["rule"].lower() for c in constraints)
    assert "must acknowledge material data quality issues" in rules
    assert "planner must explain the dispatch impact" in rules


def test_status_is_valid():
    """Status must be one of the contract-allowed values."""
    result = agent.run_ops_data_agent({"csv_path": str(REAL_CSV), "business_context": ""})
    status = result["ops_data_result"]["status"]
    assert status in {"success", "warning", "failed"}


# ── Period-over-Period tests (skipped if augmented CSV isn't present) ────────

import pytest


@pytest.mark.skipif(
    not AUG_CSV.exists(),
    reason="data/augmented_ops_data.csv not present in repo (PoP demo data)"
)
def test_augmented_csv_pop_mode():
    """Enhancement B: augmented CSV with delivery_date + KPIs → period_over_period mode."""
    result = agent.run_ops_data_agent({"csv_path": str(AUG_CSV), "business_context": ""})
    opa = result["ops_data_result"]
    assert opa["data"]["analysis_metadata"]["analysis_mode"] == "period_over_period"

    pop = opa["trend_analysis"].get("pop_metrics")
    assert pop is not None, "Expected pop_metrics section in trend_analysis"
    assert pop["status"] == "computed"
    assert len(pop["periods_available"]) >= 2, "Expected at least 2 periods"
    assert "deltas" in pop
    assert "otdr_pct_change" in pop["deltas"]


# ── Manual run (when invoked directly, not via pytest) ───────────────────────

if __name__ == "__main__":
    print(f"Repo root : {REPO_ROOT}")
    print(f"Real CSV  : {REAL_CSV}  (exists: {REAL_CSV.exists()})")
    print(f"Aug CSV   : {AUG_CSV}  (exists: {AUG_CSV.exists()})")
    print()

    state = {"csv_path": str(REAL_CSV), "business_context": ""}
    r = agent.run_ops_data_agent(state)
    opa = r["ops_data_result"]
    print(f"Status     : {opa['status']}")
    print(f"Summary    : {opa['summary']}")
    print(f"DQ issues  : {len(opa['data_quality_issues'])}")
    print(f"IM matches : {len(opa['item_master_matches'])}")
    for m in opa["item_master_matches"]:
        print(f"  • {m['missing_identifier']} → {m['matched_item_id']} "
              f"(confidence {m['confidence']}, {m['confidence_band']})")
