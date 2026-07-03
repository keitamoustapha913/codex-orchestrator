from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _combined_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS if path.exists())


def test_docs_explain_list_real_codex_smoke_runbooks_command():
    assert "cxor list-real-codex-smoke-runbooks" in _combined_docs()


def test_docs_explain_list_command_flags():
    text = _combined_docs()

    assert "--root" in text
    assert "--json" in text
    assert "--latest" in text
    assert "--only-invalid" in text
    assert "--limit" in text


def test_docs_explain_list_command_is_read_only():
    assert "read-only" in _combined_docs()


def test_docs_explain_list_command_does_not_run_codex_or_pytest():
    text = _combined_docs()

    assert "does not run Codex" in text
    assert "does not run pytest" in text


def test_docs_explain_invalid_bundles_are_listed():
    assert "invalid bundles are listed" in _combined_docs()


def test_docs_explain_validate_single_bundle_followup():
    assert "cxor validate-real-codex-smoke-runbook --run-dir" in _combined_docs()
