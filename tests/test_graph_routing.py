from graph import route_after_audit


def test_route_after_failed_audit_returns_planner_before_retry_limit():
    state = {
        "audit_result": {"audit_status": "fail"},
        "audit_retry_count": 1,
    }

    assert route_after_audit(state) == "planner"


def test_route_after_failed_audit_returns_report_at_retry_limit():
    state = {
        "audit_result": {"audit_status": "fail"},
        "audit_retry_count": 2,
    }

    assert route_after_audit(state) == "report"


def test_route_after_passed_audit_returns_report():
    state = {
        "audit_result": {"audit_status": "pass"},
        "audit_retry_count": 0,
    }

    assert route_after_audit(state) == "report"
