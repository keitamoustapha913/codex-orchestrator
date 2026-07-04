from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("IMPLEMENTATION_STATUS.md"),
    Path("docs/general_work_decomposition.md"),
    Path("docs/multi_patchlet_transaction_graph.md"),
    Path("docs/general_goal_proof_contract.md"),
    Path("docs/goal_progress_and_partial_apply.md"),
    Path("docs/autonomous_loop.md"),
    Path("docs/cli.md"),
    Path("docs/release.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
]


def _text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_docs_explain_one_file_not_sufficient():
    assert "one allowed file per patchlet is necessary but not sufficient" in _text()


def test_docs_explain_slice_level_change_boundary():
    assert "slice-level allowed-change boundary" in _text()


def test_docs_explain_future_slice_changes_rejected():
    assert "future slice changes are rejected" in _text()


def test_docs_explain_patchlet_scoped_proof():
    assert "patchlet-scoped proof" in _text()


def test_docs_explain_partial_blocks_done():
    assert "PARTIAL progress accepts patchlet progress but blocks DONE" in _text()


def test_docs_explain_report_ingestion_pass_prefix():
    assert "pass: / fail: / blocked:" in _text()


def test_docs_explain_artifact_directory_guard():
    assert "artifact directories are allowed only under approved roots" in _text()
