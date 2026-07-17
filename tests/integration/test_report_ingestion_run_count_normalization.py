from __future__ import annotations

from codex_orchestrator.report_ingestion import _normalize_deterministic_run_counts


def test_deterministic_run_counts_accepts_real_codex_object_values():
    report, changed = _normalize_deterministic_run_counts(
        {"deterministic_run_counts": {"baseline": {"phase": "baseline", "runs": 5}}}
    )
    assert changed is True
    assert report["deterministic_run_counts"]["baseline"] == "5/5"
    assert report["deterministic_run_counts_raw"]["baseline"]["runs"] == 5
