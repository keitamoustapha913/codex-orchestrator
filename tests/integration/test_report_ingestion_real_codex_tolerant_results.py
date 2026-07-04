from __future__ import annotations

from codex_orchestrator.report_ingestion import _normalize_deterministic_run_counts, normalize_acceptance_criteria_result


def test_acceptance_criteria_result_accepts_plain_pass():
    assert normalize_acceptance_criteria_result("pass")["normalized_status"] == "pass"


def test_acceptance_criteria_result_accepts_pass_colon_description():
    result = normalize_acceptance_criteria_result("pass: changed the requested status setting only")
    assert result["normalized_status"] == "pass"
    assert result["detail"] == "changed the requested status setting only"


def test_acceptance_criteria_result_accepts_fail_colon_description():
    assert normalize_acceptance_criteria_result("fail: probe failed")["normalized_status"] == "fail"


def test_acceptance_criteria_result_accepts_blocked_colon_description():
    assert normalize_acceptance_criteria_result("blocked: missing dependency")["normalized_status"] == "blocked"


def test_acceptance_criteria_result_preserves_raw_value():
    assert normalize_acceptance_criteria_result("PASS: Done")["raw_value"] == "PASS: Done"


def test_acceptance_criteria_result_normalizes_status():
    assert normalize_acceptance_criteria_result("PASS: Done")["normalized_status"] == "pass"


def test_acceptance_criteria_result_rejects_vague_success_without_status_prefix():
    result = normalize_acceptance_criteria_result("looks good")
    assert result["valid"] is False
    assert result["error_code"] == "INVALID_ACCEPTANCE_CRITERIA_RESULT"


def test_deterministic_run_counts_accepts_real_codex_object_values():
    report, changed = _normalize_deterministic_run_counts(
        {"deterministic_run_counts": {"baseline": {"phase": "baseline", "runs": 5}}}
    )
    assert changed is True
    assert report["deterministic_run_counts"]["baseline"] == "5/5"
    assert report["deterministic_run_counts_raw"]["baseline"]["runs"] == 5
