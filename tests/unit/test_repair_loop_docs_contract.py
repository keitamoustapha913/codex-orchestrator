from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_docs_mention_repair_application_and_patchlet_regeneration() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    cli_docs = (REPO_ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    installation = (REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8")

    combined = "\n".join([readme, cli_docs, installation])
    combined_lower = combined.lower()

    assert "cxor apply-repair" in combined
    assert "cxor regenerate-patchlets" in combined
    assert "failure -> classification -> repair plan -> apply repair -> regenerate patchlets -> verify" in combined_lower
    assert "no blind retry" in combined_lower
    assert "uv + python 3.10" in combined_lower


def test_docs_mention_idempotent_repair_resume() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    cli_docs = (REPO_ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    status = (REPO_ROOT / "IMPLEMENTATION_STATUS.md").read_text(encoding="utf-8")

    combined = "\n".join([readme, cli_docs, status]).lower()

    assert "idempotent" in combined
    assert "cxor auto --resume" in combined
    assert "cxor apply-repair" in combined
    assert "cxor regenerate-patchlets" in combined
    assert "no blind retry" in combined


def test_docs_mention_terminal_done_repair_commands_are_noop() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    cli_docs = (REPO_ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    status = (REPO_ROOT / "IMPLEMENTATION_STATUS.md").read_text(encoding="utf-8")

    combined = "\n".join([readme, cli_docs, status]).lower()

    assert "done" in combined
    assert "apply-repair" in combined
    assert "regenerate-patchlets" in combined
    assert "no-op" in combined
    assert "terminal" in combined
    assert "no blind retry" in combined
