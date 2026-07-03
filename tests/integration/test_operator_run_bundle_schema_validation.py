from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.real_codex_operator_runbook import CommandCapture, run_real_codex_smoke_runbook
from codex_orchestrator.validators.schema_validator import validate_json, validate_json_file


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


def _without(payload: dict, key: str) -> dict:
    copy = dict(payload)
    copy.pop(key, None)
    return copy


def test_generated_selected_policy_validates_against_schema(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    assert validate_json_file(run_dir / "selected_policy.json", "real_codex_smoke_selected_policy.schema.json") == []


def test_selected_policy_schema_rejects_missing_kind(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "selected_policy.json")

    assert validate_json(_without(payload, "kind"), "real_codex_smoke_selected_policy.schema.json")


def test_selected_policy_schema_rejects_wrong_kind(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "selected_policy.json")
    payload["kind"] = "wrong"

    assert validate_json(payload, "real_codex_smoke_selected_policy.schema.json")


def test_selected_policy_schema_rejects_negative_timeout(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "selected_policy.json")
    payload["codex_patchlet_timeout_seconds"] = -1

    assert validate_json(payload, "real_codex_smoke_selected_policy.schema.json")


def test_selected_policy_schema_rejects_non_boolean_dry_run(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "selected_policy.json")
    payload["dry_run"] = "true"

    assert validate_json(payload, "real_codex_smoke_selected_policy.schema.json")


def test_selected_policy_schema_rejects_non_boolean_run_real_codex(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "selected_policy.json")
    payload["run_real_codex"] = "false"

    assert validate_json(payload, "real_codex_smoke_selected_policy.schema.json")


def test_generated_dry_run_result_validates_against_schema(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    assert validate_json_file(run_dir / "result.json", "real_codex_smoke_operator_result.schema.json") == []


def test_operator_result_schema_rejects_missing_outcome(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "result.json")

    assert validate_json(_without(payload, "outcome"), "real_codex_smoke_operator_result.schema.json")


def test_operator_result_schema_rejects_wrong_kind(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "result.json")
    payload["kind"] = "wrong"

    assert validate_json(payload, "real_codex_smoke_operator_result.schema.json")


def test_operator_result_schema_rejects_invalid_outcome(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "result.json")
    payload["outcome"] = "done"

    assert validate_json(payload, "real_codex_smoke_operator_result.schema.json")


def test_operator_result_schema_rejects_missing_default_skip(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "result.json")

    assert validate_json(_without(payload, "default_skip"), "real_codex_smoke_operator_result.schema.json")


def test_operator_result_schema_rejects_dry_run_with_explicit_smoke_run_true(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "result.json")
    payload["explicit_smoke"]["run"] = True

    assert validate_json(payload, "real_codex_smoke_operator_result.schema.json")


def test_generated_dry_run_diagnosis_paths_validates_against_schema(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    assert validate_json_file(run_dir / "diagnosis_paths.json", "real_codex_smoke_diagnosis_paths.schema.json") == []


def test_diagnosis_paths_schema_accepts_null_paths_for_dry_run(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "diagnosis_paths.json")

    assert validate_json(payload, "real_codex_smoke_diagnosis_paths.schema.json") == []


def test_diagnosis_paths_schema_accepts_string_paths_for_safe_failure(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "diagnosis_paths.json")
    payload["diagnosis_json_path"] = "/tmp/diagnosis.json"
    payload["diagnosis_md_path"] = "/tmp/diagnosis.md"
    payload["copied_diagnosis_json"] = "diagnosis.json"
    payload["copied_diagnosis_md"] = "diagnosis.md"

    assert validate_json(payload, "real_codex_smoke_diagnosis_paths.schema.json") == []


def test_diagnosis_paths_schema_rejects_wrong_kind(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "diagnosis_paths.json")
    payload["kind"] = "wrong"

    assert validate_json(payload, "real_codex_smoke_diagnosis_paths.schema.json")


def test_diagnosis_paths_schema_rejects_non_string_non_null_path(tmp_path: Path):
    payload = _read_json(_dry_run_bundle(tmp_path) / "diagnosis_paths.json")
    payload["progress_path"] = 123

    assert validate_json(payload, "real_codex_smoke_diagnosis_paths.schema.json")


def test_generated_runbook_validation_result_validates_against_schema(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    assert validate_json_file(run_dir / "validation_result.json", "real_codex_smoke_runbook_validation.schema.json") == []
