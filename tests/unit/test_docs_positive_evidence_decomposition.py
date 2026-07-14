from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _docs_text() -> str:
    paths = [
        ROOT / "README.md",
        ROOT / "IMPLEMENTATION_STATUS.md",
        ROOT / "docs/general_work_decomposition.md",
        ROOT / "docs/general_goal_proof_contract.md",
        ROOT / "docs/workflow_lifecycle.md",
        ROOT / "docs/real_codex_smoke.md",
        ROOT / "docs/runbooks/real_codex_smoke_runbook.md",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths if path.exists()).lower()


def test_docs_require_positive_file_evidence():
    assert "positive planning evidence" in _docs_text()


def test_docs_explain_unmatched_candidates_receive_no_work():
    assert "unmatched candidate" in _docs_text() and "no work" in _docs_text()


def test_docs_preserve_explicit_support_file_targets():
    assert "support files remain targetable" in _docs_text()


def test_docs_explain_one_goal_obligation_probe_per_slice():
    assert "one goal" in _docs_text() and "one proof obligation" in _docs_text() and "one probe" in _docs_text()


def test_docs_explain_multiple_patchlets_may_target_one_file():
    assert "multiple patchlets may target one file" in _docs_text()


def test_docs_explain_unresolved_mapping_safe_failure():
    assert "unresolved" in _docs_text() and "safe" in _docs_text()
