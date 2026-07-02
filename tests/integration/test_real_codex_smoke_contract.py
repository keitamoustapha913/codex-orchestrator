from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from codex_orchestrator.real_codex_smoke import (
    build_real_codex_auto_worktree_smoke_command,
    describe_real_codex_auto_worktree_opt_in_command,
    ensure_real_codex_smoke_prereqs,
    real_codex_smoke_enabled,
    run_real_codex_auto_worktree_smoke,
    run_real_codex_smoke,
)
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def read_json(path: Path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _write_fake_codex(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _write_fake_success_codex_from_cxor_env(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

execution_root = Path(os.environ["CXOR_EXECUTION_ROOT"])
run_dir = Path(os.environ["CXOR_RUN_DIR"])
patchlet_id = os.environ["CXOR_PATCHLET_ID"]
allowed_file = os.environ["CXOR_ALLOWED_PRODUCT_RUNTIME_FILE"]
report_path = Path(os.environ["CXOR_REPORT_PATH"])
probe_root = Path(os.environ["CXOR_PROBE_ROOT"])

run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "env.json").write_text(json.dumps(dict(os.environ), indent=2, sort_keys=True), encoding="utf-8")
(execution_root / allowed_file).write_text("def main():\\n    return 'ok'\\n# fake codex real-worker parity\\n", encoding="utf-8")
(probe_root / "run_001").mkdir(parents=True, exist_ok=True)
(probe_root / "probe.py").write_text("print('probe')\\n", encoding="utf-8")
(probe_root / "run_001" / "row_ledger.jsonl").write_text(json.dumps({"row": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "trace_ledger.jsonl").write_text(json.dumps({"trace": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "before_state.json").write_text(json.dumps({"value": "before"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "after_state.json").write_text(json.dumps({"value": "after"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "cleanup_proof.json").write_text(json.dumps({"cleanup_passed": True}) + "\\n", encoding="utf-8")
final_report = run_dir / "worker_stage" / "05_final_report.md"
final_report.parent.mkdir(parents=True, exist_ok=True)
final_report.write_text("FINAL_STATUS: PASS\\n", encoding="utf-8")
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": patchlet_id,
    "status": "COMPLETE",
    "changed_product_runtime_file": allowed_file,
    "changed_artifact_files": [
        f".artifacts/probes/{patchlet_id}/probe.py",
        f".artifacts/probes/{patchlet_id}/run_001/row_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/trace_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/before_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/after_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/cleanup_proof.json"
    ],
    "probe_commands": [f"python .artifacts/probes/{patchlet_id}/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
    "root_cause_classification": {
        "observed_failure": "baseline failed before allowed change",
        "immediate_cause": "allowed file lacked required parity change",
        "why_immediate_cause_happened": "fake real_codex parity path applies deterministic fix",
        "deeper_owner_boundary": allowed_file,
        "producer_transformer_consumer_boundary": f"producer {allowed_file} -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "probe ran directly against the changed boundary",
        "negative_control_proof": "adjacent paths remained unchanged",
        "recursive_why_audit": ["why1", "why2", "why3"]
    },
    "before_after_state": [{"before": "old", "after": "new"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe created isolated temp data and cleaned it",
    "proof_of_fix": {
        "summary": "direct probe passed after allowed change",
        "deterministic_run_count": "5/5"
    },
    "probe_artifact_refs": [{
        "patchlet_id": patchlet_id,
        "probe_root": f".artifacts/probes/{patchlet_id}",
        "run_id": "run_001"
    }],
    "acceptance_criteria_result": "pass"
}, indent=2) + "\\n", encoding="utf-8")
print(str(execution_root))
print("fake real_codex success parity", file=__import__("sys").stderr)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_contract_sensitive_fake_codex(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

run_dir = Path(os.environ["CXOR_RUN_DIR"])
run_dir.mkdir(parents=True, exist_ok=True)
prompt_arg = sys.argv[-1]
if prompt_arg == "-":
    prompt_path = run_dir / "codex_task_prompt.md"
    prompt_text = sys.stdin.read()
else:
    prompt_path = Path(prompt_arg)
    prompt_text = prompt_path.read_text(encoding="utf-8")
task_contract_path = next(
    (Path(line.split("- ", 1)[1].strip()) for line in prompt_text.splitlines() if "worker_memory/TASK_CONTRACT.md" in line),
    None,
)
task_contract_read = False
task_contract_text = ""
if task_contract_path is not None:
    if not task_contract_path.exists():
        print("missing task contract", file=sys.stderr)
        raise SystemExit(19)
    task_contract_text = task_contract_path.read_text(encoding="utf-8")
    task_contract_read = True
(run_dir / "contract_check.json").write_text(json.dumps({
    "prompt_path": str(prompt_path),
    "contract_seen": "Real Codex Patchlet Contract" in prompt_text,
    "report_path_seen": "CXOR_REPORT_PATH" in prompt_text,
    "probe_root_seen": "CXOR_PROBE_ROOT" in prompt_text,
    "allowed_file_seen": "CXOR_ALLOWED_PRODUCT_RUNTIME_FILE" in prompt_text,
    "task_contract_seen": "worker_memory/TASK_CONTRACT.md" in prompt_text,
    "task_contract_read": task_contract_read,
    "task_contract_text_seen": "orchestrator owns gate results" in task_contract_text.lower(),
    "preflight_stage_seen": "worker_stage/00_preflight.md" in prompt_text,
    "final_report_stage_seen": "worker_stage/05_final_report.md" in prompt_text,
    "wrapper_gate_seen": "The orchestrator writes gates." in prompt_text
}, indent=2, sort_keys=True), encoding="utf-8")

if "Real Codex Patchlet Contract" not in prompt_text:
    print("missing real codex contract", file=sys.stderr)
    raise SystemExit(17)

execution_root = Path(os.environ["CXOR_EXECUTION_ROOT"])
patchlet_id = os.environ["CXOR_PATCHLET_ID"]
allowed_file = os.environ["CXOR_ALLOWED_PRODUCT_RUNTIME_FILE"]
report_path = Path(os.environ["CXOR_REPORT_PATH"])
probe_root = Path(os.environ["CXOR_PROBE_ROOT"])

(execution_root / allowed_file).write_text("def main():\\n    return 'ok'\\n# contract sensitive parity\\n", encoding="utf-8")
(probe_root / "run_001").mkdir(parents=True, exist_ok=True)
(probe_root / "probe.py").write_text("print('probe')\\n", encoding="utf-8")
(probe_root / "run_001" / "row_ledger.jsonl").write_text(json.dumps({"row": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "trace_ledger.jsonl").write_text(json.dumps({"trace": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "before_state.json").write_text(json.dumps({"value": "before"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "after_state.json").write_text(json.dumps({"value": "after"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "cleanup_proof.json").write_text(json.dumps({"cleanup_passed": True}) + "\\n", encoding="utf-8")
final_report = run_dir / "worker_stage" / "05_final_report.md"
final_report.parent.mkdir(parents=True, exist_ok=True)
final_report.write_text("FINAL_STATUS: PASS\\n", encoding="utf-8")
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": patchlet_id,
    "status": "COMPLETE",
    "changed_product_runtime_file": allowed_file,
    "changed_artifact_files": [
        f".artifacts/probes/{patchlet_id}/probe.py",
        f".artifacts/probes/{patchlet_id}/run_001/row_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/trace_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/before_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/after_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/cleanup_proof.json"
    ],
    "probe_commands": [f"python .artifacts/probes/{patchlet_id}/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
    "root_cause_classification": {
        "observed_failure": "baseline failed before allowed change",
        "immediate_cause": "allowed file lacked required behavior",
        "why_immediate_cause_happened": "contract-sensitive fake codex applied deterministic fix",
        "deeper_owner_boundary": allowed_file,
        "producer_transformer_consumer_boundary": f"producer {allowed_file} -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "probe ran directly against changed boundary",
        "negative_control_proof": "adjacent paths remained unchanged",
        "recursive_why_audit": ["why1", "why2", "why3"]
    },
    "before_after_state": [{"before": "old", "after": "new"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe created isolated temp data and cleaned it",
    "proof_of_fix": {
        "summary": "direct probe passed after allowed change",
        "deterministic_run_count": "5/5"
    },
    "probe_artifact_refs": [{
        "patchlet_id": patchlet_id,
        "probe_root": f".artifacts/probes/{patchlet_id}",
        "run_id": "run_001"
    }],
    "acceptance_criteria_result": "pass"
}, indent=2) + "\\n", encoding="utf-8")
print(str(prompt_path))
print("contract present", file=sys.stderr)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _last_patchlet_run(ctx) -> dict:
    manifest = read_json(ctx.paths.run_manifest)
    patchlet_runs = [run for run in manifest["runs"] if run.get("patchlet_id") == "P0001"]
    assert patchlet_runs
    return patchlet_runs[-1]


def _first_subprompt_text(ctx) -> tuple[Path, str]:
    subprompts = sorted(ctx.paths.subprompts_dir.glob("*.md"))
    assert subprompts
    return subprompts[0], subprompts[0].read_text(encoding="utf-8")


def test_real_codex_smoke_is_skipped_without_explicit_flag():
    assert real_codex_smoke_enabled(False) is False
    assert real_codex_smoke_enabled(True) is True


def test_real_codex_auto_worktree_smoke_is_skipped_without_explicit_flag(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/smoke/test_real_codex_auto_worktree.py",
        ],
        cwd=repo_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "1 skipped" in combined or "1 skipped" in combined.lower()


def test_real_codex_smoke_requires_clean_target_repo(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    (git_repo / "app.py").write_text("def main():\n    return 'dirty'\n", encoding="utf-8")

    with pytest.raises(Exception, match="clean target repo required"):
        ensure_real_codex_smoke_prereqs(ctx, allow_real_codex=True)


def test_real_codex_smoke_requires_codex_binary(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = resolve_target_repo(repo=git_repo)
    monkeypatch.setenv("PATH", "")

    with pytest.raises(Exception, match="Codex binary not found"):
        ensure_real_codex_smoke_prereqs(ctx, allow_real_codex=True)


def test_real_codex_auto_worktree_contract_mentions_use_worktree_and_real_codex(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)

    command = build_real_codex_auto_worktree_smoke_command(
        ctx,
        master=git_repo / "master_prompt.md",
        max_iterations=150,
    )

    assert "--use-worktree" in command
    assert "--worker-mode" in command
    assert "real_codex" in command
    assert "--until" in command
    assert "DONE" in command


def test_real_codex_auto_worktree_pytest_documents_exact_opt_in_command():
    command = describe_real_codex_auto_worktree_opt_in_command()

    assert "pytest -q tests/smoke/test_real_codex_auto_worktree.py" in command
    assert "--run-real-codex" in command
    assert "-s" in command


def test_real_codex_auto_worktree_smoke_injects_patchlet_contract_into_generated_prompt(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    _, subprompt = _first_subprompt_text(ctx)
    assert "Real Codex Patchlet Contract" in subprompt


def test_real_codex_auto_worktree_smoke_prompt_mentions_cxor_report_and_probe_paths(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    _, subprompt = _first_subprompt_text(ctx)
    assert "CXOR_REPORT_PATH" in subprompt
    assert "CXOR_PROBE_ROOT" in subprompt
    assert "probe_artifact_refs" in subprompt


def test_real_codex_auto_worktree_smoke_prompt_mentions_only_allowed_product_file(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    _, subprompt = _first_subprompt_text(ctx)
    assert "CXOR_ALLOWED_PRODUCT_RUNTIME_FILE" in subprompt
    assert "Only change the allowed product/runtime file" in subprompt


def test_real_codex_auto_worktree_smoke_prompt_is_available_as_durable_artifact(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    subprompt_path, _ = _first_subprompt_text(ctx)
    assert subprompt_path.exists()
    assert subprompt_path.is_relative_to(ctx.root)


def test_real_codex_auto_worktree_smoke_success_contract_with_fake_codex(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

execution_root = Path.cwd()
artifact_root = Path(os.environ["CXOR_ARTIFACT_ROOT"])
patchlet_id = os.environ["CXOR_PATCHLET_ID"]
(execution_root / "app.py").write_text("def main():\\n    return 'ok'\\n# fake codex worktree change\\n", encoding="utf-8")
probe_root = artifact_root / ".artifacts" / "probes" / patchlet_id
(probe_root / "run_001").mkdir(parents=True, exist_ok=True)
(probe_root / "probe.py").write_text("print('probe')\\n", encoding="utf-8")
(probe_root / "run_001" / "row_ledger.jsonl").write_text(json.dumps({"row": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "trace_ledger.jsonl").write_text(json.dumps({"trace": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "before_state.json").write_text(json.dumps({"value": "before"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "after_state.json").write_text(json.dumps({"value": "after"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "cleanup_proof.json").write_text(json.dumps({"cleanup_passed": True}) + "\\n", encoding="utf-8")
final_report = artifact_root / ".codex-orchestrator" / "runs" / "P0001_attempt1" / "worker_stage" / "05_final_report.md"
final_report.parent.mkdir(parents=True, exist_ok=True)
final_report.write_text("FINAL_STATUS: PASS\\n", encoding="utf-8")
report_path = artifact_root / ".codex-orchestrator" / "reports" / f"{patchlet_id}.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": patchlet_id,
    "status": "COMPLETE",
    "changed_product_runtime_file": "app.py",
    "changed_artifact_files": [
        f".artifacts/probes/{patchlet_id}/probe.py",
        f".artifacts/probes/{patchlet_id}/run_001/row_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/trace_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/before_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/after_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/cleanup_proof.json"
    ],
    "probe_commands": [f"python .artifacts/probes/{patchlet_id}/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "baseline failed",
            "immediate_cause": "minimal fake codex change",
            "why_immediate_cause_happened": "controlled smoke path",
            "deeper_owner_boundary": "app.py",
            "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
            "not_downstream_of_unprobed_state_proof": "direct probe evidence",
            "negative_control_proof": "adjacent path unchanged",
            "recursive_why_audit": ["why1", "why2", "why3"]
        },
    "before_after_state": [{"before": "old", "after": "new"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe cleaned up temporary state",
    "probe_artifact_refs": [{
        "patchlet_id": patchlet_id,
        "probe_root": f".artifacts/probes/{patchlet_id}",
        "run_id": "run_001"
    }],
    "acceptance_criteria_result": "pass"
}, indent=2) + "\\n", encoding="utf-8")
print(str(execution_root))
print("fake codex success", file=__import__("sys").stderr)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
    )

    final = read_json(ctx.paths.final_verification_json)
    patchlet_run = _last_patchlet_run(ctx)

    assert result["worker_mode"] == "real_codex"
    assert result["use_worktree"] is True
    assert result["state_stage"] == "DONE"
    assert final["status"] == "DONE"
    assert (ctx.paths.reports_dir / "P0001.json").exists()
    assert (ctx.paths.probe_dir / "P0001" / "run_001" / "row_ledger.jsonl").exists()
    assert patchlet_run["execution_mode"] == "worktree"
    assert patchlet_run["artifact_root"] == str(ctx.root)


def test_real_codex_worker_fake_success_reaches_done_through_auto_worktree(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_success_codex_from_cxor_env(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
    )

    assert result["outcome"] == "success"
    assert result["state_stage"] == "DONE"


def test_real_codex_worker_fake_success_records_successful_run_manifest_entry(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_success_codex_from_cxor_env(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
    )

    patchlet_run = _last_patchlet_run(ctx)
    assert patchlet_run["worker_mode"] == "real_codex"
    assert patchlet_run["status"] == "COMPLETE"
    assert patchlet_run["success"] is True


def test_real_codex_worker_fake_success_records_worktree_metadata(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_success_codex_from_cxor_env(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
    )

    patchlet_run = _last_patchlet_run(ctx)
    assert patchlet_run["execution_mode"] == "worktree"
    assert patchlet_run["worktree"]["enabled"] is True
    assert patchlet_run["worktree"]["cleanup_status"] == "removed"


def test_real_codex_worker_fake_success_final_verification_is_done(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_success_codex_from_cxor_env(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
    )

    final = read_json(ctx.paths.final_verification_json)
    assert final["status"] == "DONE"


def test_real_codex_worker_fake_success_artifacts_are_under_target_root(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_success_codex_from_cxor_env(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
    )

    assert (ctx.paths.reports_dir / "P0001.json").exists()
    assert (ctx.paths.probe_dir / "P0001" / "run_001" / "cleanup_proof.json").exists()
    patchlet_run = _last_patchlet_run(ctx)
    assert patchlet_run["artifact_root"] == str(ctx.root)


def test_fake_codex_contract_sensitive_binary_fails_without_contract(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
        inject_contract=False,
    )

    contract_check = read_json(Path(result["run_dir"]) / "contract_check.json")
    assert result["outcome"] == "safe_failure"
    assert result["error_type"] == "WorkerExecutionError"
    assert contract_check["contract_seen"] is False


def test_fake_codex_contract_sensitive_binary_reaches_done_with_injected_contract(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    final = read_json(ctx.paths.final_verification_json)
    patchlet_run = _last_patchlet_run(ctx)
    contract_check = read_json(Path(result["run_dir"]) / "contract_check.json")

    assert result["outcome"] == "success"
    assert result["state_stage"] == "DONE"
    assert final["status"] == "DONE"
    assert patchlet_run["status"] == "COMPLETE"
    assert contract_check["contract_seen"] is True


def test_fake_codex_contract_sensitive_binary_records_prompt_contract_evidence(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    contract_check = read_json(Path(result["run_dir"]) / "contract_check.json")
    assert contract_check["prompt_path"] == result["prompt_artifact_path"]
    assert contract_check["contract_seen"] is True
    assert contract_check["report_path_seen"] is True
    assert contract_check["probe_root_seen"] is True
    assert contract_check["allowed_file_seen"] is True
    assert contract_check["task_contract_seen"] is True
    assert contract_check["preflight_stage_seen"] is True
    assert contract_check["final_report_stage_seen"] is True
    assert contract_check["wrapper_gate_seen"] is True


def test_real_codex_prompt_mentions_task_contract_path(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    prompt_text = Path(result["prompt_artifact_path"]).read_text(encoding="utf-8")
    assert "worker_memory/TASK_CONTRACT.md" in prompt_text


def test_real_codex_prompt_mentions_worker_stage_preflight_path(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    prompt_text = Path(result["prompt_artifact_path"]).read_text(encoding="utf-8")
    assert "worker_stage/00_preflight.md" in prompt_text


def test_real_codex_prompt_mentions_worker_stage_final_report_path(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    prompt_text = Path(result["prompt_artifact_path"]).read_text(encoding="utf-8")
    assert "worker_stage/05_final_report.md" in prompt_text


def test_real_codex_prompt_mentions_wrapper_gate_is_orchestrator_owned(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    prompt_text = Path(result["prompt_artifact_path"]).read_text(encoding="utf-8")
    assert "The orchestrator writes gates." in prompt_text


def test_real_codex_prompt_mentions_ten_minute_budget(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    prompt_text = Path(result["prompt_artifact_path"]).read_text(encoding="utf-8")
    assert "hard timeout of 600 seconds" in prompt_text
    assert "Aim to finish by 540 seconds" in prompt_text


def test_real_codex_prompt_mentions_write_final_report_before_timeout(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    prompt_text = Path(result["prompt_artifact_path"]).read_text(encoding="utf-8")
    assert "worker_stage/05_final_report.md" in prompt_text
    assert "BLOCKED or FAILED status" in prompt_text
    assert "Do not keep investigating indefinitely" in prompt_text


def test_contract_sensitive_fake_codex_reads_task_contract_and_reaches_done(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    contract_check = read_json(Path(result["run_dir"]) / "contract_check.json")
    assert result["state_stage"] == "DONE"
    assert contract_check["contract_seen"] is True
    assert contract_check["task_contract_seen"] is True
    assert contract_check["task_contract_read"] is True
    assert contract_check["task_contract_text_seen"] is True


def test_contract_sensitive_fake_codex_fails_when_task_contract_missing(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from codex_orchestrator.patchlet_run_context import build_patchlet_run_context
    from codex_orchestrator.stages.build_inventory import build_inventory
    from codex_orchestrator.stages.census import run_census
    from codex_orchestrator.stages.classify_evidence import classify_evidence
    from codex_orchestrator.stages.compile_patchlets import compile_patchlets
    from codex_orchestrator.stages.extract_invariants import extract_invariants
    from codex_orchestrator.stages.init import init_workflow
    from codex_orchestrator.stages.normalize import normalize_master_prompt
    from codex_orchestrator.errors import WorkerExecutionError
    from codex_orchestrator.workers.codex_exec import CodexExecWorker

    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][0]
    run_ctx = build_patchlet_run_context(
        ctx,
        patchlet=patchlet,
        run_id="P0001_attempt1",
        execution_root=ctx.root,
        artifact_root=ctx.root,
        is_worktree=False,
        worktree_path=None,
    )
    run_dir = ctx.paths.runs_dir / "P0001_attempt1"

    with pytest.raises(WorkerExecutionError, match="exit_code=19"):
        CodexExecWorker(codex_binary="codex").run_patchlet(ctx, patchlet, run_dir=run_dir, run_ctx=run_ctx)

    assert "missing task contract" in (run_dir / "stderr.txt").read_text(encoding="utf-8")


def test_real_codex_smoke_result_reports_worker_capsule_paths(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    assert Path(result["worker_capsule_manifest_path"]).exists()
    assert Path(result["worker_memory_dir"]).is_dir()
    assert Path(result["worker_stage_dir"]).is_dir()
    assert Path(result["wrapper_gate_result_path"]).exists()


def test_real_codex_smoke_result_reports_timeout_progress_and_model_metadata(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.delenv("CODEX_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("CODEX_PATCHLET_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("CODEX_MODEL", raising=False)
    monkeypatch.delenv("CODEX_PATCHLET_MODEL", raising=False)

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    assert result["timeout_seconds"] == 600
    assert result["timed_out"] is False
    assert result["progress_path"].endswith("progress.jsonl")
    assert result["selected_model"] == "gpt-5.4-mini"
    assert result["selected_reasoning"] == "medium"
    assert result["run_manifest_entry"]["timeout_seconds"] == 600
    assert result["run_manifest_entry"]["selected_model"] == "gpt-5.4-mini"


def test_real_codex_auto_worktree_smoke_result_reports_prompt_artifact_path(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    assert result["prompt_artifact_path"]
    assert Path(result["prompt_artifact_path"]).exists()
    assert Path(result["prompt_artifact_path"]).is_relative_to(ctx.root)


def test_real_codex_auto_worktree_smoke_result_reports_contract_injected_true(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_contract_sensitive_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    assert result["contract_template_path"].endswith("real_codex_patchlet_contract.md")
    assert result["contract_injected"] is True


def test_real_codex_auto_worktree_smoke_safe_failure_reports_contract_prompt_context(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    assert result["outcome"] == "safe_failure"
    assert result["prompt_artifact_path"]
    assert Path(result["prompt_artifact_path"]).exists()
    assert result["contract_template_path"].endswith("real_codex_patchlet_contract.md")
    assert result["contract_injected"] is True


def test_real_codex_auto_worktree_smoke_safe_failure_contract_with_fake_codex(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
print("fake codex worker failure", file=sys.stderr)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    assert result["worker_mode"] == "real_codex"
    assert result["use_worktree"] is True
    assert result["state_stage"] != "DONE"
    assert result["error_type"] in {"WorkerExecutionError", "RuntimeError"}
    assert Path(result["stdout_path"]).exists()
    assert Path(result["stderr_path"]).exists()
    assert Path(result["command_path"]).exists()
    assert Path(result["output_jsonl_path"]).exists()


def test_real_codex_auto_worktree_safe_failure_contract_records_run_manifest_entry_with_fake_codex(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
print("fake codex worker failure", file=sys.stderr)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    manifest = read_json(Path(result["run_manifest_path"]))
    patchlet_runs = [run for run in manifest["runs"] if run.get("patchlet_id") == "P0001"]

    assert result["outcome"] == "safe_failure"
    assert len(patchlet_runs) == 1
    assert patchlet_runs[0]["status"] == "WORKER_FAILED"
    assert patchlet_runs[0]["worker_failure"]["type"] == "WorkerExecutionError"
    assert patchlet_runs[0]["execution_mode"] == "worktree"
    assert patchlet_runs[0]["worktree"]["enabled"] is True


def test_real_codex_auto_worktree_safe_failure_result_reports_manifest_entry(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
print("fake codex worker failure", file=sys.stderr)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    assert result["outcome"] == "safe_failure"
    assert result["run_manifest_path"]
    assert result["run_manifest_entry"]["patchlet_id"] == "P0001"
    assert result["run_manifest_entry"]["status"] == "WORKER_FAILED"
    assert result["run_manifest_entry"]["worker_failure"]["blind_retry_allowed"] is False


def test_real_codex_auto_worktree_safe_failure_writes_diagnosis_artifacts_with_fake_codex(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
print("authentication failed: session expired", file=sys.stderr)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    assert result["outcome"] == "safe_failure"
    assert Path(result["diagnosis_json_path"]).exists()
    assert Path(result["diagnosis_md_path"]).exists()


def test_real_codex_auto_worktree_safe_failure_result_reports_diagnosis_paths(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    assert result["diagnosis_json_path"]
    assert result["diagnosis_md_path"]
    assert result["diagnosis_primary_category"]
    assert result["diagnosis_summary"]


def test_real_codex_auto_worktree_safe_failure_diagnosis_links_run_manifest_entry(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    diagnosis = read_json(Path(result["diagnosis_json_path"]))
    assert diagnosis["attempt_id"] == result["run_manifest_entry"]["attempt_id"]
    assert diagnosis["evidence_paths"]["run_manifest"].endswith("run_manifest.json")


def test_real_codex_auto_worktree_safe_failure_diagnosis_mentions_prompt_artifact_when_present(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
    )

    diagnosis = read_json(Path(result["diagnosis_json_path"]))
    assert diagnosis["artifact_presence"]["prompt_artifact"] is True
    assert diagnosis["evidence_paths"]["prompt_artifact"].endswith(".md")


def test_real_codex_auto_worktree_smoke_preserves_target_on_unauthorized_fake_codex_diff(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    other = git_repo / "other.py"
    other.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "add", "other.py"], check=True)
    subprocess.run(
        ["git", "-C", str(git_repo), "commit", "-m", "add other"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    app_hash_before = Path(git_repo / "app.py").read_text(encoding="utf-8")
    other_hash_before = Path(other).read_text(encoding="utf-8")
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

execution_root = Path.cwd()
artifact_root = Path(os.environ["CXOR_ARTIFACT_ROOT"])
patchlet_id = os.environ["CXOR_PATCHLET_ID"]
(execution_root / "other.py").write_text("value = 2\\n", encoding="utf-8")
probe_root = artifact_root / ".artifacts" / "probes" / patchlet_id
(probe_root / "run_001").mkdir(parents=True, exist_ok=True)
(probe_root / "probe.py").write_text("print('probe')\\n", encoding="utf-8")
(probe_root / "run_001" / "row_ledger.jsonl").write_text(json.dumps({"row": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "trace_ledger.jsonl").write_text(json.dumps({"trace": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "before_state.json").write_text(json.dumps({"value": "before"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "after_state.json").write_text(json.dumps({"value": "after"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "cleanup_proof.json").write_text(json.dumps({"cleanup_passed": True}) + "\\n", encoding="utf-8")
report_path = artifact_root / ".codex-orchestrator" / "reports" / f"{patchlet_id}.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": patchlet_id,
    "status": "COMPLETE",
    "changed_product_runtime_file": "app.py",
    "changed_artifact_files": [
        f".artifacts/probes/{patchlet_id}/probe.py",
        f".artifacts/probes/{patchlet_id}/run_001/row_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/trace_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/before_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/after_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/cleanup_proof.json"
    ],
    "probe_commands": [f"python .artifacts/probes/{patchlet_id}/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "baseline failed",
            "immediate_cause": "unauthorized change",
            "why_immediate_cause_happened": "controlled smoke path",
            "deeper_owner_boundary": "other.py",
            "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
            "not_downstream_of_unprobed_state_proof": "direct probe evidence",
            "negative_control_proof": "adjacent path unchanged",
            "recursive_why_audit": ["why1", "why2", "why3"]
        },
    "before_after_state": [{"before": "old", "after": "new"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe cleaned up temporary state",
    "probe_artifact_refs": [{
        "patchlet_id": patchlet_id,
        "probe_root": f".artifacts/probes/{patchlet_id}",
        "run_id": "run_001"
    }],
    "acceptance_criteria_result": "pass"
}, indent=2) + "\\n", encoding="utf-8")
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
        max_iterations=25,
        until="FAILURE_CLASSIFICATION_REQUIRED",
    )

    assert result["state_stage"] == "FAILURE_CLASSIFICATION_REQUIRED"
    assert (ctx.paths.failures_dir / "F0001.json").exists()
    assert (ctx.paths.runs_dir / "P0001_attempt1" / "diff.patch").exists()
    assert (git_repo / "app.py").read_text(encoding="utf-8") == app_hash_before
    assert other.read_text(encoding="utf-8") == other_hash_before


def test_real_codex_auto_worktree_smoke_writes_artifacts_to_target_not_worktree(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

execution_root = Path.cwd()
artifact_root = Path(os.environ["CXOR_ARTIFACT_ROOT"])
patchlet_id = os.environ["CXOR_PATCHLET_ID"]
(execution_root / "app.py").write_text("def main():\\n    return 'ok'\\n# fake codex worktree change\\n", encoding="utf-8")
probe_root = artifact_root / ".artifacts" / "probes" / patchlet_id
(probe_root / "run_001").mkdir(parents=True, exist_ok=True)
(probe_root / "probe.py").write_text("print('probe')\\n", encoding="utf-8")
(probe_root / "run_001" / "row_ledger.jsonl").write_text(json.dumps({"row": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "trace_ledger.jsonl").write_text(json.dumps({"trace": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "before_state.json").write_text(json.dumps({"value": "before"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "after_state.json").write_text(json.dumps({"value": "after"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "cleanup_proof.json").write_text(json.dumps({"cleanup_passed": True}) + "\\n", encoding="utf-8")
report_path = artifact_root / ".codex-orchestrator" / "reports" / f"{patchlet_id}.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": patchlet_id,
    "status": "COMPLETE",
    "changed_product_runtime_file": "app.py",
    "changed_artifact_files": [
        f".artifacts/probes/{patchlet_id}/probe.py",
        f".artifacts/probes/{patchlet_id}/run_001/row_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/trace_ledger.jsonl",
        f".artifacts/probes/{patchlet_id}/run_001/before_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/after_state.json",
        f".artifacts/probes/{patchlet_id}/run_001/cleanup_proof.json"
    ],
    "probe_commands": [f"python .artifacts/probes/{patchlet_id}/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "baseline failed",
            "immediate_cause": "minimal fake codex change",
            "why_immediate_cause_happened": "controlled smoke path",
            "deeper_owner_boundary": "app.py",
            "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
            "not_downstream_of_unprobed_state_proof": "direct probe evidence",
            "negative_control_proof": "adjacent path unchanged",
            "recursive_why_audit": ["why1", "why2", "why3"]
        },
    "before_after_state": [{"before": "old", "after": "new"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe cleaned up temporary state",
    "probe_artifact_refs": [{
        "patchlet_id": patchlet_id,
        "probe_root": f".artifacts/probes/{patchlet_id}",
        "run_id": "run_001"
    }],
    "acceptance_criteria_result": "pass"
}, indent=2) + "\\n", encoding="utf-8")
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
    )

    patchlet_run = _last_patchlet_run(ctx)
    assert patchlet_run["artifact_root"] == str(ctx.root)
    assert (ctx.paths.reports_dir / "P0001.json").exists()
    assert (ctx.paths.probe_dir / "P0001" / "run_001" / "cleanup_proof.json").exists()


def test_real_codex_smoke_uses_diff_and_report_validation(git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
from pathlib import Path

repo = Path.cwd()
report_path = repo / ".codex-orchestrator" / "reports" / "P0001.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
probe_root = repo / ".artifacts" / "probes" / "P0001"
(probe_root / "run_001").mkdir(parents=True, exist_ok=True)
(probe_root / "probe.py").write_text("print('probe')\\n", encoding="utf-8")
(probe_root / "run_001" / "row_ledger.jsonl").write_text(json.dumps({"row": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "trace_ledger.jsonl").write_text(json.dumps({"trace": 1}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "before_state.json").write_text(json.dumps({"value": "before"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "after_state.json").write_text(json.dumps({"value": "after"}) + "\\n", encoding="utf-8")
(probe_root / "run_001" / "cleanup_proof.json").write_text(json.dumps({"cleanup_passed": True}) + "\\n", encoding="utf-8")
report_path.write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": "P0001",
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [
        ".artifacts/probes/P0001/probe.py",
        ".artifacts/probes/P0001/run_001/row_ledger.jsonl",
        ".artifacts/probes/P0001/run_001/trace_ledger.jsonl",
        ".artifacts/probes/P0001/run_001/before_state.json",
        ".artifacts/probes/P0001/run_001/after_state.json",
        ".artifacts/probes/P0001/run_001/cleanup_proof.json"
    ],
    "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
    "root_cause_classification": {
        "observed_failure": "baseline failed",
        "immediate_cause": "investigation only",
        "why_immediate_cause_happened": "manual smoke validation",
        "deeper_owner_boundary": "app.main",
        "producer_transformer_consumer_boundary": "producer app.main -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "direct probe evidence",
        "negative_control_proof": "unrelated branch unchanged"
    },
    "before_after_state": [{"before": "ok", "after": "ok"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe created isolated temp data and cleaned it",
    "probe_artifact_refs": [{
        "patchlet_id": "P0001",
        "probe_root": ".artifacts/probes/P0001",
        "run_id": "run_001"
    }],
    "acceptance_criteria_result": "pass"
}, indent=2) + "\\n", encoding="utf-8")
print(str(repo))
print("fake codex stderr", file=__import__("sys").stderr)
""",
    )
    monkeypatch.setenv("PATH", f"{fake_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=True,
        codex_binary="codex",
    )

    report_path = Path(result["report_path"])
    stdout_path = Path(result["stdout_path"])
    stderr_path = Path(result["stderr_path"])
    command_path = Path(result["command_path"])
    output_jsonl_path = Path(result["output_jsonl_path"])

    assert result["worker_mode"] == "real_codex"
    assert result["state_stage"] == "PATCHLET_EXECUTION_COMPLETE"
    assert report_path.exists()
    assert stdout_path.exists()
    assert stderr_path.exists()
    assert command_path.exists()
    assert output_jsonl_path.exists()
    assert validate_json_file(report_path, "patchlet_report.schema.json") == []
    assert str(git_repo) in stdout_path.read_text(encoding="utf-8")
    assert "fake codex stderr" in stderr_path.read_text(encoding="utf-8")
    index = read_json(ctx.paths.patchlet_index)
    assert index["patchlets"][0]["patchlet_id"] == "P0001"
    assert index["patchlets"][0]["status"] == "VERIFIED_NO_CHANGE_NEEDED"
