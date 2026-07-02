from __future__ import annotations

import shutil
from pathlib import Path

from codex_orchestrator.config import write_default_target_config
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.run_records import init_run_manifest
from codex_orchestrator.state import new_state, save_state, sha256_file
from codex_orchestrator.target_repo import TargetRepoContext


def _mkdirs(ctx: TargetRepoContext) -> None:
    for path in [
        ctx.paths.workflow_dir,
        ctx.paths.census_dir,
        ctx.paths.patchlets_dir,
        ctx.paths.subprompts_dir,
        ctx.paths.reports_dir,
        ctx.paths.runs_dir,
        ctx.paths.failures_dir,
        ctx.paths.repair_plans_dir,
        ctx.paths.verifier_dir,
        ctx.paths.probe_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def init_workflow(
    ctx: TargetRepoContext,
    *,
    master: str | Path | None = None,
    invocation_argv: list[str] | None = None,
    mode: str = "manual",
    until: str = "DONE",
):
    _mkdirs(ctx)
    (ctx.paths.probe_dir / ".gitkeep").touch()
    readme = ctx.paths.workflow_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Codex Orchestrator Workflow Artifacts\n\n"
            "This directory contains durable target-repository workflow artifacts.\n"
            "The installed cxor CLI owns orchestration code; no source is copied here.\n",
            encoding="utf-8",
        )
    write_default_target_config(ctx.paths.config)

    state_stage = "INITIALIZED"
    if master is not None:
        master_path = Path(master).expanduser().resolve()
        if not master_path.exists():
            raise FileNotFoundError(f"Master prompt does not exist: {master_path}")
        shutil.copyfile(master_path, ctx.paths.master_prompt)
        state_stage = "MASTER_PROMPT_SAVED"

    if not ctx.paths.run_manifest.exists():
        init_run_manifest(ctx, invocation_argv=invocation_argv)

    if not ctx.paths.state.exists():
        state = new_state(ctx, stage=state_stage, mode=mode, until=until)
        state.master_prompt_sha256 = sha256_file(ctx.paths.master_prompt)
        save_state(ctx, state)
    else:
        from codex_orchestrator.state import load_state, transition

        state = load_state(ctx)
        if master is not None:
            state.master_prompt_sha256 = sha256_file(ctx.paths.master_prompt)
            transition(ctx, state, "MASTER_PROMPT_SAVED", reason="master prompt saved")
            state = load_state(ctx)

    # Seed empty manifests that later stages can overwrite.
    for path, data in [
        (ctx.paths.patchlet_index, {"schema_version": "1.0", "kind": "patchlet_index", "patchlets": []}),
        (ctx.paths.transaction_groups, {"schema_version": "1.0", "kind": "transaction_groups", "transaction_groups": []}),
    ]:
        if not path.exists():
            write_json(path, data)
    return state
