from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.command_runner import CommandRunner, command_available
from codex_orchestrator.jsonio import append_jsonl, write_json
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext


def _record_command(ctx: TargetRepoContext, *, name: str, result) -> None:
    append_jsonl(ctx.paths.census_commands, {
        "schema_version": "1.0",
        "kind": "census_command",
        "name": name,
        "command": " ".join(result.args),
        "cwd": result.cwd,
        "exit_code": result.exit_code,
        "stdout_path": result.stdout_path,
        "stderr_path": result.stderr_path,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
    })


def run_census(ctx: TargetRepoContext) -> dict:
    ctx.paths.census_dir.mkdir(parents=True, exist_ok=True)
    (ctx.paths.census_dir / "stdout").mkdir(exist_ok=True)
    (ctx.paths.census_dir / "stderr").mkdir(exist_ok=True)
    # Reset commands log for deterministic stage reruns.
    ctx.paths.census_commands.write_text("", encoding="utf-8")
    runner = CommandRunner()

    git_ls = runner.run(
        ["git", "ls-files"],
        cwd=ctx.root,
        stdout_path=ctx.paths.census_repo_files,
        stderr_path=ctx.paths.census_dir / "stderr" / "git_ls_files.err",
    )
    _record_command(ctx, name="git ls-files", result=git_ls)

    git_status = runner.run(
        ["git", "status", "--short"],
        cwd=ctx.root,
        stdout_path=ctx.paths.census_git_status,
        stderr_path=ctx.paths.census_dir / "stderr" / "git_status.err",
    )
    _record_command(ctx, name="git status --short", result=git_status)

    tools = {name: {"available": command_available(name), "checked_at": now_iso()} for name in ["git", "rg", "pytest", "npm", "docker"]}
    write_json(ctx.paths.census_tool_availability, tools)

    if tools["rg"]["available"]:
        rg = runner.run(
            ["rg", "--files"],
            cwd=ctx.root,
            stdout_path=ctx.paths.census_dir / "stdout" / "rg_files.txt",
            stderr_path=ctx.paths.census_dir / "stderr" / "rg_files.err",
        )
        _record_command(ctx, name="rg --files", result=rg)
        lines = [json.dumps({"path": line}, sort_keys=True) for line in rg.stdout.splitlines()]
        ctx.paths.census_rg_files.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    else:
        ctx.paths.census_rg_files.write_text("", encoding="utf-8")

    state = load_state(ctx)
    transition(ctx, state, "CENSUS_READY", reason="deterministic census complete")
    return tools
