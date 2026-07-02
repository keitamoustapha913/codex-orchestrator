from __future__ import annotations

import os
import shutil
from pathlib import Path

from codex_orchestrator.errors import WorkerPreconditionError
from codex_orchestrator.git_guard import snapshot_status
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import TargetRepoContext

from .stages.build_inventory import build_inventory
from .stages.census import run_census
from .stages.classify_evidence import classify_evidence
from .stages.compile_patchlets import compile_patchlets
from .stages.extract_invariants import extract_invariants
from .stages.init import init_workflow
from .stages.normalize import normalize_master_prompt
from .stages.run_patchlet import run_next_patchlet


def real_codex_smoke_enabled(explicit_flag: bool) -> bool:
    return bool(explicit_flag)


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
    os.environ["CXOR_CODEX_BINARY"] = codex_binary
    try:
        result = run_next_patchlet(ctx, worker_mode="real_codex")
    finally:
        if previous_binary is None:
            os.environ.pop("CXOR_CODEX_BINARY", None)
        else:
            os.environ["CXOR_CODEX_BINARY"] = previous_binary

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
