from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("IMPLEMENTATION_STATUS.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/general_goal_proof_contract.md"),
    Path("docs/semantic_goal_satisfaction.md"),
]


def _docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_docs_explain_object_probe_artifact_refs_canonicalized():
    text = _docs_text()
    assert "object-shaped `probe_artifact_refs`" in text
    assert "canonicalized from actual artifact files" in text


def test_docs_explain_worker_hash_not_trusted():
    text = _docs_text()
    assert "worker-provided hashes are not trusted" in text


def test_docs_explain_raw_worker_metadata_preserved():
    text = _docs_text()
    assert "raw worker metadata is preserved for audit" in text


def test_docs_explain_unsafe_paths_rejected():
    text = _docs_text()
    assert "unsafe paths" in text
    assert "missing files" in text
    assert "product files remain rejected" in text


def test_docs_explain_patchlet_mismatch_rejected():
    text = _docs_text()
    assert "patchlet mismatches" in text
    assert "remain rejected" in text
