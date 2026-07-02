from __future__ import annotations

import json
import os
import selectors
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, TextIO

from codex_orchestrator.codex_execution_policy import (
    resolve_patchlet_timeout_seconds,
    resolve_progress_interval_seconds,
)
from codex_orchestrator.codex_model_profile import resolve_codex_model_profile


DEFAULT_SKIP_COMMAND = [
    "uv",
    "run",
    "--no-sync",
    "pytest",
    "-q",
    "tests/smoke/test_real_codex_auto_worktree.py",
]
EXPLICIT_SMOKE_COMMAND = [*DEFAULT_SKIP_COMMAND, "--run-real-codex", "-s"]


@dataclass(frozen=True)
class CommandCapture:
    exit_code: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], Path, dict[str, str]], CommandCapture]


def default_command_runner(args: list[str], cwd: Path, env: dict[str, str]) -> CommandCapture:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return CommandCapture(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)


def streaming_command_runner(
    args: list[str],
    cwd: Path,
    env: dict[str, str],
    *,
    live_progress_sink: TextIO | None,
) -> CommandCapture:
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    selector = selectors.DefaultSelector()
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    if process.stdout is not None:
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    if process.stderr is not None:
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")

    while selector.get_map():
        for key, _ in selector.select(timeout=0.2):
            line = key.fileobj.readline()
            if line == "":
                selector.unregister(key.fileobj)
                continue
            if key.data == "stdout":
                stdout_chunks.append(line)
            else:
                stderr_chunks.append(line)
            _tee_progress_line(line, live_progress_sink)

    exit_code = process.wait()
    return CommandCapture(exit_code=exit_code, stdout="".join(stdout_chunks), stderr="".join(stderr_chunks))


def run_real_codex_smoke_runbook(
    *,
    repo_root: Path,
    operator_root: Path | None = None,
    timestamp: str | None = None,
    dry_run: bool,
    run_real_codex: bool,
    runner: CommandRunner | None = None,
    default_skip_command: list[str] | None = None,
    explicit_smoke_command: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    live_progress: bool | None = None,
    live_progress_sink: TextIO | None = None,
) -> dict:
    if dry_run == run_real_codex:
        raise ValueError("choose exactly one of dry_run or run_real_codex")

    repo_root = repo_root.resolve()
    selected_env = dict(os.environ if env is None else env)
    live_progress_enabled = _resolve_runbook_live_progress(selected_env, run_real_codex=run_real_codex, requested=live_progress)
    policy = _selected_policy(
        selected_env,
        dry_run=dry_run,
        run_real_codex=run_real_codex,
        live_progress_enabled=live_progress_enabled,
    )
    effective_runner = runner or default_command_runner
    run_dir = _operator_run_dir(repo_root, operator_root, timestamp)
    run_dir.mkdir(parents=True, exist_ok=False)

    (run_dir / "README.md").write_text(_readme_text(dry_run=dry_run, run_real_codex=run_real_codex), encoding="utf-8")
    (run_dir / "environment.txt").write_text(_environment_text(repo_root, selected_env), encoding="utf-8")
    _write_json(run_dir / "selected_policy.json", policy)

    git_status = effective_runner(["git", "status", "--short"], repo_root, selected_env)
    (run_dir / "git_status.txt").write_text(git_status.stdout + git_status.stderr, encoding="utf-8")

    codex_version = effective_runner(["codex", "--version"], repo_root, selected_env)
    (run_dir / "codex_version.txt").write_text(codex_version.stdout + codex_version.stderr, encoding="utf-8")

    default_command = default_skip_command or DEFAULT_SKIP_COMMAND
    default_skip = effective_runner(default_command, repo_root, selected_env)
    (run_dir / "default_skip_stdout.txt").write_text(default_skip.stdout, encoding="utf-8")
    (run_dir / "default_skip_stderr.txt").write_text(default_skip.stderr, encoding="utf-8")

    result_payload = {
        "schema_version": "1.0",
        "kind": "real_codex_smoke_operator_result",
        "outcome": "dry_run" if dry_run else "not_run",
        "default_skip": {
            "exit_code": default_skip.exit_code,
            "skipped": default_skip.exit_code == 0 and "skipped" in default_skip.stdout.lower(),
        },
        "explicit_smoke": {
            "run": False,
            "exit_code": None,
            "outcome": "not_run",
        },
        "operator_run_dir": str(run_dir),
        "diagnosis_paths": [],
    }
    diagnosis_payload = _empty_diagnosis_paths_payload()

    if dry_run:
        (run_dir / "explicit_smoke_stdout.txt").write_text(
            "explicit real Codex smoke was not run in dry-run mode\n",
            encoding="utf-8",
        )
        (run_dir / "explicit_smoke_stderr.txt").write_text("", encoding="utf-8")
    else:
        explicit_command = explicit_smoke_command or EXPLICIT_SMOKE_COMMAND
        explicit_env = dict(selected_env)
        explicit_env["CXOR_LIVE_CODEX_PROGRESS"] = "1" if live_progress_enabled else "0"
        if runner is None:
            explicit = streaming_command_runner(
                explicit_command,
                repo_root,
                explicit_env,
                live_progress_sink=live_progress_sink or sys.stderr if live_progress_enabled else None,
            )
        else:
            explicit = effective_runner(explicit_command, repo_root, explicit_env)
            if live_progress_enabled:
                _tee_progress_lines(explicit.stdout, live_progress_sink or sys.stderr)
                _tee_progress_lines(explicit.stderr, live_progress_sink or sys.stderr)
        (run_dir / "explicit_smoke_stdout.txt").write_text(explicit.stdout, encoding="utf-8")
        (run_dir / "explicit_smoke_stderr.txt").write_text(explicit.stderr, encoding="utf-8")
        parsed, parse_error = parse_smoke_stdout(explicit.stdout)
        explicit_result = {
            "run": True,
            "exit_code": explicit.exit_code,
            "outcome": parsed.get("outcome", "unknown") if parsed is not None else "unparsed",
        }
        if parse_error is not None:
            explicit_result["parse_error"] = parse_error
        if parsed is not None:
            explicit_result["parsed_smoke"] = parsed
            result_payload.update(_top_level_smoke_fields(parsed))
            diagnosis_payload = _diagnosis_paths_from_smoke(parsed, run_dir)
            result_payload["diagnosis_paths"] = [
                value for key, value in diagnosis_payload.items()
                if key.endswith("_path") and value
            ]
        result_payload["explicit_smoke"] = explicit_result
        result_payload["outcome"] = explicit_result["outcome"]

    _write_json(run_dir / "diagnosis_paths.json", diagnosis_payload)
    _write_json(run_dir / "result.json", result_payload)
    return result_payload


def parse_smoke_stdout(stdout: str) -> tuple[dict | None, str | None]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed, None
    return None, "no JSON object found in explicit smoke stdout"


def _operator_run_dir(repo_root: Path, operator_root: Path | None, timestamp: str | None) -> Path:
    root = operator_root.resolve() if operator_root is not None else repo_root / ".operator-runs"
    stamp = timestamp or datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    return root / "real-codex-smoke" / f"{stamp}-real-codex-smoke"


def _selected_policy(
    env: Mapping[str, str],
    *,
    dry_run: bool,
    run_real_codex: bool,
    live_progress_enabled: bool,
) -> dict:
    profile = resolve_codex_model_profile("patchlet", env)
    timeout = resolve_patchlet_timeout_seconds(env)
    return {
        "schema_version": "1.0",
        "kind": "real_codex_smoke_selected_policy",
        "codex_patchlet_timeout_seconds": timeout,
        "codex_timeout_seconds": _optional_int_env(env, "CODEX_TIMEOUT_SECONDS"),
        "codex_model": profile.model,
        "codex_reasoning": profile.reasoning,
        "codex_progress_interval_seconds": resolve_progress_interval_seconds(env),
        "live_progress_enabled": live_progress_enabled,
        "run_real_codex": run_real_codex,
        "dry_run": dry_run,
    }


def _resolve_runbook_live_progress(
    env: Mapping[str, str],
    *,
    run_real_codex: bool,
    requested: bool | None,
) -> bool:
    if not run_real_codex:
        return False if requested is None else requested
    if requested is not None:
        return requested
    return env.get("CXOR_LIVE_CODEX_PROGRESS") != "0"


def _tee_progress_lines(text: str, sink: TextIO) -> None:
    for line in text.splitlines(keepends=True):
        _tee_progress_line(line, sink)


def _tee_progress_line(line: str, sink: TextIO | None) -> None:
    if sink is None:
        return
    if line.startswith("[cxor:"):
        sink.write(line)
        sink.flush()


def _optional_int_env(env: Mapping[str, str], name: str) -> int | None:
    value = env.get(name)
    if value is None or value == "":
        return None
    return int(value)


def _environment_text(repo_root: Path, env: Mapping[str, str]) -> str:
    lines = [
        f"repo_root={repo_root}",
        f"cwd={Path.cwd()}",
        f"UV_CACHE_DIR={env.get('UV_CACHE_DIR', '')}",
        f"CODEX_PATCHLET_TIMEOUT_SECONDS={env.get('CODEX_PATCHLET_TIMEOUT_SECONDS', '')}",
        f"CODEX_TIMEOUT_SECONDS={env.get('CODEX_TIMEOUT_SECONDS', '')}",
        f"CODEX_PROGRESS_INTERVAL_SECONDS={env.get('CODEX_PROGRESS_INTERVAL_SECONDS', '')}",
        f"CODEX_PATCHLET_MODEL={env.get('CODEX_PATCHLET_MODEL', '')}",
        f"CODEX_MODEL={env.get('CODEX_MODEL', '')}",
        f"CODEX_PATCHLET_REASONING={env.get('CODEX_PATCHLET_REASONING', '')}",
        f"CODEX_REASONING={env.get('CODEX_REASONING', '')}",
    ]
    return "\n".join(lines) + "\n"


def _readme_text(*, dry_run: bool, run_real_codex: bool) -> str:
    mode = "dry_run" if dry_run else "run_real_codex" if run_real_codex else "unknown"
    return (
        "# Real Codex Smoke Operator Run\n\n"
        f"Mode: {mode}\n\n"
        "This directory captures a manual operator-controlled real-Codex smoke attempt.\n"
        "Dry-run mode does not invoke explicit real Codex. Explicit mode preserves stdout,\n"
        "stderr, selected policy, and diagnosis paths. A safe_failure outcome means evidence\n"
        "was captured; it does not mean the task reached DONE.\n"
    )


def _top_level_smoke_fields(smoke: Mapping[str, object]) -> dict:
    fields = [
        "diagnosis_json_path",
        "diagnosis_md_path",
        "diagnosis_primary_category",
        "run_manifest_path",
        "run_dir",
        "stdout_path",
        "stderr_path",
        "output_jsonl_path",
        "progress_path",
        "timeout_seconds",
        "timed_out",
        "selected_model",
        "selected_reasoning",
    ]
    return {field: smoke[field] for field in fields if field in smoke}


def _empty_diagnosis_paths_payload() -> dict:
    return {
        "schema_version": "1.0",
        "kind": "real_codex_smoke_diagnosis_paths",
        "diagnosis_json_path": None,
        "diagnosis_md_path": None,
        "run_manifest_path": None,
        "run_dir": None,
        "stdout_path": None,
        "stderr_path": None,
        "output_jsonl_path": None,
        "progress_path": None,
        "copied_diagnosis_json": None,
        "copied_diagnosis_md": None,
    }


def _diagnosis_paths_from_smoke(smoke: Mapping[str, object], run_dir: Path) -> dict:
    payload = _empty_diagnosis_paths_payload()
    for key in [
        "diagnosis_json_path",
        "diagnosis_md_path",
        "run_manifest_path",
        "run_dir",
        "stdout_path",
        "stderr_path",
        "output_jsonl_path",
        "progress_path",
    ]:
        value = smoke.get(key)
        payload[key] = str(value) if value else None
    _copy_if_present(payload, "diagnosis_json_path", run_dir / "diagnosis.json", "copied_diagnosis_json")
    _copy_if_present(payload, "diagnosis_md_path", run_dir / "diagnosis.md", "copied_diagnosis_md")
    return payload


def _copy_if_present(payload: dict, source_key: str, destination: Path, copied_key: str) -> None:
    source_value = payload.get(source_key)
    if not source_value:
        return
    source = Path(str(source_value))
    if not source.exists():
        return
    shutil.copyfile(source, destination)
    payload[copied_key] = destination.name


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def command_from_string(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return shlex.split(value)
