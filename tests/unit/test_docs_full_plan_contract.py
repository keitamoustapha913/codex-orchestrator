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


def test_docs_cover_auto_use_worktree_command():
    text = _docs_text()
    assert "cxor auto --repo" in text
    assert "--use-worktree" in text


def test_docs_state_worktrees_are_optional_not_default_for_auto():
    text = _docs_text().lower()
    assert "auto --use-worktree" in text
    assert "optional" in text
    assert "not default" in text or "not the default" in text


def test_docs_cover_auto_worktree_clean_repo_precondition():
    text = _docs_text().lower()
    assert "clean target repo" in text
    assert "auto --use-worktree" in text


def test_docs_cover_auto_worktree_unauthorized_diff_isolation():
    text = _docs_text().lower()
    assert "unauthorized" in text
    assert "do not mutate target product/runtime files" in text or "does not mutate target product/runtime files" in text


def test_docs_cover_ci_only_read_only_with_auto():
    text = _docs_text().lower()
    assert "ci_only" in text
    assert "read-only" in text


def test_docs_cover_real_codex_auto_worktree_smoke_opt_in():
    text = _docs_text()
    assert "real_codex" in text
    assert "--run-real-codex" in text
    assert "cxor auto --repo" in text
    assert "--use-worktree" in text


def test_docs_warn_real_codex_smoke_is_not_default_suite():
    text = _docs_text().lower()
    assert "not part of the default test suite" in text or "default suite does not run real codex" in text
    assert "opt-in" in text


def test_docs_warn_not_to_weaken_validators_for_real_codex():
    text = _docs_text().lower()
    assert "do not weaken validators" in text
    assert "real codex" in text


def test_docs_explain_real_codex_smoke_artifact_inspection():
    text = _docs_text()
    assert ".codex-orchestrator/runs/" in text
    assert ".codex-orchestrator/failures/" in text
    assert ".artifacts/probes/" in text


def test_docs_explain_real_codex_safe_failure_run_manifest_entry():
    text = _docs_text()
    assert "run_manifest.json" in text
    assert "WORKER_FAILED" in text
    assert "blind retry is not allowed" in text.lower()


def test_docs_explain_real_codex_failed_attempt_artifact_paths():
    text = _docs_text()
    assert "stdout.txt" in text
    assert "stderr.txt" in text
    assert "command.json" in text
    assert "output.jsonl" in text
