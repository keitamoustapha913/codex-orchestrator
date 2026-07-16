from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("IMPLEMENTATION_STATUS.md"),
    Path("docs/general_work_decomposition.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/goal_progress_and_partial_apply.md"),
    Path("docs/cli.md"),
]


def _combined_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_docs_explain_tracked_peer_changes_are_debris():
    text = _combined_docs()
    assert "tracked peer edits" in text
    assert "sandbox debris" in text


def test_docs_explain_changed_peer_files_are_non_blocking():
    text = _combined_docs().lower()
    assert "sandbox debris never blocks promotion" in text


def test_docs_explain_filename_shape_has_no_authority():
    text = _combined_docs().lower()
    assert "filenames" in text or "name" in text
    assert "cannot make it authoritative" in text or "do not infer authority" in text


def test_docs_explain_canonical_patch_excludes_debris():
    text = _combined_docs().lower()
    assert "excluded from the canonical patch" in text


def test_docs_explain_allowlist_is_only_product_boundary():
    text = _combined_docs().lower()
    assert "deterministic allowlist is the only product boundary" in text
