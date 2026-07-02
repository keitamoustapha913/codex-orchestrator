from __future__ import annotations

from pathlib import Path


def _docs_text() -> str:
    repo = Path(__file__).resolve().parents[2]
    paths = [
        repo / "README.md",
        repo / "IMPLEMENTATION_STATUS.md",
        repo / "docs" / "cli.md",
        repo / "docs" / "installation.md",
        repo / "docs" / "autonomous_loop.md",
        repo / "docs" / "root_cause_patchlets.md",
        repo / "docs" / "transaction_groups.md",
        repo / "docs" / "rediscovery.md",
        repo / "docs" / "worktrees.md",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths if path.exists())


def test_docs_cover_uv_python_310_contract():
    text = _docs_text()
    assert "uv + Python 3.10" in text


def test_docs_cover_autonomous_until_done_contract():
    text = _docs_text()
    assert "cxor auto" in text
    assert "--until DONE" in text
    assert "--repo" in text


def test_docs_cover_no_blind_retry_and_root_cause_probe_gate():
    text = _docs_text()
    assert "No blind retry" in text
    assert "ROOT-CAUSE PROBE-ONLY INVESTIGATION" in text


def test_docs_cover_durable_probe_artifacts_and_probe_refs():
    text = _docs_text()
    assert "durable probe artifacts" in text
    assert "probe_artifact_refs" in text


def test_docs_cover_transaction_groups_and_global_verifier():
    text = _docs_text()
    assert "transaction group" in text.lower()
    assert "verify-global" in text or "global verifier" in text.lower()


def test_docs_cover_repair_classifications_and_rediscovery():
    text = _docs_text()
    assert "OUTSIDE_KNOWN_GRAPH" in text
    assert "rediscover" in text
    assert "rebuild-inventory" in text


def test_docs_cover_worktree_isolation_and_validated_merge():
    text = _docs_text()
    assert "worktree" in text.lower()
    assert "validated merge" in text.lower()
    assert "--use-worktree" in text


def test_docs_cover_ci_friendly_commands_that_exist():
    text = _docs_text()
    assert "cxor doctor --repo" in text
    assert "cxor validate-state --repo" in text
    assert "cxor verify-global --repo" in text
    assert "cxor auto --repo" in text
    assert "--worker-mode ci_only" in text


def test_docs_do_not_claim_worktrees_are_default():
    text = _docs_text().lower()
    assert "worktrees are default" not in text
    assert "worktree mode is optional" in text or "use-worktree" in text
