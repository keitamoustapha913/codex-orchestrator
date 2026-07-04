from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from codex_orchestrator.command_runner import CommandRunner
from codex_orchestrator.errors import WorkerExecutionError
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _setup_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def test_real_codex_runner_emits_compact_liveness_events(tmp_path: Path):
    script = tmp_path / "quiet.py"
    script.write_text("import time\ntime.sleep(1.4)\n", encoding="utf-8")
    events: list[dict] = []

    CommandRunner().run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout_seconds=3,
        liveness_callback=events.append,
        progress_interval_seconds=1,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )

    assert any(event["event_type"] == "codex_liveness" for event in events)


def test_liveness_events_do_not_print_full_jsonl(tmp_path: Path):
    script = tmp_path / "stream.py"
    script.write_text("import json\nprint(json.dumps({'type':'agent_message','payload':'x'*1000}), flush=True)\n", encoding="utf-8")
    events: list[dict] = []

    CommandRunner().run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout_seconds=3,
        liveness_callback=events.append,
        stdout_line_callback=lambda _line, _elapsed: None,
        progress_interval_seconds=1,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )

    assert "x" * 1000 not in json.dumps(events)


def test_liveness_events_include_patchlet_attempt_elapsed_and_last_event_type(tmp_path: Path):
    script = tmp_path / "stream.py"
    script.write_text("import json, time\nprint(json.dumps({'type':'thread.started'}), flush=True)\ntime.sleep(1.2)\n", encoding="utf-8")
    events: list[dict] = []

    CommandRunner().run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout_seconds=3,
        liveness_callback=events.append,
        progress_interval_seconds=1,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )

    event = next(event for event in events if event["event_type"] == "codex_liveness")
    assert event["patchlet_id"] == "P0001"
    assert event["attempt_id"] == "P0001_attempt1"
    assert event["elapsed_seconds"] >= 1
    assert event["last_event_type"] in {"thread.started", "process.started"}


def test_liveness_events_are_throttled_by_progress_interval(tmp_path: Path):
    script = tmp_path / "quiet.py"
    script.write_text("import time\ntime.sleep(1.4)\n", encoding="utf-8")
    events: list[dict] = []

    CommandRunner().run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout_seconds=5,
        liveness_callback=events.append,
        progress_interval_seconds=10,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )

    assert [event["event_type"] for event in events].count("codex_liveness") <= 1


def test_liveness_events_continue_during_long_running_stream(tmp_path: Path):
    script = tmp_path / "stream.py"
    script.write_text(
        "import json, time\n"
        "for i in range(20):\n"
        "    print(json.dumps({'type':'agent_message','i':i}), flush=True)\n"
        "    time.sleep(0.1)\n",
        encoding="utf-8",
    )
    events: list[dict] = []

    CommandRunner().run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout_seconds=5,
        liveness_callback=events.append,
        progress_interval_seconds=1,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )

    assert any(event["event_type"] == "codex_liveness" for event in events)


def test_liveness_events_are_written_to_operator_events_jsonl(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ctx = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/usr/bin/env python3\nimport time\ntime.sleep(2)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS", "1")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS", "1")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    assert "codex_liveness" in (ctx.paths.workflow_dir / "operator_events.jsonl").read_text(encoding="utf-8")


def test_liveness_events_are_visible_in_live_progress_output(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    ctx = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/usr/bin/env python3\nimport time\ntime.sleep(2)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS", "1")
    monkeypatch.setenv("CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS", "1")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    assert "codex alive:" in capsys.readouterr().err


def test_liveness_includes_no_progress_duration(tmp_path: Path):
    script = tmp_path / "quiet.py"
    script.write_text("import time\ntime.sleep(1.3)\n", encoding="utf-8")
    events: list[dict] = []

    CommandRunner().run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout_seconds=5,
        liveness_callback=events.append,
        progress_interval_seconds=1,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )

    assert any(event.get("no_progress_for_seconds", 0) >= 1 for event in events)


def test_stall_classifier_reports_likely_stalled_after_configured_no_progress_window(tmp_path: Path):
    script = tmp_path / "quiet.py"
    script.write_text("import time\ntime.sleep(1.3)\n", encoding="utf-8")
    events: list[dict] = []

    CommandRunner().run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout_seconds=5,
        liveness_callback=events.append,
        progress_interval_seconds=1,
        no_progress_stall_seconds=1,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )

    assert any(event.get("stall_status") == "likely_stalled" for event in events)
