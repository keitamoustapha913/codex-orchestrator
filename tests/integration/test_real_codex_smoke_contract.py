from __future__ import annotations

import os
from pathlib import Path

import pytest

from codex_orchestrator.real_codex_smoke import (
    ensure_real_codex_smoke_prereqs,
    real_codex_smoke_enabled,
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


def test_real_codex_smoke_is_skipped_without_explicit_flag():
    assert real_codex_smoke_enabled(False) is False
    assert real_codex_smoke_enabled(True) is True


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
report_path.write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": "P0001",
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [".artifacts/probes/P0001/probe.py"],
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
