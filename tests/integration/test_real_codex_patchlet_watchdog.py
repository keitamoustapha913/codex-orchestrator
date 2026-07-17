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
from codex_orchestrator.workers.codex_exec import CodexExecWorker


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
    patchlet = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))["patchlets"][0]
    return ctx, patchlet


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_patchlet_timeout_defaults_to_600_seconds(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(
        fake_codex,
        """#!/usr/bin/env python3
import json, os
from pathlib import Path
Path(os.environ["CXOR_TASK_COMPLETION_HANDOFF_PATH"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["CXOR_TASK_COMPLETION_HANDOFF_PATH"]).write_text(json.dumps({
  "schema_version":"1.0","kind":"task_worker_completion_handoff","patchlet_id":"P0001",
  "status":"VERIFIED_NO_CHANGE_NEEDED","changed_product_runtime_file":None,
  "changed_artifact_files":[".artifacts/probes/P0001/probe.py"],
  "probe_commands":["python .artifacts/probes/P0001/probe.py"],
  "deterministic_run_counts":{"baseline":"5/5","proof_of_fix":"5/5","negative_controls":"5/5"},
  "root_cause_classification":{"observed_failure":"none","immediate_cause":"none","why_immediate_cause_happened":"already ok","deeper_owner_boundary":"target","producer_transformer_consumer_boundary":"target -> probe","not_downstream_of_unprobed_state_proof":"direct","negative_control_proof":"direct"},
  "before_after_state":[{"before":"ok","after":"ok"}],"row_ledger":[],"trace_ledger":[],
  "cleanup_proof":"ok"
}), encoding="utf-8")
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.delenv("CODEX_PATCHLET_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("CODEX_TIMEOUT_SECONDS", raising=False)

    run_dir = ctx.paths.runs_dir / "default_watchdog"
    CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    assert json.loads((run_dir / "command.json").read_text(encoding="utf-8"))["timeout_seconds"] == 600


def test_patchlet_timeout_uses_codex_patchlet_timeout_seconds_env(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ctx, patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "1")

    run_dir = ctx.paths.runs_dir / "env_timeout"
    with pytest.raises(WorkerExecutionError):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    command = json.loads((run_dir / "command.json").read_text(encoding="utf-8"))
    assert command["timeout_seconds"] == 1
    assert command["timed_out"] is True


def test_real_codex_runner_enforces_hard_wall_clock_timeout(tmp_path: Path):
    script = tmp_path / "sleep_forever.py"
    script.write_text("import time\nwhile True: time.sleep(1)\n", encoding="utf-8")

    result = CommandRunner().run([sys.executable, str(script)], cwd=tmp_path, timeout_seconds=1)

    assert result.exit_code == 124
    assert result.timed_out is True
    assert result.duration_seconds < 4


def test_streaming_jsonl_loop_enforces_timeout_while_output_continues(tmp_path: Path):
    script = tmp_path / "stream_forever.py"
    script.write_text(
        "import json, time\n"
        "i = 0\n"
        "while True:\n"
        "    print(json.dumps({'type': 'agent_message', 'i': i}), flush=True)\n"
        "    i += 1\n"
        "    time.sleep(0.05)\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    result = CommandRunner().run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout_seconds=1,
        stdout_line_callback=lambda line, _elapsed: seen.append(line),
    )

    assert result.timed_out is True
    assert result.duration_seconds < 4
    assert seen


def test_timeout_writes_attempt_timed_out_result(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, _patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "1")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    manifest = json.loads(ctx.paths.run_manifest.read_text(encoding="utf-8"))
    latest = manifest["runs"][-1]
    assert latest["lifecycle_status"] == "ATTEMPT_TIMED_OUT"
    assert latest["worker_failure"]["failure_category"] == "orchestrator_subprocess_timeout"


def test_timeout_preserves_stdout_stderr_output_jsonl_progress_jsonl(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ctx, _patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(
        fake_codex,
        """#!/usr/bin/env python3
import json, time
print(json.dumps({"type":"thread.started"}), flush=True)
time.sleep(5)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "1")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    assert (run_dir / "stdout.txt").exists()
    assert (run_dir / "stderr.txt").exists()
    assert (run_dir / "output.jsonl").exists()
    assert (run_dir / "progress.jsonl").exists()


def test_timeout_marks_state_resumable_not_stuck_in_execution_in_progress(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ctx, _patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "1")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    state = json.loads((ctx.paths.workflow_dir / "state.json").read_text(encoding="utf-8"))
    assert state["stage"] != "PATCHLET_EXECUTION_IN_PROGRESS"
    assert state["stage"] == "FAILURE_CLASSIFICATION_REQUIRED"


def test_timeout_emits_operator_event_patchlet_timed_out(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ctx, _patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "1")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    events = (ctx.paths.workflow_dir / "operator_events.jsonl").read_text(encoding="utf-8")
    assert "patchlet_timed_out" in events


def test_timeout_creates_failure_record_with_timeout_classification(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ctx, _patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "1")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    failures = sorted(ctx.paths.failures_dir.glob("F*.json"))
    assert failures
    failure = json.loads(failures[-1].read_text(encoding="utf-8"))
    assert failure["failure_signature"] == "orchestrator_subprocess_timeout"


def test_user_interrupt_marks_orchestrator_aborted_or_attempt_interrupted_with_evidence(tmp_path: Path):
    script = tmp_path / "interrupt.py"
    script.write_text("raise KeyboardInterrupt\n", encoding="utf-8")

    result = CommandRunner().run([sys.executable, str(script)], cwd=tmp_path)

    assert result.interrupted is True
    assert result.exit_code == 130


def test_resume_after_interrupted_attempt_does_not_blind_retry_without_classification(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ctx, _patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/usr/bin/env python3\nraise KeyboardInterrupt\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    manifest = json.loads(ctx.paths.run_manifest.read_text(encoding="utf-8"))
    latest = manifest["runs"][-1]
    assert latest["lifecycle_status"] == "ATTEMPT_INTERRUPTED"
    assert latest["worker_failure"]["blind_retry_allowed"] is False


def test_run_manifest_records_started_ended_duration_timeout_and_kill_signal(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ctx, _patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, "#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "1")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    latest = json.loads(ctx.paths.run_manifest.read_text(encoding="utf-8"))["runs"][-1]
    assert latest["started_at"]
    assert latest["ended_at"]
    assert latest["duration_seconds"] >= 1
    assert latest["timeout_seconds"] == 1
    assert latest["termination_signal"] in {"SIGTERM", "SIGKILL"}
