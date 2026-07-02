from __future__ import annotations

from pathlib import Path


def _docs_text() -> str:
    repo = Path(__file__).resolve().parents[2]
    paths = [
        repo / "README.md",
        repo / "IMPLEMENTATION_STATUS.md",
        repo / "docs" / "cli.md",
        repo / "docs" / "autonomous_loop.md",
        repo / "docs" / "root_cause_patchlets.md",
        repo / "docs" / "transaction_groups.md",
        repo / "docs" / "worktrees.md",
        repo / "docs" / "real_codex_smoke.md",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths if path.exists())


def test_docs_explain_worker_capsule_per_attempt_memory():
    text = _docs_text().lower()
    assert "worker capsule" in text
    assert "per-attempt" in text


def test_docs_explain_memory_is_context_not_proof():
    text = _docs_text().lower()
    assert "memory is context, not proof" in text


def test_docs_explain_orchestrator_owns_gate_results():
    text = _docs_text().lower()
    assert "orchestrator writes gate results" in text or "orchestrator owns gate results" in text


def test_docs_explain_transaction_and_global_matrices():
    text = _docs_text().lower()
    assert "patchlet_output_matrix.json" in text
    assert "verification_matrix.json" in text
    assert "global_gate_result.json" in text


def test_docs_explain_worker_capsule_path_violation():
    text = _docs_text()

    assert "worker_capsule_path_violation" in text
    assert "Codex path-obedience issue" in text


def test_docs_explain_do_not_create_target_root_worker_stage():
    text = _docs_text()

    assert "Do not create target-root worker_stage/" in text


def test_docs_explain_worker_stage_dir_env_var():
    text = _docs_text()

    assert "CXOR_WORKER_STAGE_DIR" in text
