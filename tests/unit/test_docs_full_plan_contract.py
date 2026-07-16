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
        repo / "docs" / "real_codex_smoke.md",
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


def test_docs_state_write_capable_workers_always_use_disposable_sandboxes():
    text = _docs_text().lower()
    assert "every write-capable worker" in text
    assert "disposable sandbox" in text


def test_docs_cover_auto_use_worktree_command():
    text = _docs_text()
    assert "cxor auto --repo" in text
    assert "--use-worktree" in text


def test_docs_state_auto_worker_flag_cannot_select_direct_execution():
    text = _docs_text().lower()
    assert "auto --use-worktree" in text
    assert "direct execution" in text
    assert "cannot" in text


def test_docs_cover_auto_worktree_clean_repo_precondition():
    text = _docs_text().lower()
    assert "clean target repo" in text
    assert "auto --use-worktree" in text


def test_docs_cover_auto_worktree_non_allowlisted_debris_isolation():
    text = _docs_text().lower()
    assert "sandbox debris" in text
    assert "canonical patch" in text


def _allowlist_boundary_docs_text() -> str:
    repo = Path(__file__).resolve().parents[2]
    paths = [
        repo / "README.md",
        repo / "IMPLEMENTATION_STATUS.md",
        repo / "docs" / "general_work_decomposition.md",
        repo / "docs" / "workflow_lifecycle.md",
        repo / "docs" / "real_codex_smoke.md",
        repo / "docs" / "runbooks" / "real_codex_smoke_runbook.md",
        repo / "docs" / "report_contract.md",
        repo / "docs" / "semantic_goal_satisfaction.md",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths).lower()


def test_docs_define_allowlist_as_only_product_boundary():
    text = _allowlist_boundary_docs_text()
    assert "deterministic allowlist is the only product boundary" in text


def test_docs_define_all_non_allowlisted_sandbox_paths_as_debris():
    text = _allowlist_boundary_docs_text()
    assert "all in-sandbox non-allowlisted outputs are sandbox debris" in text


def test_docs_state_debris_is_non_blocking():
    text = _allowlist_boundary_docs_text()
    assert "sandbox debris never blocks promotion" in text


def test_docs_state_containment_escape_remains_blocking():
    text = _allowlist_boundary_docs_text()
    assert "containment escape remains blocking" in text


def test_docs_contain_no_legacy_evidence_migration_contract():
    text = _allowlist_boundary_docs_text()
    assert "legacy evidence is migrated" not in text
    assert "legacy evidence migration" not in text


def test_docs_contain_no_root_scratch_compatibility_contract():
    text = _allowlist_boundary_docs_text()
    assert "root scratch sweep" not in text
    assert "role-shaped" not in text


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


def test_docs_explain_fake_success_parity_for_real_codex_path():
    text = _docs_text().lower()
    assert "fake-success parity" in text
    assert "worker_mode real_codex" in text or "worker_mode=real_codex" in text
    assert "auto --use-worktree" in text


def test_docs_explain_real_codex_success_depends_on_valid_report_and_probe_output():
    text = _docs_text().lower()
    assert "valid report" in text
    assert "durable probe artifacts" in text
    assert "real codex success to done is not guaranteed" in text
    assert "do not weaken validators" in text


def test_docs_link_real_codex_failure_to_run_manifest_evidence():
    text = _docs_text()
    assert "run_manifest.json" in text
    assert "WORKER_FAILED" in text


def test_docs_reference_real_codex_patchlet_contract_prompt():
    text = _docs_text()
    assert "real_codex_patchlet_contract.md" in text


def test_docs_explain_real_codex_contract_is_injected_into_smoke_prompt():
    text = _docs_text().lower()
    assert "real_codex_patchlet_contract.md" in text
    assert "contract injected" in text or "injected into the smoke prompt" in text


def test_docs_explain_real_codex_contract_contains_minimal_valid_payload_example():
    text = _docs_text().lower()
    assert "minimal valid report" in text
    assert "cxor_report_path" in text
    assert "cxor_probe_root" in text


def test_docs_explain_how_to_inspect_generated_prompt_artifact():
    text = _docs_text().lower()
    assert "generated prompt artifact" in text or "generated subprompt artifact" in text
    assert ".codex-orchestrator/subprompts/" in text


def test_docs_explain_real_success_still_depends_on_codex_obeying_contract():
    text = _docs_text().lower()
    assert "real success is not guaranteed" in text or "real codex success to done is not guaranteed" in text
    assert "do not weaken validators" in text
    assert "contract" in text


def test_docs_explain_real_codex_failure_diagnosis_artifacts():
    text = _docs_text()
    assert "real_codex_failure_diagnosis.json" in text
    assert "real_codex_failure_diagnosis.md" in text
    assert "stdout.txt" in text
    assert "stderr.txt" in text
    assert "output.jsonl" in text
    assert "command.json" in text
    assert "run_manifest.json" in text


def test_docs_explain_diagnose_real_codex_command():
    text = _docs_text()
    assert "diagnose-real-codex" in text
    assert "--attempt" in text


def test_docs_explain_diagnosis_does_not_weaken_validators():
    text = _docs_text().lower()
    assert "do not weaken validators" in text
    assert "diagnose-real-codex" in text


def test_docs_explain_unknown_category_when_artifacts_are_insufficient():
    text = _docs_text()
    assert "unknown_codex_nonzero_exit" in text
