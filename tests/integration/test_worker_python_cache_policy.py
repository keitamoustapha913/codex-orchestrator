from __future__ import annotations

import os
import subprocess
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


def _compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _write_env_capturing_codex(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

patchlet_id = os.environ["CXOR_PATCHLET_ID"]
run_dir = Path(os.environ["CXOR_RUN_DIR"])
probe_root = Path(os.environ["CXOR_PROBE_ROOT"])
probe_run = probe_root / "run_001"
probe_run.mkdir(parents=True, exist_ok=True)
(probe_root / "probe.py").write_text("print('probe passed')\\n", encoding="utf-8")
for name, payload in {
    "row_ledger.jsonl": '{"row": 1}\\n',
    "trace_ledger.jsonl": '{"trace": 1}\\n',
    "before_state.json": '{"state": "before"}\\n',
    "after_state.json": '{"state": "after"}\\n',
    "cleanup_proof.json": '{"cleanup_passed": true}\\n',
}.items():
    (probe_run / name).write_text(payload, encoding="utf-8")

Path(os.environ["CXOR_PREFLIGHT_PATH"]).write_text("preflight", encoding="utf-8")
Path(os.environ["CXOR_FINAL_REPORT_PATH"]).write_text("FINAL_STATUS: PASS\\n", encoding="utf-8")
(run_dir / "env_capture.json").write_text(json.dumps({
    "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE")
}), encoding="utf-8")
report = {
    "schema_version": "1.0",
    "kind": "task_worker_completion_handoff",
    "patchlet_id": patchlet_id,
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [f".artifacts/probes/{patchlet_id}/probe.py"],
    "probe_commands": [f"PYTHONDONTWRITEBYTECODE=1 python -B .artifacts/probes/{patchlet_id}/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
    "root_cause_classification": {
        "observed_failure": "no change needed",
        "immediate_cause": "already ok",
        "why_immediate_cause_happened": "probe passed",
        "deeper_owner_boundary": "app.py",
        "producer_transformer_consumer_boundary": "app.py -> probe",
        "not_downstream_of_unprobed_state_proof": "direct probe",
        "negative_control_proof": "negative control",
        "recursive_why_audit": []
    },
    "before_after_state": [{"before": "ok", "after": "ok"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "cleanup ok",
    "probe_artifact_refs": [{"patchlet_id": patchlet_id, "probe_root": f".artifacts/probes/{patchlet_id}", "run_id": "run_001"}],
}
Path(os.environ["CXOR_TASK_COMPLETION_HANDOFF_PATH"]).write_text(json.dumps(report), encoding="utf-8")
print(json.dumps({"type": "turn.completed"}), flush=True)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _run_fake_real_codex(git_repo: Path, tmp_path: Path, monkeypatch):
    fake = tmp_path / "codex"
    _write_env_capturing_codex(fake)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    ctx = _compiled_ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)
    return ctx


def test_real_codex_worker_env_sets_python_dont_write_bytecode(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _run_fake_real_codex(git_repo, tmp_path, monkeypatch)

    env_capture = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "env_capture.json")
    command = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "command.json")
    assert env_capture["PYTHONDONTWRITEBYTECODE"] == "1"
    assert command["env"]["PYTHONDONTWRITEBYTECODE"] == "1"


def test_fake_codex_worker_env_sets_python_dont_write_bytecode(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _run_fake_real_codex(git_repo, tmp_path, monkeypatch)

    env_capture = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "env_capture.json")
    assert env_capture["PYTHONDONTWRITEBYTECODE"] == "1"


def test_worker_capsule_writes_runtime_side_effect_contract(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _run_fake_real_codex(git_repo, tmp_path, monkeypatch)

    contract = ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "RUNTIME_SIDE_EFFECT_CONTRACT.md"
    assert contract.exists()
    text = contract.read_text(encoding="utf-8")
    assert "language-runtime cache or build byproduct files" in text
    assert "target-root product/runtime files" in text


def test_task_contract_references_runtime_side_effect_contract(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _run_fake_real_codex(git_repo, tmp_path, monkeypatch)

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "TASK_CONTRACT.md").read_text(encoding="utf-8")
    assert "RUNTIME_SIDE_EFFECT_CONTRACT.md" in text
    assert "PYTHON_RUNTIME_SIDE_EFFECT_CONTRACT.md" not in text


def test_write_these_files_references_runtime_side_effect_contract(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _run_fake_real_codex(git_repo, tmp_path, monkeypatch)

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "WRITE_THESE_FILES.md").read_text(encoding="utf-8")
    assert "RUNTIME_SIDE_EFFECT_CONTRACT.md" in text
    assert "PYTHON_RUNTIME_SIDE_EFFECT_CONTRACT.md" not in text


def test_generated_prompt_mentions_runtime_byproduct_policy(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _run_fake_real_codex(git_repo, tmp_path, monkeypatch)

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "codex_task_prompt.md").read_text(encoding="utf-8")
    assert "language-runtime caches or build byproducts" in text
    assert "PYTHONDONTWRITEBYTECODE=1" not in text


def test_generated_prompt_forbids_target_root_runtime_mutation(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _run_fake_real_codex(git_repo, tmp_path, monkeypatch)

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "codex_task_prompt.md").read_text(encoding="utf-8")
    assert "Do not load target-root product/runtime files in a way that mutates target-root state." in text
    assert "python -B" not in text


def test_generated_prompt_warns_not_to_leave_target_root_runtime_byproducts(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _run_fake_real_codex(git_repo, tmp_path, monkeypatch)

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "codex_task_prompt.md").read_text(encoding="utf-8")
    assert "runtime byproduct leaks" in text
    assert "Do not leave __pycache__/ anywhere under target root" not in text


def test_fake_worker_import_with_env_does_not_create_target_pycache(git_repo: Path):
    subprocess.run(
        [
            os.environ.get("PYTHON", "python"),
            "-c",
            "import importlib.util; p='app.py'; s=importlib.util.spec_from_file_location('app', p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)",
        ],
        cwd=git_repo,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    assert not (git_repo / "__pycache__").exists()


def test_runtime_side_effect_contract_is_present_for_repair_patchlets(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _run_fake_real_codex(git_repo, tmp_path, monkeypatch)

    assert (ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "RUNTIME_SIDE_EFFECT_CONTRACT.md").exists()
