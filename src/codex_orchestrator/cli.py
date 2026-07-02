from __future__ import annotations

import argparse
import json
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
    from codex_orchestrator.stages.status import status

    ctx = _ctx(args)
    result = status(ctx)
    print(json.dumps(result, indent=2, sort_keys=True))
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


def cmd_auto(args: argparse.Namespace) -> int:
    from codex_orchestrator.stages.auto import run_auto

    ctx = _ctx(args)
    state = run_auto(
        ctx,
        master=args.master,
        resume=args.resume,
        until=args.until,
        worker_mode=args.worker_mode,
        use_worktree=args.use_worktree,
        max_iterations=args.max_iterations,
        use_lock=True,
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
    status.set_defaults(func=cmd_status)

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

    auto = sub.add_parser("auto")
    _add_repo_flags(auto)
    auto.add_argument("--master", type=Path, default=None)
    auto.add_argument("--resume", action="store_true")
    auto.add_argument("--until", default="DONE")
    auto.add_argument("--worker-mode", default="mock", choices=["mock", "real_codex", "manual", "ci_only"])
    auto.add_argument("--use-worktree", action="store_true")
    auto.add_argument("--max-iterations", type=int, default=100)
    auto.set_defaults(func=cmd_auto)

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
