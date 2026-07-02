from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from codex_orchestrator.errors import WorkerExecutionError, WorkerPreconditionError
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workers.codex_exec import CodexExecWorker


def setup_patchlet_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet_index = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))
    return ctx, patchlet_index["patchlets"][0]


def write_fake_codex(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_codex_worker_runs_with_target_repo_as_cwd_and_records_outputs(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, patchlet = setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

cwd = Path.cwd()
print(cwd)
print("fake codex diagnostic", file=sys.stderr)
report = {
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": "P0001",
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [".artifacts/probes/P0001/probe.py"],
    "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
    "root_cause_classification": {
        "observed_failure": "probe confirmed no change needed",
        "immediate_cause": "no change required",
        "why_immediate_cause_happened": "target already satisfies invariant",
        "deeper_owner_boundary": "app.py",
        "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "probe ran directly against the boundary",
        "negative_control_proof": "negative control passed"
    },
    "before_after_state": [{"before": "ok", "after": "ok"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe cleaned up temporary state",
    "acceptance_criteria_result": "pass"
}
(cwd / ".codex-orchestrator" / "reports").mkdir(parents=True, exist_ok=True)
(cwd / ".codex-orchestrator" / "reports" / "P0001.json").write_text(json.dumps(report), encoding="utf-8")
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "real_codex_test"
    result = CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    command = json.loads((run_dir / "command.json").read_text(encoding="utf-8"))
    output = json.loads((run_dir / "output.jsonl").read_text(encoding="utf-8").strip())
    assert result.exit_code == 0
    assert result.report_path == ctx.paths.reports_dir / "P0001.json"
    assert (run_dir / "stdout.txt").read_text(encoding="utf-8").strip() == str(ctx.root)
    assert "fake codex diagnostic" in (run_dir / "stderr.txt").read_text(encoding="utf-8")
    assert command["cwd"] == str(ctx.root)
    assert command["target_repo_root"] == str(ctx.root)
    assert command["patchlet_id"] == "P0001"
    assert output["cwd"] == str(ctx.root)
    assert output["target_repo_root"] == str(ctx.root)
    assert command["repo_sha_before"] == command["repo_sha_after"]


def test_codex_worker_records_stdout_stderr_jsonl_and_exit_code(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, patchlet = setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

print("stdout-marker")
print("stderr-marker", file=sys.stderr)
cwd = Path.cwd()
report = {
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": "P0001",
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [".artifacts/probes/P0001/probe.py"],
    "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
    "root_cause_classification": {
        "observed_failure": "probe confirmed no change needed",
        "immediate_cause": "no change required",
        "why_immediate_cause_happened": "target already satisfies invariant",
        "deeper_owner_boundary": "app.py",
        "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "probe ran directly against the boundary",
        "negative_control_proof": "negative control passed"
    },
    "before_after_state": [{"before": "ok", "after": "ok"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe cleaned up temporary state",
    "acceptance_criteria_result": "pass"
}
(cwd / ".codex-orchestrator" / "reports").mkdir(parents=True, exist_ok=True)
(cwd / ".codex-orchestrator" / "reports" / "P0001.json").write_text(json.dumps(report), encoding="utf-8")
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "real_codex_capture"
    CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    output = json.loads((run_dir / "output.jsonl").read_text(encoding="utf-8").strip())
    assert "stdout-marker" in (run_dir / "stdout.txt").read_text(encoding="utf-8")
    assert "stderr-marker" in (run_dir / "stderr.txt").read_text(encoding="utf-8")
    assert output["exit_code"] == 0
    assert output["stdout_path"].endswith("stdout.txt")
    assert output["stderr_path"].endswith("stderr.txt")


def test_codex_worker_nonzero_exit_becomes_structured_worker_failure(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, patchlet = setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
print("worker failed", file=sys.stderr)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "real_codex_failure"
    with pytest.raises(WorkerExecutionError, match="exit_code=17"):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    assert "worker failed" in (run_dir / "stderr.txt").read_text(encoding="utf-8")
    command = json.loads((run_dir / "command.json").read_text(encoding="utf-8"))
    assert command["exit_code"] == 17


def test_codex_worker_timeout_becomes_structured_worker_failure(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, patchlet = setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import time
time.sleep(5)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_TIMEOUT_SECONDS", "1")

    run_dir = ctx.paths.runs_dir / "real_codex_timeout"
    with pytest.raises(WorkerExecutionError, match="timed out after 1s"):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    command = json.loads((run_dir / "command.json").read_text(encoding="utf-8"))
    output = json.loads((run_dir / "output.jsonl").read_text(encoding="utf-8").strip())
    assert command["exit_code"] == 124
    assert command["timed_out"] is True
    assert output["timeout_seconds"] == 1
    assert "timed out after 1 seconds" in (run_dir / "stderr.txt").read_text(encoding="utf-8")


def test_codex_worker_does_not_write_into_orchestrator_source_repo(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, patchlet = setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    source_repo_report = Path(__file__).resolve().parents[2] / ".codex-orchestrator" / "reports" / "P0001.json"
    if source_repo_report.exists():
        source_repo_report.unlink()
    write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
from pathlib import Path

cwd = Path.cwd()
report = {
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": "P0001",
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [".artifacts/probes/P0001/probe.py"],
    "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
    "root_cause_classification": {
        "observed_failure": "probe confirmed no change needed",
        "immediate_cause": "no change required",
        "why_immediate_cause_happened": "target already satisfies invariant",
        "deeper_owner_boundary": "app.py",
        "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "probe ran directly against the boundary",
        "negative_control_proof": "negative control passed"
    },
    "before_after_state": [{"before": "ok", "after": "ok"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe cleaned up temporary state",
    "acceptance_criteria_result": "pass"
}
(cwd / ".codex-orchestrator" / "reports").mkdir(parents=True, exist_ok=True)
(cwd / ".codex-orchestrator" / "reports" / "P0001.json").write_text(json.dumps(report), encoding="utf-8")
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "real_codex_target_only"
    CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    assert (ctx.paths.reports_dir / "P0001.json").exists()
    assert not source_repo_report.exists()


def test_codex_worker_missing_binary_reports_structured_precondition_error(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    ctx, patchlet = setup_patchlet_ctx(git_repo)
    monkeypatch.setenv("PATH", "")

    with pytest.raises(WorkerPreconditionError, match="Codex binary not found"):
        CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=ctx.paths.runs_dir / "missing_binary")
