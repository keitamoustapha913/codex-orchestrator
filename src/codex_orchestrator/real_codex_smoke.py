from __future__ import annotations

import os
import shutil
from pathlib import Path

from codex_orchestrator.errors import CxorError, WorkerPreconditionError
from codex_orchestrator.git_guard import snapshot_status
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import TargetRepoContext

from .diagnostics import diagnose_real_codex_attempt
from .stages.build_inventory import build_inventory
from .stages.census import run_census
from .stages.classify_evidence import classify_evidence
from .stages.compile_patchlets import compile_patchlets
from .stages.extract_invariants import extract_invariants
from .stages.init import init_workflow
from .stages.normalize import normalize_master_prompt
from .stages.auto import run_auto
from .stages.run_patchlet import run_next_patchlet
from .run_records import load_run_manifest


def _real_codex_contract_template_path() -> Path:
    return Path(__file__).resolve().parent / "prompt_templates" / "real_codex_patchlet_contract.md"


def real_codex_smoke_enabled(explicit_flag: bool) -> bool:
    return bool(explicit_flag)


def describe_real_codex_auto_worktree_opt_in_command() -> str:
    return (
        "uv run --no-sync pytest -q "
        "tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s"
    )


def ensure_real_codex_smoke_prereqs(
    ctx: TargetRepoContext,
    *,
    codex_binary: str = "codex",
    allow_real_codex: bool = False,
) -> None:
    if not allow_real_codex:
        raise WorkerPreconditionError("real codex smoke requires explicit allow flag")
    if snapshot_status(ctx.root).status:
        raise WorkerPreconditionError(f"clean target repo required: {ctx.root}")
    if shutil.which(codex_binary) is None:
        raise WorkerPreconditionError(f"Codex binary not found: {codex_binary}")


def run_real_codex_smoke(
    ctx: TargetRepoContext,
    *,
    master: str | Path,
    codex_binary: str = "codex",
    allow_real_codex: bool = False,
    inject_contract: bool = True,
) -> dict:
    ensure_real_codex_smoke_prereqs(
        ctx,
        codex_binary=codex_binary,
        allow_real_codex=allow_real_codex,
    )
    init_workflow(ctx, master=master, invocation_argv=["pytest", "--run-real-codex"], mode="manual", until="DONE")
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)

    previous_binary = os.environ.get("CXOR_CODEX_BINARY")
    previous_contract = os.environ.get("CXOR_REAL_CODEX_CONTRACT_PATH")
    os.environ["CXOR_CODEX_BINARY"] = codex_binary
    if inject_contract:
        os.environ["CXOR_REAL_CODEX_CONTRACT_PATH"] = str(_real_codex_contract_template_path())
    else:
        os.environ.pop("CXOR_REAL_CODEX_CONTRACT_PATH", None)
    try:
        result = run_next_patchlet(ctx, worker_mode="real_codex")
    finally:
        if previous_binary is None:
            os.environ.pop("CXOR_CODEX_BINARY", None)
        else:
            os.environ["CXOR_CODEX_BINARY"] = previous_binary
        if previous_contract is None:
            os.environ.pop("CXOR_REAL_CODEX_CONTRACT_PATH", None)
        else:
            os.environ["CXOR_REAL_CODEX_CONTRACT_PATH"] = previous_contract

    state = load_state(ctx)
    run_dir = ctx.paths.runs_dir / f"{result.patchlet_id}_attempt1"
    return {
        "worker_mode": "real_codex",
        "patchlet_id": result.patchlet_id,
        "patchlet_status": result.status,
        "report_valid": result.report_valid,
        "state_stage": state.stage,
        "run_dir": str(run_dir),
        "report_path": str(ctx.paths.reports_dir / f"{result.patchlet_id}.json"),
        "stdout_path": str(run_dir / "stdout.txt"),
        "stderr_path": str(run_dir / "stderr.txt"),
        "command_path": str(run_dir / "command.json"),
        "output_jsonl_path": str(run_dir / "output.jsonl"),
        "diff_path": str(run_dir / "diff.patch"),
    }


def build_real_codex_auto_worktree_smoke_command(
    ctx: TargetRepoContext,
    *,
    master: str | Path,
    until: str = "DONE",
    max_iterations: int = 150,
) -> list[str]:
    return [
        "cxor",
        "auto",
        "--repo",
        str(ctx.root),
        "--master",
        str(Path(master)),
        "--until",
        until,
        "--worker-mode",
        "real_codex",
        "--use-worktree",
        "--max-iterations",
        str(max_iterations),
    ]


def _latest_run_dir(ctx: TargetRepoContext) -> Path | None:
    run_dirs = sorted(
        [path for path in ctx.paths.runs_dir.glob("*") if path.is_dir()],
        key=lambda path: path.name,
    )
    if not run_dirs:
        return None
    return run_dirs[-1]


def _latest_patchlet_run_entry(ctx: TargetRepoContext) -> dict | None:
    manifest = load_run_manifest(ctx)
    patchlet_runs = [run for run in manifest.get("runs", []) if run.get("patchlet_id")]
    if not patchlet_runs:
        return None
    return patchlet_runs[-1]


def _latest_prompt_artifact_path(ctx: TargetRepoContext) -> Path | None:
    run_dir = _latest_run_dir(ctx)
    if run_dir is not None:
        command_path = run_dir / "command.json"
        if command_path.exists():
            from .jsonio import read_json
            command = read_json(command_path)
            recorded_prompt_path = command.get("prompt_path")
            if recorded_prompt_path:
                prompt_path = Path(recorded_prompt_path)
                if prompt_path.exists():
                    return prompt_path
            args = command.get("args", [])
            if args:
                prompt_path = Path(args[-1])
                if prompt_path.exists():
                    return prompt_path
    manifest = load_run_manifest(ctx)
    patchlet_runs = [run for run in manifest.get("runs", []) if run.get("patchlet_id")]
    if not patchlet_runs:
        index_path = ctx.paths.patchlet_index
        if not index_path.exists():
            return None
        from .jsonio import read_json
        index = read_json(index_path)
        patchlets = index.get("patchlets", [])
        if not patchlets:
            return None
        return ctx.root / patchlets[0]["subprompt_path"]
    from .jsonio import read_json
    index = read_json(ctx.paths.patchlet_index) if ctx.paths.patchlet_index.exists() else {"patchlets": []}
    patchlet_id = patchlet_runs[-1].get("patchlet_id")
    for patchlet in index.get("patchlets", []):
        if patchlet.get("patchlet_id") == patchlet_id:
            return ctx.root / patchlet["subprompt_path"]
    return None


def _smoke_result(
    ctx: TargetRepoContext,
    *,
    master: str | Path,
    until: str,
    max_iterations: int,
    outcome: str,
    state_stage: str,
    error_type: str | None = None,
    error_message: str | None = None,
) -> dict:
    run_dir = _latest_run_dir(ctx)
    run_manifest_entry = _latest_patchlet_run_entry(ctx)
    prompt_artifact_path = _latest_prompt_artifact_path(ctx)
    capsule_manifest_path = str(run_dir / "worker_capsule.json") if run_dir is not None else None
    contract_template_path = _real_codex_contract_template_path()
    contract_injected = False
    if prompt_artifact_path is not None and prompt_artifact_path.exists():
        contract_injected = "Real Codex Patchlet Contract" in prompt_artifact_path.read_text(encoding="utf-8")
    result = {
        "worker_mode": "real_codex",
        "use_worktree": True,
        "command": build_real_codex_auto_worktree_smoke_command(
            ctx,
            master=master,
            until=until,
            max_iterations=max_iterations,
        ),
        "outcome": outcome,
        "state_stage": state_stage,
        "error_type": error_type,
        "error_message": error_message,
        "target_repo_root": str(ctx.root),
        "run_manifest_path": str(ctx.paths.run_manifest),
        "prompt_artifact_path": str(prompt_artifact_path) if prompt_artifact_path is not None else None,
        "worker_capsule_manifest_path": capsule_manifest_path,
        "worker_memory_dir": str(run_dir / "worker_memory") if run_dir is not None else None,
        "worker_stage_dir": str(run_dir / "worker_stage") if run_dir is not None else None,
        "wrapper_gate_result_path": str(run_dir / "gates" / "wrapper_gate_result.json") if run_dir is not None else None,
        "contract_template_path": str(contract_template_path),
        "contract_injected": contract_injected,
        "final_verification_path": str(ctx.paths.final_verification_json),
        "reports_dir": str(ctx.paths.reports_dir),
        "probes_dir": str(ctx.paths.probe_dir),
        "runs_dir": str(ctx.paths.runs_dir),
        "run_manifest_entry": run_manifest_entry,
        "run_dir": str(run_dir) if run_dir is not None else None,
        "stdout_path": str(run_dir / "stdout.txt") if run_dir is not None else None,
        "stderr_path": str(run_dir / "stderr.txt") if run_dir is not None else None,
        "command_path": str(run_dir / "command.json") if run_dir is not None else None,
        "output_jsonl_path": str(run_dir / "output.jsonl") if run_dir is not None else None,
        "diff_path": str(run_dir / "diff.patch") if run_dir is not None else None,
    }
    if outcome == "safe_failure" and run_manifest_entry is not None and run_manifest_entry.get("attempt_id"):
        diagnosis = diagnose_real_codex_attempt(
            ctx,
            attempt_id=run_manifest_entry["attempt_id"],
            prompt_artifact_path=prompt_artifact_path,
            outcome=outcome,
        )
        result.update(diagnosis)
    return result


def run_real_codex_auto_worktree_smoke(
    ctx: TargetRepoContext,
    *,
    master: str | Path,
    codex_binary: str = "codex",
    allow_real_codex: bool = False,
    until: str = "DONE",
    max_iterations: int = 150,
    inject_contract: bool = True,
) -> dict:
    ensure_real_codex_smoke_prereqs(
        ctx,
        codex_binary=codex_binary,
        allow_real_codex=allow_real_codex,
    )
    init_workflow(
        ctx,
        master=master,
        invocation_argv=["pytest", "--run-real-codex"],
        mode="manual",
        until="DONE",
    )

    previous_binary = os.environ.get("CXOR_CODEX_BINARY")
    previous_contract = os.environ.get("CXOR_REAL_CODEX_CONTRACT_PATH")
    os.environ["CXOR_CODEX_BINARY"] = codex_binary
    if inject_contract:
        os.environ["CXOR_REAL_CODEX_CONTRACT_PATH"] = str(_real_codex_contract_template_path())
    else:
        os.environ.pop("CXOR_REAL_CODEX_CONTRACT_PATH", None)
    try:
        try:
            state = run_auto(
                ctx,
                master=master,
                resume=True,
                until=until,
                worker_mode="real_codex",
                use_worktree=True,
                max_iterations=max_iterations,
            )
        except (CxorError, RuntimeError, FileNotFoundError) as exc:
            state = load_state(ctx)
            return _smoke_result(
                ctx,
                master=master,
                until=until,
                max_iterations=max_iterations,
                outcome="safe_failure",
                state_stage=state.stage,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
    finally:
        if previous_binary is None:
            os.environ.pop("CXOR_CODEX_BINARY", None)
        else:
            os.environ["CXOR_CODEX_BINARY"] = previous_binary
        if previous_contract is None:
            os.environ.pop("CXOR_REAL_CODEX_CONTRACT_PATH", None)
        else:
            os.environ["CXOR_REAL_CODEX_CONTRACT_PATH"] = previous_contract

    return _smoke_result(
        ctx,
        master=master,
        until=until,
        max_iterations=max_iterations,
        outcome="success",
        state_stage=state.stage,
    )
