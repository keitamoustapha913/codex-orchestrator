from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable

from codex_orchestrator.errors import CxorError, TargetRepoError
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.version import __version__


def _add_repo_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, default=None, help="Target repository. Defaults to current Git root.")
    parser.add_argument("--allow-non-git", action="store_true", help="Allow target directory without Git.")
    parser.add_argument("--allow-self-target", action="store_true", help="Allow targeting the orchestrator source repo intentionally.")


def _ctx(args: argparse.Namespace):
    return resolve_target_repo(
        repo=getattr(args, "repo", None),
        allow_non_git=getattr(args, "allow_non_git", False),
        allow_self_target=getattr(args, "allow_self_target", False),
    )


def cmd_version(args: argparse.Namespace) -> int:
    print(f"codex-orchestrator {__version__}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.doctor import doctor

    ctx = None
    try:
        if args.repo is not None:
            ctx = _ctx(args)
        else:
            # Doctor is read-only and may run outside a target repo.
            try:
                ctx = _ctx(args)
            except TargetRepoError:
                ctx = None
        print(json.dumps(doctor(ctx), indent=2, sort_keys=True))
        return 0
    except CxorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def cmd_init(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.init import init_workflow

    ctx = _ctx(args)
    state = init_workflow(ctx, master=args.master, invocation_argv=sys.argv, mode="manual", until="DONE")
    print(f"{state.stage} {ctx.root}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    import time

    from codex_orchestrator.stages.status import status

    ctx = _ctx(args)
    iterations = 0
    while True:
        result = status(ctx)
        if getattr(args, "workflow", None) and result.get("active_workflow_id") != args.workflow and result.get("workflow_id") != args.workflow:
            result = {**result, "workflow_filter": args.workflow, "filter_match": False}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Repo: {result['repo']}")
            print(f"Stage: {result['stage']}")
            print(f"Current: {result.get('current_patchlet_id') or '-'} / {result.get('current_attempt_id') or '-'}")
            print(f"Loop iteration: {result.get('current_loop_iteration')}")
            print(
                "Patchlets: "
                f"completed={result.get('completed_patchlet_count')} "
                f"failed={result.get('failed_patchlet_count')} "
                f"pending={result.get('pending_patchlet_count')}"
            )
            print(f"Classification: {result.get('classification')}")
            print(f"Prompt: {result.get('active_prompt_path') or '-'}")
            last_event = result.get("last_event") or {}
            print(f"Last event: {last_event.get('event_id', '-')} {last_event.get('event_type', '-')}")
            print(f"Next: {result.get('next_action')}")
        if not args.watch:
            return 0
        iterations += 1
        if args.max_iterations is not None and iterations >= args.max_iterations:
            return 0
        time.sleep(args.interval)


def cmd_goal_progress(args: argparse.Namespace) -> int:
    import time

    from codex_orchestrator.goal_progress import load_goal_progress

    ctx = _ctx(args)
    iterations = 0
    while True:
        progress = load_goal_progress(ctx.paths.workflow_dir)
        if progress is None:
            progress = {"schema_version": "1.0", "kind": "goal_progress", "overall_goal_status": "NOT_STARTED", "counts": {}}
        if args.json:
            print(json.dumps(progress, indent=2, sort_keys=True))
        else:
            counts = progress.get("counts", {})
            print(f"workflow_id: {progress.get('workflow_id') or '-'}")
            print(f"run_id: {progress.get('run_id') or '-'}")
            print(f"overall goal status: {progress.get('overall_goal_status')}")
            print(f"provability status: {progress.get('provability_status') or '-'}")
            print(
                "counts: "
                f"required={counts.get('required_obligations', 0)} "
                f"proven={counts.get('proven', 0)} "
                f"failed={counts.get('failed', 0)} "
                f"blocked={counts.get('blocked', 0)} "
                f"unproven={counts.get('unproven', 0)}"
            )
            for obligation in progress.get("obligations", []):
                print(f"- {obligation.get('obligation_id')}: {obligation.get('status')} {obligation.get('operator_summary', '')}")
            print(f"latest accepted checkpoint: {progress.get('latest_accepted_checkpoint') or '-'}")
            print(f"applyable progress: {progress.get('applyable_progress')}")
            print(f"next action: {progress.get('next_action') or '-'}")
        if not args.watch:
            return 0
        iterations += 1
        if args.max_iterations is not None and iterations >= args.max_iterations:
            return 0
        time.sleep(args.interval)


def cmd_decomposition(args: argparse.Namespace) -> int:
    from codex_orchestrator.jsonio import read_json
    from codex_orchestrator.stages.status import status

    ctx = _ctx(args)
    decomp_dir = ctx.paths.workflow_dir / "decomposition"
    plan_path = decomp_dir / "work_decomposition_plan.json"
    patchlet_plan_path = decomp_dir / "patchlet_plan.json"
    graph_path = decomp_dir / "dependency_graph.json"
    group_path = decomp_dir / "transaction_group_plan.json"
    plan = read_json(plan_path) if plan_path.exists() else {}
    patchlet_plan = read_json(patchlet_plan_path) if patchlet_plan_path.exists() else {"patchlets": []}
    graph = read_json(graph_path) if graph_path.exists() else {"topological_order": [], "edges": []}
    group_plan = read_json(group_path) if group_path.exists() else {"transaction_groups": []}
    status_summary = status(ctx).get("decomposition", {})
    payload = {
        "schema_version": "1.0",
        "kind": "decomposition_status",
        "workflow_id": plan.get("workflow_id"),
        "run_id": plan.get("run_id"),
        "decomposition_strategy": plan.get("decomposition_strategy"),
        "work_slice_count": plan.get("work_slice_count", 0),
        "patchlet_count": plan.get("patchlet_count", len(patchlet_plan.get("patchlets", []))),
        "transaction_group_count": plan.get("transaction_group_count", len(group_plan.get("transaction_groups", []))),
        "per_file_patchlet_counts": plan.get("per_file_patchlet_counts", {}),
        "same_file_multi_patchlet_groups": status_summary.get("same_file_multi_patchlet_groups", []),
        "topological_order": graph.get("topological_order", []),
        "ready_patchlets": status_summary.get("ready_patchlets", []),
        "waiting_patchlets": status_summary.get("waiting_patchlets", []),
        "accepted_patchlets": status_summary.get("accepted_patchlets", []),
        "blocked_patchlets": status_summary.get("blocked_patchlets", []),
        "patchlets": patchlet_plan.get("patchlets", []),
        "dependency_edges": graph.get("edges", []),
        "transaction_groups": group_plan.get("transaction_groups", []),
        "decomposition_plan_path": ".codex-orchestrator/decomposition/work_decomposition_plan.json" if plan else None,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(f"workflow_id: {payload.get('workflow_id') or '-'}")
    print(f"run_id: {payload.get('run_id') or '-'}")
    print(f"decomposition strategy: {payload.get('decomposition_strategy') or '-'}")
    print(f"work slices: {payload['work_slice_count']}")
    print(f"patchlets: {payload['patchlet_count']}")
    print(f"transaction groups: {payload['transaction_group_count']}")
    print(f"memory compacting required: false")
    for path, count in sorted(payload.get("per_file_patchlet_counts", {}).items()):
        print(f"{path}: {count} patchlet(s)")
    for group in payload.get("same_file_multi_patchlet_groups", []):
        print(f"same-file sequence: {group['file']} has {' -> '.join(group['patchlet_ids'])}")
    if args.patchlets:
        for patchlet in payload["patchlets"]:
            print(
                f"{patchlet['patchlet_id']} -> {patchlet.get('allowed_product_runtime_file')} "
                f"slice={patchlet.get('work_slice_id')} budget={patchlet.get('time_budget_seconds')}"
            )
    if args.dependencies:
        print("topological order: " + (" -> ".join(payload["topological_order"]) or "-"))
        for edge in payload["dependency_edges"]:
            print(f"{edge.get('from')} -> {edge.get('to')}: {edge.get('reason')}")
    return 0


def cmd_validate_state(args: argparse.Namespace) -> int:
    from codex_orchestrator.validators.state_validator import validate_state_file

    ctx = _ctx(args)
    errors = validate_state_file(ctx.paths.state)
    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VALID")
    return 0


def cmd_census(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.census import run_census

    ctx = _ctx(args)
    tools = run_census(ctx)
    print(json.dumps(tools, indent=2, sort_keys=True))
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.normalize import normalize_master_prompt

    ctx = _ctx(args)
    goal = normalize_master_prompt(ctx)
    print(goal["success_goals"][0]["goal_id"])
    return 0


def cmd_classify_evidence(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.classify_evidence import classify_evidence

    ctx = _ctx(args)
    rows = classify_evidence(ctx)
    print(f"evidence_rows={len(rows)}")
    return 0


def cmd_build_inventory(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.build_inventory import build_inventory

    ctx = _ctx(args)
    graph = build_inventory(ctx)
    print(f"nodes={len(graph.get('nodes', []))}")
    return 0


def cmd_rebuild_inventory(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.rebuild_inventory import rebuild_inventory

    ctx = _ctx(args)
    result = rebuild_inventory(ctx, scope=args.scope)
    print(f"{result['next_stage']} {ctx.root}")
    return 0


def cmd_extract_invariants(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.extract_invariants import extract_invariants

    ctx = _ctx(args)
    invariants = extract_invariants(ctx)
    print(f"invariants={len(invariants)}")
    return 0


def cmd_compile_patchlets(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.compile_patchlets import compile_patchlets

    ctx = _ctx(args)
    index = compile_patchlets(ctx)
    print(f"patchlets={len(index.get('patchlets', []))}")
    return 0


def cmd_run_next(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.run_patchlet import run_next_patchlet

    ctx = _ctx(args)
    result = run_next_patchlet(ctx, worker_mode=args.worker_mode, use_worktree=args.use_worktree)
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    return 0 if result.status not in {"FAILED_WITH_EVIDENCE"} else 1


def cmd_run_all(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.run_patchlet import run_all_patchlets

    ctx = _ctx(args)
    results = run_all_patchlets(ctx, worker_mode=args.worker_mode, use_worktree=args.use_worktree)
    print(json.dumps([r.__dict__ for r in results], indent=2, sort_keys=True))
    return 0 if all(r.status not in {"FAILED_WITH_EVIDENCE"} for r in results) else 1


def cmd_validate_report(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.validate_report import validate_report

    ctx = _ctx(args)
    report = validate_report(ctx, args.patchlet_id)
    print(f"VALID {report['patchlet_id']} {report['status']}")
    return 0


def cmd_verify_global(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.verify_global import verify_global

    ctx = _ctx(args)
    result = verify_global(ctx)
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    return 0 if result.done else 1


def cmd_verify_group(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.verify_group import verify_group

    ctx = _ctx(args)
    result = verify_group(ctx, transaction_group_id=args.transaction_group_id)
    print(f"{result['transaction_group_id']} {result['status']} {result['artifact_path']}")
    return 0 if result["status"] == "PASSED" else 1


def cmd_verify_all_groups(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.verify_group import verify_all_groups

    ctx = _ctx(args)
    results = verify_all_groups(ctx)
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if all(result["status"] == "PASSED" for result in results) else 1


def cmd_classify_failures(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.classify_failures import classify_failures

    ctx = _ctx(args)
    result = classify_failures(ctx)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_plan_repair(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.plan_repair import plan_repair

    ctx = _ctx(args)
    result = plan_repair(ctx)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_apply_repair(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.apply_repair import apply_repair

    ctx = _ctx(args)
    result = apply_repair(ctx)
    if result == "DONE_NOOP":
        print(f"DONE no-op {ctx.root}")
    else:
        print(result)
    return 0


def cmd_regenerate_patchlets(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.regenerate_patchlets import regenerate_patchlets

    ctx = _ctx(args)
    result = regenerate_patchlets(ctx, from_repair_plan=args.from_repair_plan)
    if result.get("status") == "DONE_NOOP":
        print(f"DONE no-op {ctx.root}")
    else:
        print(f"PATCHLETS_READY {ctx.root} {' '.join(result['patchlet_ids'])}")
    return 0


def cmd_rediscover(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.rediscover import rediscover

    ctx = _ctx(args)
    result = rediscover(ctx, scope=args.scope)
    print(f"{result['rediscovery_id']} {result['scope']} {ctx.root}")
    return 0


def cmd_diagnose_real_codex(args: argparse.Namespace) -> int:
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _ctx(args)
    result = diagnose_real_codex_attempt(ctx, attempt_id=args.attempt)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_real_codex_smoke_runbook(args: argparse.Namespace) -> int:
    from codex_orchestrator.real_codex_operator_runbook import (
        DEFAULT_SKIP_COMMAND,
        EXPLICIT_SMOKE_COMMAND,
        command_from_string,
        run_real_codex_smoke_runbook,
    )

    repo_root = Path.cwd()
    result = run_real_codex_smoke_runbook(
        repo_root=repo_root,
        operator_root=args.operator_root,
        timestamp=args.timestamp,
        dry_run=args.dry_run,
        run_real_codex=args.run_real_codex,
        default_skip_command=command_from_string(args.default_skip_command, DEFAULT_SKIP_COMMAND),
        explicit_smoke_command=command_from_string(args.explicit_smoke_command, EXPLICIT_SMOKE_COMMAND),
        live_progress=args.live_progress,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_apply_results(args: argparse.Namespace) -> int:
    from codex_orchestrator.apply_results import apply_results

    ctx = _ctx(args)
    result = apply_results(ctx, mode=args.mode, scope=args.scope, allow_partial=args.allow_partial)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    from codex_orchestrator.control import request_stop

    ctx = _ctx(args)
    mode = "now" if args.now else "after_current_attempt"
    result = request_stop(ctx, mode=mode)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"stop requested mode={mode} repo={ctx.root}")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    from codex_orchestrator.workflow_lifecycle import archive_current_workflow

    ctx = _ctx(args)
    result = archive_current_workflow(ctx)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    import subprocess

    from codex_orchestrator.workflow_lifecycle import reset_current_workflow

    ctx = _ctx(args)
    if not args.archive and not args.hard_delete_artifacts:
        print("error: reset requires --archive or --hard-delete-artifacts", file=sys.stderr)
        return 2
    if args.hard_delete_artifacts:
        status = subprocess.run(["git", "-C", str(ctx.root), "status", "--porcelain=v1"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        dirty = [line for line in status.stdout.splitlines() if line and not line[3:].startswith((".codex-orchestrator/", ".artifacts/"))]
        if dirty:
            print("error: reset --hard-delete-artifacts refuses dirty product/runtime files", file=sys.stderr)
            return 2
    result = reset_current_workflow(ctx, archive=args.archive, hard_delete_artifacts=args.hard_delete_artifacts)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_workflows(args: argparse.Namespace) -> int:
    from codex_orchestrator.workflow_lifecycle import read_workflow_registry

    ctx = _ctx(args)
    registry = read_workflow_registry(ctx.root)
    if args.json:
        print(json.dumps(registry, indent=2, sort_keys=True))
        return 0
    workflows = registry.get("workflows", [])
    if not workflows:
        print(f"No cxor workflows found for repo: {ctx.root}")
        return 0
    active = registry.get("active_workflow_id")
    for workflow in workflows:
        marker = "*" if workflow.get("workflow_id") == active else "-"
        print(
            " ".join(
                [
                    marker,
                    workflow.get("workflow_id", "-"),
                    workflow.get("run_id") or "-",
                    workflow.get("status") or "-",
                    workflow.get("goal_fingerprint") or "-",
                ]
            )
        )
    return 0


def cmd_validate_integration_artifacts(args: argparse.Namespace) -> int:
    from codex_orchestrator.validators.integration_artifact_validator import validate_integration_artifacts

    ctx = _ctx(args)
    result = validate_integration_artifacts(ctx.root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


def cmd_validate_real_codex_smoke_runbook(args: argparse.Namespace) -> int:
    from codex_orchestrator.validators.real_codex_smoke_runbook_validator import validate_real_codex_smoke_runbook

    result = validate_real_codex_smoke_runbook(args.run_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


def cmd_list_real_codex_smoke_runbooks(args: argparse.Namespace) -> int:
    from codex_orchestrator.real_codex_smoke_runbook_listing import (
        format_real_codex_smoke_runbook_table,
        list_real_codex_smoke_runbooks,
    )

    result = list_real_codex_smoke_runbooks(
        args.root,
        latest=args.latest,
        only_invalid=args.only_invalid,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_real_codex_smoke_runbook_table(result))
    return 0


def cmd_export_real_codex_smoke_runbook(args: argparse.Namespace) -> int:
    from codex_orchestrator.real_codex_smoke_runbook_export import export_real_codex_smoke_runbook

    result = export_real_codex_smoke_runbook(
        args.run_dir,
        out=args.out,
        archive_format=args.format,
        force=args.force,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["exported"] else 1


def cmd_inspect_capsule(args: argparse.Namespace) -> int:
    ctx = _ctx(args)
    run_dir = ctx.paths.runs_dir / args.attempt
    payload = {
        "attempt": args.attempt,
        "run_dir": str(run_dir),
        "worker_capsule_manifest": str(run_dir / "worker_capsule.json"),
        "worker_memory_dir": str(run_dir / "worker_memory"),
        "worker_stage_dir": str(run_dir / "worker_stage"),
        "worker_events_path": str(run_dir / "worker_hooks" / "events.jsonl"),
        "wrapper_gate_result_path": str(run_dir / "gates" / "wrapper_gate_result.json"),
        "diagnostics_dir": str(run_dir / "diagnostics"),
        "presence": {
            "worker_capsule_manifest": (run_dir / "worker_capsule.json").exists(),
            "worker_memory_dir": (run_dir / "worker_memory").is_dir(),
            "worker_stage_dir": (run_dir / "worker_stage").is_dir(),
            "worker_events_path": (run_dir / "worker_hooks" / "events.jsonl").exists(),
            "wrapper_gate_result_path": (run_dir / "gates" / "wrapper_gate_result.json").exists(),
            "diagnostics_dir": (run_dir / "diagnostics").is_dir(),
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_validate_capsule(args: argparse.Namespace) -> int:
    from codex_orchestrator.validators.schema_validator import validate_json, validate_json_file

    ctx = _ctx(args)
    run_dir = ctx.paths.runs_dir / args.attempt
    errors: list[str] = []
    capsule_manifest = run_dir / "worker_capsule.json"
    live_memory = run_dir / "worker_memory" / "LIVE_MEMORY.json"
    allowed_paths = run_dir / "worker_memory" / "ALLOWED_PATHS.json"
    events_path = run_dir / "worker_hooks" / "events.jsonl"
    wrapper_gate = run_dir / "gates" / "wrapper_gate_result.json"

    if not capsule_manifest.exists():
        errors.append(f"missing {capsule_manifest}")
    else:
        errors.extend(validate_json_file(capsule_manifest, "worker_capsule.schema.json"))
    if not live_memory.exists():
        errors.append(f"missing {live_memory}")
    else:
        errors.extend(validate_json_file(live_memory, "worker_memory.schema.json"))
    if not allowed_paths.exists():
        errors.append(f"missing {allowed_paths}")
    else:
        errors.extend(validate_json_file(allowed_paths, "allowed_paths.schema.json"))
    if not events_path.exists():
        errors.append(f"missing {events_path}")
    else:
        for lineno, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"events.jsonl line {lineno}: {exc}")
                continue
            if not isinstance(event, dict):
                errors.append(f"events.jsonl line {lineno}: event is not an object")
                continue
            event_errors = validate_json(event, "worker_event.schema.json")
            errors.extend(f"events.jsonl line {lineno}: {error}" for error in event_errors)
    if not wrapper_gate.exists():
        errors.append(f"missing {wrapper_gate}")
    else:
        errors.extend(validate_json_file(wrapper_gate, "wrapper_gate_result.schema.json"))

    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VALID")
    return 0


def cmd_prompts(args: argparse.Namespace) -> int:
    from codex_orchestrator.prompt_index import get_prompt_entry, list_prompt_entries, prompt_index_path

    ctx = _ctx(args)
    index_path = prompt_index_path(ctx.root)
    if args.show or args.show_path:
        entry = get_prompt_entry(ctx.root, args.show) if args.show else None
        prompt_path = None
        if args.show_path:
            candidate = Path(args.show_path)
            prompt_path = candidate if candidate.is_absolute() else ctx.root / candidate
        elif entry is not None:
            prompt_path = ctx.root / entry["path"]
        if prompt_path is None:
            print(f"error: prompt id not found: {args.show}", file=sys.stderr)
            return 1
        if not prompt_path.exists():
            print(f"error: prompt file not found: {prompt_path}", file=sys.stderr)
            return 1
        lines = prompt_path.read_text(encoding="utf-8").splitlines()
        limit = args.lines
        if limit > 0:
            lines = lines[:limit]
        print("\n".join(lines))
        return 0

    filters = {
        "attempt_id": args.attempt,
        "patchlet_id": args.patchlet,
        "kind": args.kind,
        "workflow_id": getattr(args, "workflow", None),
    }
    prompts = list_prompt_entries(ctx.root, filters)
    if args.latest and prompts:
        prompts = [prompts[-1]]
    if args.json:
        print(json.dumps({
            "schema_version": "1.0",
            "kind": "prompt_list",
            "repo": str(ctx.root),
            "count": len(prompts),
            "prompts": prompts,
        }, indent=2, sort_keys=True))
        return 0
    if not index_path.exists():
        print(f"No prompt index found for repo: {ctx.root}")
        return 0
    if not prompts:
        print(f"No prompts found for repo: {ctx.root}")
        return 0
    for prompt in prompts:
        print(
            " ".join(
                [
                    prompt.get("prompt_id", "-"),
                    prompt.get("kind", "-"),
                    prompt.get("patchlet_id") or "-",
                    prompt.get("attempt_id") or "-",
                    prompt.get("path", "-"),
                    f"{prompt.get('size_bytes', 0)} bytes",
                ]
            )
        )
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    import time

    from codex_orchestrator.operator_events import read_operator_events

    ctx = _ctx(args)

    def _emit(events: list[dict]) -> None:
        if args.json:
            print(json.dumps({
                "schema_version": "1.0",
                "kind": "operator_event_list",
                "repo": str(ctx.root),
                "count": len(events),
                "events": events,
            }, indent=2, sort_keys=True))
            return
        if not events:
            print(f"No operator events found for repo: {ctx.root}")
            return
        for event in events:
            print(
                " ".join(
                    [
                        event.get("event_id", "-"),
                        event.get("created_at", "-"),
                        event.get("severity", "-"),
                        event.get("event_type", "-"),
                        event.get("patchlet_id") or event.get("attempt_id") or "-",
                        event.get("summary", ""),
                    ]
                )
            )

    filters = {
        "since": args.since,
        "limit": args.limit,
        "attempt_id": args.attempt,
        "patchlet_id": args.patchlet,
        "event_type": args.event_type,
        "workflow_id": getattr(args, "workflow", None),
        "invocation_id": getattr(args, "invocation", None),
    }
    if not args.follow:
        _emit(read_operator_events(ctx.root, **filters))
        return 0

    emitted = 0
    since = args.since
    while True:
        events = read_operator_events(
            ctx.root,
            since=since,
            limit=args.limit,
            attempt_id=args.attempt,
            patchlet_id=args.patchlet,
            event_type=args.event_type,
            workflow_id=getattr(args, "workflow", None),
            invocation_id=getattr(args, "invocation", None),
        )
        if events:
            if args.json:
                for event in events:
                    print(json.dumps(event, sort_keys=True), flush=True)
            else:
                _emit(events)
            emitted += len(events)
            since = events[-1].get("event_id")
            if args.max_events is not None and emitted >= args.max_events:
                return 0
        elif args.max_events == 0:
            return 0
        time.sleep(args.interval)


def cmd_auto(args: argparse.Namespace) -> int:
    from codex_orchestrator.invocations import create_invocation
    from codex_orchestrator.operator_events import append_operator_event
    from codex_orchestrator.operator_progress import operator_progress_streamer, should_enable_live_progress
    from codex_orchestrator.rerun_preflight import RerunPreflightError, run_rerun_preflight
    from codex_orchestrator.state import load_state
    from codex_orchestrator.stages.auto import run_auto
    from codex_orchestrator.workflow_lifecycle import reset_current_workflow

    ctx = _ctx(args)
    preflight = run_rerun_preflight(
        ctx,
        master=args.master,
        worker_mode=args.worker_mode,
        use_worktree=args.use_worktree,
        until=args.until,
        resume=args.resume,
        new_run=getattr(args, "new_run", False),
        force_new_run=getattr(args, "force_new_run", False),
        allow_dirty_target=getattr(args, "allow_dirty_target", False),
    )
    if preflight["decision"].startswith("REFUSE"):
        raise RerunPreflightError(preflight)
    if preflight["decision"] == "RETURN_EXISTING_DONE":
        state = load_state(ctx)
        print("Existing workflow is already DONE for the same goal fingerprint.", file=sys.stderr)
        print("Use --new-run to start another workflow.", file=sys.stderr)
        print(f"{state.stage} {ctx.root}")
        return 0 if state.stage == args.until else 1
    if preflight["decision"] == "START_NEW_WORKFLOW" and (args.new_run or args.force_new_run or args.archive_existing) and ctx.paths.state.exists():
        reset_current_workflow(ctx, archive=True)

    live_progress = should_enable_live_progress(
        worker_mode=args.worker_mode,
        explicit=args.live_progress,
        stream=sys.stderr,
    )
    if live_progress:
        os.environ["CXOR_LIVE_PROGRESS"] = "1"
        os.environ["CXOR_LIVE_CODEX_PROGRESS"] = "1"
        os.environ["CODEX_PROGRESS_STDERR"] = "1"
        os.environ["CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS"] = str(int(args.progress_interval_seconds))
    os.environ["CXOR_LOOP_GOVERNOR_MODE"] = args.loop_governor_mode
    os.environ["CXOR_MAX_REPEATED_FAILURE_SIGNATURE"] = str(args.max_repeated_failure_signature)
    invocation = create_invocation(
        ctx.root,
        command="auto",
        live_progress=live_progress,
        progress_format=args.progress_format,
    )
    os.environ["CXOR_INVOCATION_ID"] = invocation["invocation_id"]

    with operator_progress_streamer(
        ctx.root,
        enabled=live_progress,
        progress_format=args.progress_format,
        interval_seconds=args.progress_interval_seconds,
        stream=sys.stderr,
    ):
        append_operator_event(
            ctx.root,
            event_type="workflow_started",
            severity="info",
            stage="AUTO",
            summary=f"workflow started repo={ctx.root} until={args.until} worker={args.worker_mode}",
            artifact_paths=[],
            next_action="Running autonomous workflow.",
            details={
                "worker_mode": args.worker_mode,
                "until": args.until,
                "use_worktree": args.use_worktree,
                "max_iterations": args.max_iterations,
            },
        )
        state = run_auto(
            ctx,
            master=args.master,
            resume=args.resume,
            until=args.until,
            worker_mode=args.worker_mode,
            use_worktree=args.use_worktree,
            max_iterations=args.max_iterations,
            use_lock=True,
            allow_dirty_target=getattr(args, "allow_dirty_target", False),
        )
    print(f"{state.stage} {ctx.root}")
    return 0 if state.stage == args.until else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cxor", description="Codex Orchestrator CLI")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor")
    _add_repo_flags(doctor)
    doctor.set_defaults(func=cmd_doctor)

    init = sub.add_parser("init")
    _add_repo_flags(init)
    init.add_argument("--master", type=Path, required=True)
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status")
    _add_repo_flags(status)
    status.add_argument("--json", action="store_true")
    status.add_argument("--watch", action="store_true")
    status.add_argument("--workflow", default=None)
    status.add_argument("--interval", type=float, default=5.0)
    status.add_argument("--max-iterations", type=int, default=None)
    status.set_defaults(func=cmd_status)

    goal_progress = sub.add_parser("goal-progress")
    _add_repo_flags(goal_progress)
    goal_progress.add_argument("--json", action="store_true")
    goal_progress.add_argument("--watch", action="store_true")
    goal_progress.add_argument("--interval", type=float, default=2.0)
    goal_progress.add_argument("--max-iterations", type=int, default=None, help=argparse.SUPPRESS)
    goal_progress.set_defaults(func=cmd_goal_progress)

    decomposition = sub.add_parser("decomposition")
    _add_repo_flags(decomposition)
    decomposition.add_argument("--json", action="store_true")
    decomposition.add_argument("--patchlets", action="store_true")
    decomposition.add_argument("--dependencies", action="store_true")
    decomposition.set_defaults(func=cmd_decomposition)

    validate_state = sub.add_parser("validate-state")
    _add_repo_flags(validate_state)
    validate_state.set_defaults(func=cmd_validate_state)

    for name, func in [
        ("census", cmd_census),
        ("normalize", cmd_normalize),
        ("classify-evidence", cmd_classify_evidence),
        ("build-inventory", cmd_build_inventory),
        ("rebuild-inventory", cmd_rebuild_inventory),
        ("extract-invariants", cmd_extract_invariants),
        ("compile-patchlets", cmd_compile_patchlets),
        ("verify-group", cmd_verify_group),
        ("verify-all-groups", cmd_verify_all_groups),
        ("verify-global", cmd_verify_global),
        ("classify-failures", cmd_classify_failures),
        ("plan-repair", cmd_plan_repair),
        ("apply-repair", cmd_apply_repair),
        ("rediscover", cmd_rediscover),
        ("diagnose-real-codex", cmd_diagnose_real_codex),
        ("inspect-capsule", cmd_inspect_capsule),
        ("validate-capsule", cmd_validate_capsule),
        ("regenerate-patchlets", cmd_regenerate_patchlets),
    ]:
        p = sub.add_parser(name)
        _add_repo_flags(p)
        if name == "regenerate-patchlets":
            p.add_argument("--from-repair-plan", default="latest")
        if name == "diagnose-real-codex":
            p.add_argument("--attempt", required=True)
        if name in {"inspect-capsule", "validate-capsule"}:
            p.add_argument("--attempt", required=True)
        if name in {"rediscover", "rebuild-inventory"}:
            p.add_argument("--scope", default="impacted", choices=["impacted", "full"])
        if name == "verify-group":
            p.add_argument("transaction_group_id")
        p.set_defaults(func=func)

    run_next = sub.add_parser("run-next")
    _add_repo_flags(run_next)
    run_next.add_argument("--worker-mode", default="mock", choices=["mock", "real_codex", "manual", "ci_only"])
    run_next.add_argument("--use-worktree", action="store_true")
    run_next.set_defaults(func=cmd_run_next)

    run_all = sub.add_parser("run-all")
    _add_repo_flags(run_all)
    run_all.add_argument("--worker-mode", default="mock", choices=["mock", "real_codex", "manual", "ci_only"])
    run_all.add_argument("--use-worktree", action="store_true")
    run_all.set_defaults(func=cmd_run_all)

    validate_report = sub.add_parser("validate-report")
    _add_repo_flags(validate_report)
    validate_report.add_argument("patchlet_id")
    validate_report.set_defaults(func=cmd_validate_report)

    prompts = sub.add_parser("prompts")
    _add_repo_flags(prompts)
    prompts.add_argument("--json", action="store_true")
    prompts.add_argument("--latest", action="store_true")
    prompts.add_argument("--attempt", default=None)
    prompts.add_argument("--patchlet", default=None)
    prompts.add_argument("--kind", default=None)
    prompts.add_argument("--workflow", default=None)
    prompts.add_argument("--show", default=None)
    prompts.add_argument("--show-path", default=None)
    prompts.add_argument("--lines", type=int, default=120)
    prompts.set_defaults(func=cmd_prompts)

    monitor = sub.add_parser("monitor")
    _add_repo_flags(monitor)
    monitor.add_argument("--follow", action="store_true")
    monitor.add_argument("--json", action="store_true")
    monitor.add_argument("--since", default=None)
    monitor.add_argument("--attempt", default=None)
    monitor.add_argument("--patchlet", default=None)
    monitor.add_argument("--event-type", default=None)
    monitor.add_argument("--workflow", default=None)
    monitor.add_argument("--invocation", default=None)
    monitor.add_argument("--limit", type=int, default=None)
    monitor.add_argument("--interval", type=float, default=2.0)
    monitor.add_argument("--max-events", type=int, default=None, help=argparse.SUPPRESS)
    monitor.set_defaults(func=cmd_monitor)

    auto = sub.add_parser("auto")
    _add_repo_flags(auto)
    auto.add_argument("--master", type=Path, default=None)
    auto.add_argument("--resume", action="store_true")
    auto.add_argument("--new-run", action="store_true")
    auto.add_argument("--force-new-run", action="store_true")
    auto.add_argument("--allow-dirty-target", action="store_true")
    auto.add_argument("--archive-existing", action="store_true")
    auto.add_argument("--until", default="DONE")
    auto.add_argument("--worker-mode", default="mock", choices=["mock", "real_codex", "manual", "ci_only"])
    auto.add_argument("--use-worktree", action="store_true")
    auto.add_argument("--max-iterations", type=int, default=100)
    auto_progress = auto.add_mutually_exclusive_group()
    auto_progress.add_argument("--live-progress", dest="live_progress", action="store_true")
    auto_progress.add_argument("--no-live-progress", dest="live_progress", action="store_false")
    auto.add_argument("--progress-interval-seconds", type=float, default=15.0)
    auto.add_argument("--progress-format", choices=["compact", "jsonl"], default="compact")
    auto.add_argument("--max-repeated-failure-signature", type=int, default=3)
    auto.add_argument("--loop-governor-mode", choices=["warning", "safe-fail"], default="warning")
    auto.set_defaults(live_progress=None)
    auto.set_defaults(func=cmd_auto)

    runbook = sub.add_parser("real-codex-smoke-runbook")
    mode = runbook.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run-real-codex", action="store_true")
    runbook.add_argument("--operator-root", type=Path, default=None)
    runbook.add_argument("--timestamp", default=None, help=argparse.SUPPRESS)
    runbook.add_argument("--default-skip-command", default=None, help=argparse.SUPPRESS)
    runbook.add_argument("--explicit-smoke-command", default=None, help=argparse.SUPPRESS)
    live_progress = runbook.add_mutually_exclusive_group()
    live_progress.add_argument("--live-progress", dest="live_progress", action="store_true")
    live_progress.add_argument("--no-live-progress", dest="live_progress", action="store_false")
    runbook.set_defaults(live_progress=None)
    runbook.set_defaults(func=cmd_real_codex_smoke_runbook)

    apply_results = sub.add_parser("apply-results")
    _add_repo_flags(apply_results)
    apply_results.add_argument("--mode", default="patch", choices=["patch", "branch", "working-tree"])
    apply_results.add_argument("--scope", default="final", choices=["final", "accepted"])
    apply_results.add_argument("--allow-partial", action="store_true")
    apply_results.set_defaults(func=cmd_apply_results)

    stop = sub.add_parser("stop")
    _add_repo_flags(stop)
    stop_mode = stop.add_mutually_exclusive_group()
    stop_mode.add_argument("--now", action="store_true")
    stop_mode.add_argument("--after-current-attempt", action="store_true")
    stop.add_argument("--json", action="store_true")
    stop.set_defaults(func=cmd_stop)

    archive = sub.add_parser("archive")
    _add_repo_flags(archive)
    archive.set_defaults(func=cmd_archive)

    reset = sub.add_parser("reset")
    _add_repo_flags(reset)
    reset.add_argument("--archive", action="store_true")
    reset.add_argument("--hard-delete-artifacts", action="store_true")
    reset.set_defaults(func=cmd_reset)

    workflows = sub.add_parser("workflows")
    _add_repo_flags(workflows)
    workflows.add_argument("--json", action="store_true")
    workflows.set_defaults(func=cmd_workflows)

    validate_integration = sub.add_parser("validate-integration-artifacts")
    _add_repo_flags(validate_integration)
    validate_integration.set_defaults(func=cmd_validate_integration_artifacts)

    validate_runbook = sub.add_parser("validate-real-codex-smoke-runbook")
    validate_runbook.add_argument("--run-dir", type=Path, required=True)
    validate_runbook.set_defaults(func=cmd_validate_real_codex_smoke_runbook)

    list_runbooks = sub.add_parser("list-real-codex-smoke-runbooks")
    list_runbooks.add_argument("--root", type=Path, default=None)
    list_runbooks.add_argument("--json", action="store_true")
    list_runbooks.add_argument("--latest", action="store_true")
    list_runbooks.add_argument("--only-invalid", action="store_true")
    list_runbooks.add_argument("--limit", type=int, default=None)
    list_runbooks.set_defaults(func=cmd_list_real_codex_smoke_runbooks)

    export_runbook = sub.add_parser("export-real-codex-smoke-runbook")
    export_runbook.add_argument("--run-dir", type=Path, required=True)
    export_runbook.add_argument("--out", type=Path, default=None)
    export_runbook.add_argument("--format", choices=["zip"], default="zip")
    export_runbook.add_argument("--force", action="store_true")
    export_runbook.set_defaults(func=cmd_export_real_codex_smoke_runbook)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        raise SystemExit(cmd_version(args))
    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(0)
    try:
        code = args.func(args)
    except CxorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
