from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.real_codex_operator_runbook import CommandCapture, run_real_codex_smoke_runbook
from codex_orchestrator.validators.real_codex_smoke_runbook_validator import validate_real_codex_smoke_runbook


FIXED_TIMESTAMP = "2026-07-02T18-45-00"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fake_runner(args: list[str], cwd: Path, env: dict[str, str]) -> CommandCapture:
    if args[:2] == ["git", "status"]:
        return CommandCapture(exit_code=0, stdout="", stderr="")
    if args[:2] == ["codex", "--version"]:
        return CommandCapture(exit_code=0, stdout="codex-cli 0.142.4\n", stderr="")
    return CommandCapture(exit_code=0, stdout="s\n1 skipped in 0.01s\n", stderr="")


def _dry_run_bundle(tmp_path: Path) -> Path:
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=FIXED_TIMESTAMP,
        dry_run=True,
        run_real_codex=False,
        runner=_fake_runner,
    )
    return Path(result["operator_run_dir"])


def _hash_tree(path: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = file_path.relative_to(path).as_posix()
        hashes[rel] = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return hashes


def test_operator_run_bundle_validator_requires_all_core_files(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "selected_policy.json").unlink()

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["path"] == "selected_policy.json" for error in result["errors"])


def test_operator_run_bundle_validator_allows_empty_git_status_for_clean_repo(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "git_status.txt").write_text("", encoding="utf-8")

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is True


def test_operator_run_bundle_validator_allows_empty_stderr_files(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "default_skip_stderr.txt").write_text("", encoding="utf-8")
    (run_dir / "explicit_smoke_stderr.txt").write_text("", encoding="utf-8")

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is True


def test_operator_run_bundle_validator_requires_non_empty_environment(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "environment.txt").write_text("", encoding="utf-8")

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["path"] == "environment.txt" for error in result["errors"])


def test_operator_run_bundle_validator_requires_non_empty_codex_version(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "codex_version.txt").write_text("", encoding="utf-8")

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["path"] == "codex_version.txt" for error in result["errors"])


def test_operator_run_bundle_validator_requires_default_skip_stdout_to_show_skip(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "default_skip_stdout.txt").write_text("passed\n", encoding="utf-8")

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["path"] == "default_skip_stdout.txt" for error in result["errors"])


def test_operator_run_bundle_validator_requires_explicit_smoke_stdout_placeholder_for_dry_run(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "explicit_smoke_stdout.txt").write_text("", encoding="utf-8")

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["path"] == "explicit_smoke_stdout.txt" for error in result["errors"])


def test_validate_operator_run_bundle_accepts_generated_dry_run_bundle(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["kind"] == "real_codex_smoke_runbook_validation"
    assert result["valid"] is True
    assert result["validated"]["required_files"] is True


def test_validate_operator_run_bundle_reports_missing_selected_policy(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "selected_policy.json").unlink()

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert result["validated"]["selected_policy"] is False


def test_validate_operator_run_bundle_reports_invalid_selected_policy_schema(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    payload = _read_json(run_dir / "selected_policy.json")
    payload["dry_run"] = "true"
    write_json(run_dir / "selected_policy.json", payload)

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["schema"] == "real_codex_smoke_selected_policy.schema.json" for error in result["errors"])


def test_validate_operator_run_bundle_reports_invalid_result_schema(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    payload = _read_json(run_dir / "result.json")
    payload["outcome"] = "done"
    write_json(run_dir / "result.json", payload)

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["schema"] == "real_codex_smoke_operator_result.schema.json" for error in result["errors"])


def test_validate_operator_run_bundle_reports_invalid_diagnosis_paths_schema(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    payload = _read_json(run_dir / "diagnosis_paths.json")
    payload["progress_path"] = 123
    write_json(run_dir / "diagnosis_paths.json", payload)

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["schema"] == "real_codex_smoke_diagnosis_paths.schema.json" for error in result["errors"])


def test_validate_operator_run_bundle_reports_missing_explicit_stdout(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "explicit_smoke_stdout.txt").unlink()

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["path"] == "explicit_smoke_stdout.txt" for error in result["errors"])


def test_validate_operator_run_bundle_reports_missing_copied_diagnosis_file_when_referenced(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    payload = _read_json(run_dir / "diagnosis_paths.json")
    payload["copied_diagnosis_json"] = "diagnosis.json"
    write_json(run_dir / "diagnosis_paths.json", payload)

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert any(error["path"] == "diagnosis.json" for error in result["errors"])


def test_validate_operator_run_bundle_returns_structured_errors(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "result.json").unlink()

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["errors"]
    assert {"path", "schema", "message"}.issubset(result["errors"][0])


def test_validate_operator_run_bundle_is_read_only(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    before = _hash_tree(run_dir)

    validate_real_codex_smoke_runbook(run_dir)

    assert _hash_tree(run_dir) == before


def test_validate_operator_run_bundle_does_not_invoke_codex(tmp_path: Path, monkeypatch):
    run_dir = _dry_run_bundle(tmp_path)
    marker = tmp_path / "codex_invoked"
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    fake_codex = tmp_path / "codex"
    fake_codex.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    fake_codex.chmod(0o755)

    result = validate_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is True
    assert not marker.exists()
