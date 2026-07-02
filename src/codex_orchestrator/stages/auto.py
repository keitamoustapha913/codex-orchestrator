from __future__ import annotations

from pathlib import Path

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.locks import workflow_lock
from codex_orchestrator.state import WorkflowState, load_state
from codex_orchestrator.target_repo import TargetRepoContext

from .apply_repair import apply_repair
from .build_inventory import build_inventory
from .census import run_census
from .classify_evidence import classify_evidence
from .classify_failures import classify_failures
from .compile_patchlets import compile_patchlets
from .extract_invariants import extract_invariants
from .init import init_workflow
from .normalize import normalize_master_prompt
from .plan_repair import plan_repair
from .rebuild_inventory import rebuild_inventory
from .rediscover import rediscover
from .regenerate_patchlets import regenerate_patchlets
from .run_patchlet import run_all_patchlets
from .verify_global import verify_global


def _state_or_none(ctx: TargetRepoContext) -> WorkflowState | None:
    if not ctx.paths.state.exists():
        return None
    return load_state(ctx)


def run_auto(
    ctx: TargetRepoContext,
    *,
    master: str | Path | None = None,
    resume: bool = False,
    until: str = "DONE",
    worker_mode: str = "mock",
    max_iterations: int = 100,
    use_lock: bool = False,
) -> WorkflowState:
    def _run() -> WorkflowState:
        state = _state_or_none(ctx)
        if state is None:
            if resume:
                raise FileNotFoundError(f"Cannot resume; missing state file: {ctx.paths.state}")
            state = init_workflow(ctx, master=master, invocation_argv=["cxor", "auto"], mode="auto", until=until)
        elif master is not None and not ctx.paths.master_prompt.exists():
            state = init_workflow(ctx, master=master, invocation_argv=["cxor", "auto"], mode="auto", until=until)

        state = load_state(ctx)
        if worker_mode == "ci_only":
            if state.stage == until:
                return state
            raise StagePreconditionError(
                "auto",
                current_stage=state.stage,
                target_repo=str(ctx.root),
                detail=(
                    "ci_only worker is read-only and can only resume a workflow "
                    f"already at the requested stage {until}"
                ),
            )

        for _ in range(max_iterations):
            state = load_state(ctx)
            state.current_loop_iteration += 1
            from codex_orchestrator.state import save_state, transition
            save_state(ctx, state)
            stage = state.stage
            if stage == until:
                return state
            if not ctx.paths.master_prompt.exists():
                if master is None:
                    raise FileNotFoundError("Missing master prompt; pass --master or initialize first")
                init_workflow(ctx, master=master, invocation_argv=["cxor", "auto"], mode="auto", until=until)
                continue
            if not ctx.paths.goal_spec.exists() or stage in {"MASTER_PROMPT_SAVED", "GOAL_SPEC_REQUIRED", "INITIALIZED"}:
                normalize_master_prompt(ctx)
                continue
            if not ctx.paths.census_repo_files.exists() or stage == "CENSUS_REQUIRED":
                run_census(ctx)
                continue
            if not ctx.paths.search_evidence_jsonl.exists() or stage == "EVIDENCE_CLASSIFICATION_REQUIRED":
                classify_evidence(ctx)
                continue
            if not ctx.paths.inventory_graph.exists() or stage == "INVENTORY_BUILD_REQUIRED":
                build_inventory(ctx)
                continue
            if not ctx.paths.invariants.exists() or stage == "INVARIANT_EXTRACTION_REQUIRED":
                extract_invariants(ctx)
                continue
            patchlet_index_empty = True
            if ctx.paths.patchlet_index.exists():
                from codex_orchestrator.jsonio import read_json
                try:
                    patchlet_index_empty = not bool(read_json(ctx.paths.patchlet_index).get("patchlets"))
                except Exception:
                    patchlet_index_empty = True
            if not ctx.paths.patchlet_index.exists() or patchlet_index_empty or stage == "PATCHLET_COMPILATION_REQUIRED":
                compile_patchlets(ctx)
                continue
            # Pending patchlets are run before verification.
            state = load_state(ctx)
            if state.pending_patchlets or stage == "PATCHLETS_READY":
                run_all_patchlets(ctx, worker_mode=worker_mode)
                state = load_state(ctx)
                if state.stage == "FAILURE_CLASSIFICATION_REQUIRED":
                    continue
                # No pending patchlets and no failures -> verify on next loop.
                continue
            if stage in {"GLOBAL_VERIFICATION_REQUIRED", "GLOBAL_REVERIFY_REQUIRED"}:
                verify_global(ctx)
                continue
            # Default path after patchlet completion is global verification.
            if stage == "PATCHLET_EXECUTION_COMPLETE":
                transition(ctx, state, "GLOBAL_VERIFICATION_REQUIRED", reason="patchlets complete")
                continue
            if stage == "FAILURE_CLASSIFICATION_REQUIRED":
                classify_failures(ctx)
                continue
            if stage == "REPAIR_PLANNING_REQUIRED":
                plan_repair(ctx)
                continue
            if stage == "REPAIR_PLAN_READY":
                apply_repair(ctx)
                continue
            if stage == "PARTIAL_REDISCOVERY_REQUIRED":
                rediscover(ctx, scope="impacted")
                continue
            if stage == "FULL_REDISCOVERY_REQUIRED":
                rediscover(ctx, scope="full")
                continue
            if stage == "INVENTORY_REBUILD_REQUIRED":
                rebuild_inventory(ctx, scope="impacted")
                continue
            if stage == "PATCHLET_REGENERATION_REQUIRED":
                regenerate_patchlets(ctx, from_repair_plan="latest")
                continue
            if stage == "GLOBAL_VERIFICATION_COMPLETE":
                verify_global(ctx)
                continue
            # Fallback: attempt global verification once patchlet index exists.
            verify_global(ctx)
        raise RuntimeError(f"cxor auto did not reach {until} within {max_iterations} iterations")

    if use_lock:
        with workflow_lock(ctx.paths.lock, target_repo_root=ctx.root):
            return _run()
    return _run()
