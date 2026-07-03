from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from codex_orchestrator.real_codex_operator_runbook import CommandCapture, run_real_codex_smoke_runbook
from codex_orchestrator.real_codex_smoke_runbook_listing import (
    list_real_codex_smoke_runbooks,
    summarize_real_codex_smoke_runbook,
)


def _fake_runner(args: list[str], cwd: Path, env: dict[str, str]) -> CommandCapture:
    if args[:2] == ["git", "status"]:
        return CommandCapture(exit_code=0, stdout="", stderr="")
    if args[:2] == ["codex", "--version"]:
        return CommandCapture(exit_code=0, stdout="codex-cli 0.142.4\n", stderr="")
    return CommandCapture(exit_code=0, stdout="s\n1 skipped in 0.01s\n", stderr="")


def _dry_run_bundle(tmp_path: Path, timestamp: str = "2026-07-02T18-45-00") -> Path:
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=timestamp,
        dry_run=True,
        run_real_codex=False,
        runner=_fake_runner,
    )
    return Path(result["operator_run_dir"])


def _hash_tree(path: Path) -> dict[str, str]:
    return {
        file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(p for p in path.rglob("*") if p.is_file())
    }


def test_summarize_generated_dry_run_bundle(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    summary = summarize_real_codex_smoke_runbook(run_dir)

    assert summary["kind"] == "real_codex_smoke_runbook_summary"
    assert summary["valid"] is True
    assert summary["outcome"] == "dry_run"


def test_summary_includes_run_dir_timestamp_outcome_and_validation_status(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    summary = summarize_real_codex_smoke_runbook(run_dir)

    assert summary["run_dir"] == str(run_dir)
    assert summary["timestamp"] == "2026-07-02T18-45-00"
    assert summary["name"] == "2026-07-02T18-45-00-real-codex-smoke"
    assert summary["validation_status"] == "valid"


def test_summary_includes_selected_model_reasoning_and_timeout(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    summary = summarize_real_codex_smoke_runbook(run_dir)

    assert summary["selected_policy"]["model"] == "gpt-5.4-mini"
    assert summary["selected_policy"]["reasoning"] == "medium"
    assert summary["selected_policy"]["timeout_seconds"] == 600


def test_summary_includes_result_policy_diagnosis_and_validation_paths(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    summary = summarize_real_codex_smoke_runbook(run_dir)

    assert summary["paths"] == {
        "result": "result.json",
        "selected_policy": "selected_policy.json",
        "diagnosis_paths": "diagnosis_paths.json",
        "validation_result": "validation_result.json",
    }


def test_summary_handles_missing_diagnosis_category_as_null(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    summary = summarize_real_codex_smoke_runbook(run_dir)

    assert summary["diagnosis_primary_category"] is None
    assert summary["timed_out"] is None


def test_list_real_codex_smoke_runbooks_returns_all_bundles(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    _dry_run_bundle(tmp_path, "2026-07-02T18-45-00")
    _dry_run_bundle(tmp_path, "2026-07-02T18-46-00")

    result = list_real_codex_smoke_runbooks(root)

    assert result["count"] == 2
    assert len(result["bundles"]) == 2


def test_list_real_codex_smoke_runbooks_sorts_newest_first(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    _dry_run_bundle(tmp_path, "2026-07-02T18-45-00")
    _dry_run_bundle(tmp_path, "2026-07-02T18-46-00")

    result = list_real_codex_smoke_runbooks(root)

    assert [bundle["timestamp"] for bundle in result["bundles"]] == [
        "2026-07-02T18-46-00",
        "2026-07-02T18-45-00",
    ]


def test_list_real_codex_smoke_runbooks_handles_missing_root(tmp_path: Path):
    result = list_real_codex_smoke_runbooks(tmp_path / "missing")

    assert result["count"] == 0
    assert result["valid_count"] == 0
    assert result["invalid_count"] == 0
    assert result["bundles"] == []


def test_list_real_codex_smoke_runbooks_counts_valid_and_invalid_bundles(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    _dry_run_bundle(tmp_path, "2026-07-02T18-45-00")
    invalid = root / "2026-07-02T18-46-00-real-codex-smoke"
    invalid.mkdir(parents=True)

    result = list_real_codex_smoke_runbooks(root)

    assert result["valid_count"] == 1
    assert result["invalid_count"] == 1


def test_list_real_codex_smoke_runbooks_is_read_only(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    _dry_run_bundle(tmp_path)
    before = _hash_tree(root)

    list_real_codex_smoke_runbooks(root)

    assert _hash_tree(root) == before


def test_list_real_codex_smoke_runbooks_does_not_invoke_codex(tmp_path: Path, monkeypatch):
    root = tmp_path / "runs" / "real-codex-smoke"
    _dry_run_bundle(tmp_path)
    marker = tmp_path / "codex_invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(f"#!/bin/sh\ntouch {marker}\nexit 99\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")

    list_real_codex_smoke_runbooks(root)

    assert not marker.exists()


def test_list_latest_returns_newest_bundle_only(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    _dry_run_bundle(tmp_path, "2026-07-02T18-45-00")
    _dry_run_bundle(tmp_path, "2026-07-02T18-46-00")

    result = list_real_codex_smoke_runbooks(root, latest=True)

    assert result["count"] == 1
    assert result["bundles"][0]["timestamp"] == "2026-07-02T18-46-00"


def test_only_invalid_filters_valid_bundles(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    _dry_run_bundle(tmp_path, "2026-07-02T18-45-00")
    (root / "2026-07-02T18-46-00-real-codex-smoke").mkdir(parents=True)

    result = list_real_codex_smoke_runbooks(root, only_invalid=True)

    assert result["count"] == 1
    assert result["bundles"][0]["valid"] is False


def test_limit_restricts_bundle_count_after_sorting(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    _dry_run_bundle(tmp_path, "2026-07-02T18-45-00")
    _dry_run_bundle(tmp_path, "2026-07-02T18-46-00")

    result = list_real_codex_smoke_runbooks(root, limit=1)

    assert result["count"] == 1
    assert result["bundles"][0]["timestamp"] == "2026-07-02T18-46-00"


def test_listing_includes_bundle_missing_result_as_invalid(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "result.json").unlink()

    result = list_real_codex_smoke_runbooks(root)

    assert result["bundles"][0]["valid"] is False
    assert any(error["path"] == "result.json" for error in result["bundles"][0]["errors"])


def test_listing_includes_bundle_with_invalid_json_as_invalid(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "result.json").write_text("{not json", encoding="utf-8")

    result = list_real_codex_smoke_runbooks(root)

    assert result["bundles"][0]["valid"] is False
    assert any("invalid JSON" in error["message"] for error in result["bundles"][0]["errors"])


def test_listing_handles_missing_validation_result(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "validation_result.json").unlink()

    result = list_real_codex_smoke_runbooks(root)

    assert result["bundles"][0]["valid"] is False
    assert result["bundles"][0]["paths"]["validation_result"] is None


def test_listing_handles_non_timestamped_directory(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    manual = root / "manual-run"
    manual.mkdir(parents=True)

    result = list_real_codex_smoke_runbooks(root)

    assert result["bundles"][0]["timestamp"] is None
    assert result["bundles"][0]["name"] == "manual-run"
    assert result["bundles"][0]["valid"] is False
