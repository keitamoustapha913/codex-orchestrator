from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from codex_orchestrator.errors import WorkerExecutionError
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workers.codex_exec import CodexExecWorker


def _setup(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))["patchlets"][0]
    return ctx, patchlet


def _write_fake_codex(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_codex_worker_writes_progress_jsonl_from_fake_codex_events(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
print(json.dumps({"type": "thread.started"}), flush=True)
print(json.dumps({"type": "turn.started"}), flush=True)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "progress_events"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    progress = _events(run_dir / "progress.jsonl")
    assert [event["signal"] for event in progress] == ["process.started", "thread.started", "turn.started"]


def test_codex_worker_progress_records_thread_started(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex, "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'type': 'thread.started'}), flush=True)\nraise SystemExit(17)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "thread_started"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    assert "thread.started" in [event["signal"] for event in _events(run_dir / "progress.jsonl")]


def test_codex_worker_progress_records_command_execution_completed(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'type': 'command_execution.completed', 'summary': 'read TASK_CONTRACT.md'}), flush=True)\nraise SystemExit(17)\n",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "command_completed"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    event = next(event for event in _events(run_dir / "progress.jsonl") if event["signal"] == "command_execution.completed")
    assert event["signal"] == "command_execution.completed"
    assert event["summary"] == "read TASK_CONTRACT.md"


def test_codex_worker_progress_file_is_under_run_dir(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex, "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'type': 'thread.started'}), flush=True)\nraise SystemExit(17)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "progress_path"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    assert (run_dir / "progress.jsonl").exists()


def test_codex_worker_progress_is_small_not_full_stdout_copy(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
print(json.dumps({"type": "thread.started", "message": "x" * 1000}), flush=True)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "small_progress"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    progress_text = (run_dir / "progress.jsonl").read_text(encoding="utf-8")
    assert "x" * 1000 not in progress_text
    assert len(progress_text) < 600


def test_codex_worker_timeout_preserves_progress_events(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
import time
print(json.dumps({"type": "thread.started"}), flush=True)
time.sleep(5)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "1")

    run_dir = ctx.paths.runs_dir / "timeout_progress"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    command = json.loads((run_dir / "command.json").read_text(encoding="utf-8"))
    assert command["timed_out"] is True
    assert "thread.started" in [event["signal"] for event in _events(run_dir / "progress.jsonl")]


def test_codex_worker_emits_compact_live_progress_to_stderr_when_enabled(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
print(json.dumps({"type": "thread.started", "payload": "x" * 1000}), flush=True)
print(json.dumps({"type": "turn.started"}), flush=True)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS", "1")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS", "1")

    run_dir = ctx.paths.runs_dir / "live_progress_enabled"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    stderr = capsys.readouterr().err
    assert f"[cxor:{run_dir.name} +" in stderr
    assert "codex: thread.started" in stderr
    assert '{"type":' not in stderr
    assert "x" * 1000 not in stderr


def test_live_progress_can_be_disabled_with_env(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex, "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'type': 'thread.started'}), flush=True)\nraise SystemExit(17)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS", "0")

    run_dir = ctx.paths.runs_dir / "live_progress_disabled"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    assert "[cxor:" not in capsys.readouterr().err
    assert "thread.started" in [event["signal"] for event in _events(run_dir / "progress.jsonl")]


def test_live_progress_is_throttled(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
for _ in range(5):
    print(json.dumps({"type": "thread.started"}), flush=True)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS", "1")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS", "60")

    run_dir = ctx.paths.runs_dir / "live_progress_throttled"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    live_lines = [line for line in capsys.readouterr().err.splitlines() if line.startswith("[cxor:")]
    assert len([line for line in live_lines if "thread.started" in line]) == 1
    assert len([event for event in _events(run_dir / "progress.jsonl") if event["signal"] == "thread.started"]) == 5


def test_live_progress_does_not_replace_progress_jsonl(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex, "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'type': 'thread.started'}), flush=True)\nraise SystemExit(17)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS", "1")

    run_dir = ctx.paths.runs_dir / "live_progress_artifact_compat"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    assert "[cxor:" in capsys.readouterr().err
    assert (run_dir / "progress.jsonl").exists()
    assert (run_dir / "stdout.txt").exists()
    assert (run_dir / "stderr.txt").exists()
    assert (run_dir / "output.jsonl").exists()


def test_live_progress_does_not_print_full_json_payload(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex, "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'SECRET_PROMPT_TEXT'}}), flush=True)\nraise SystemExit(17)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS", "1")

    run_dir = ctx.paths.runs_dir / "live_progress_no_payload"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    stderr = capsys.readouterr().err
    assert "codex: message" in stderr
    assert "SECRET_PROMPT_TEXT" not in stderr


def test_live_progress_records_exit_line(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    ctx, patchlet = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex, "#!/usr/bin/env python3\nraise SystemExit(17)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS", "1")

    run_dir = ctx.paths.runs_dir / "live_progress_exit"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    assert "codex: exited 17" in capsys.readouterr().err
