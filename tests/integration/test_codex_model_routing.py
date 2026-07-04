from __future__ import annotations

import json
import os
from pathlib import Path

from codex_orchestrator.codex_model_profile import resolve_codex_model_profile
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
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


def _successful_fake_codex() -> str:
    return """#!/usr/bin/env python3
import json, os
from pathlib import Path
Path(os.environ["CXOR_REPORT_PATH"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["CXOR_REPORT_PATH"]).write_text(json.dumps({
  "schema_version":"1.0","kind":"patchlet_report","patchlet_id":"P0001",
  "status":"VERIFIED_NO_CHANGE_NEEDED","changed_product_runtime_file":None,
  "changed_artifact_files":[".artifacts/probes/P0001/probe.py"],
  "probe_commands":["python .artifacts/probes/P0001/probe.py"],
  "deterministic_run_counts":{"baseline":"5/5","proof_of_fix":"5/5","negative_controls":"5/5"},
  "root_cause_classification":{"observed_failure":"none","immediate_cause":"none","why_immediate_cause_happened":"already ok","deeper_owner_boundary":"target","producer_transformer_consumer_boundary":"target -> probe","not_downstream_of_unprobed_state_proof":"direct","negative_control_proof":"direct"},
  "before_after_state":[{"before":"ok","after":"ok"}],"row_ledger":[],"trace_ledger":[],
  "cleanup_proof":"ok","acceptance_criteria_result":"pass"
}), encoding="utf-8")
"""


def test_patchlet_worker_defaults_to_gpt_5_4_mini_medium():
    profile = resolve_codex_model_profile("patchlet", {})
    assert profile.model == "gpt-5.4-mini"
    assert profile.reasoning == "medium"


def test_patchlet_worker_respects_explicit_codex_model_env():
    assert resolve_codex_model_profile("patchlet", {"CODEX_MODEL": "custom-model"}).model == "custom-model"


def test_patchlet_worker_respects_explicit_codex_reasoning_env():
    assert resolve_codex_model_profile("patchlet", {"CODEX_REASONING": "high"}).reasoning == "high"


def test_planning_and_verifier_defaults_to_gpt_5_5_medium():
    profile = resolve_codex_model_profile("orchestrator", {})
    assert profile.model == "gpt-5.5"
    assert profile.reasoning == "medium"


def test_planning_and_verifier_respects_explicit_model_env():
    assert resolve_codex_model_profile("orchestrator", {"CODEX_MODEL": "planner-model"}).model == "planner-model"


def test_model_routing_recorded_in_command_json(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, _successful_fake_codex())
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "model_command"
    CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)

    command = json.loads((run_dir / "command.json").read_text(encoding="utf-8"))
    assert command["selected_model"] == "gpt-5.4-mini"
    assert command["selected_reasoning"] == "medium"


def test_model_routing_recorded_in_run_manifest(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, _successful_fake_codex())
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_dir = ctx.paths.runs_dir / "model_manifest"
    CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)
    command = json.loads((run_dir / "command.json").read_text(encoding="utf-8"))

    assert command["selected_model"] == "gpt-5.4-mini"
    assert command["selected_reasoning"] == "medium"


def test_worker_prompt_records_model_and_reasoning_policy_without_leaking_secrets(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, _successful_fake_codex())
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")

    run_dir = ctx.paths.runs_dir / "model_prompt"
    CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)
    text = (run_dir / "codex_task_prompt.md").read_text(encoding="utf-8")

    assert "gpt-5.4-mini" in json.dumps(json.loads((run_dir / "command.json").read_text(encoding="utf-8")))
    assert "secret-value" not in text
