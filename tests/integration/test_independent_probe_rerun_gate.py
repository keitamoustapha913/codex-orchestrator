from __future__ import annotations

from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.independent_probe_rerun import run_independent_probe_rerun_gate
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path, value: str = "me"):
    (git_repo / "app.py").write_text(f"def main():\n    return {value!r}\n", encoding="utf-8")
    (git_repo / "master_prompt.md").write_text("Make app return me and prove it.\n", encoding="utf-8")
    run(["git", "add", "app.py", "master_prompt.md"], git_repo)
    run(["git", "commit", "-m", "setup"], git_repo)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(ctx, build_workflow_identity(ctx, master=git_repo / "master_prompt.md", worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001"))
    normalize_master_prompt(ctx)
    return ctx


def _run_gate(ctx):
    return run_independent_probe_rerun_gate(
        repo_root=ctx.root,
        workflow_root=ctx.paths.workflow_dir,
        attempt_id="P0001_attempt1",
        patchlet_id="P0001",
        proof_obligations=read_json(ctx.paths.workflow_dir / "proof_obligations.json"),
        probe_plan=read_json(ctx.paths.workflow_dir / "probe_plan.json"),
        integration_ref=None,
        execution_root=ctx.root,
    )


def test_worker_proof_alone_does_not_prove_obligation(git_repo: Path):
    ctx = _ctx(git_repo, "ok")
    obligations = read_json(ctx.paths.workflow_dir / "proof_obligations.json")
    obligations["obligations"][0]["status"] = "PROVEN_BY_WORKER"
    assert _run_gate(ctx)["accepted"] is False


def test_orchestrator_rerun_proves_obligation(git_repo: Path):
    ctx = _ctx(git_repo)
    assert _run_gate(ctx)["accepted"] is True


def test_rerun_expected_actual_mismatch_fails(git_repo: Path):
    ctx = _ctx(git_repo, "ok")
    assert _run_gate(ctx)["accepted"] is False


def test_rerun_records_expected_and_actual(git_repo: Path):
    ctx = _ctx(git_repo, "ok")
    row = _run_gate(ctx)["probe_results"][0]
    assert row["expected_actual"] == {"expected": "me", "actual": "ok"}


def test_rerun_stdout_stderr_are_persisted(git_repo: Path):
    ctx = _ctx(git_repo)
    row = _run_gate(ctx)["probe_results"][0]
    assert (ctx.root / row["stdout_path"]).exists()
    assert (ctx.root / row["stderr_path"]).exists()


def test_rerun_result_schema_validates(git_repo: Path):
    ctx = _ctx(git_repo)
    assert validate_json(_run_gate(ctx), "independent_probe_rerun_result.schema.json") == []


def test_rerun_does_not_create_pycache(git_repo: Path):
    ctx = _ctx(git_repo)
    _run_gate(ctx)
    assert not list(ctx.root.glob("**/__pycache__"))


def test_failed_rerun_creates_failure_signature_independent_probe_rerun_failed(git_repo: Path):
    ctx = _ctx(git_repo, "ok")
    assert _run_gate(ctx)["failure_signature"] == "independent_probe_rerun_failed"


def test_probe_not_rerunnable_blocks_required_obligation(git_repo: Path):
    ctx = _ctx(git_repo)
    plan = read_json(ctx.paths.workflow_dir / "probe_plan.json")
    plan["probes"][0]["rerunnable_by_orchestrator"] = False
    result = run_independent_probe_rerun_gate(repo_root=ctx.root, workflow_root=ctx.paths.workflow_dir, attempt_id="P0001_attempt1", patchlet_id="P0001", proof_obligations=read_json(ctx.paths.workflow_dir / "proof_obligations.json"), probe_plan=plan, integration_ref=None, execution_root=ctx.root)
    assert result["failure_signature"] == "probe_not_rerunnable"


def test_app_main_semantic_runner_integrates_as_independent_probe(git_repo: Path):
    ctx = _ctx(git_repo)
    assert _run_gate(ctx)["probe_results"][0]["command"].startswith("PYTHONDONTWRITEBYTECODE=1")
