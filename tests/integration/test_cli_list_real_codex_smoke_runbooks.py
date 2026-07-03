from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.real_codex_operator_runbook import CommandCapture, run_real_codex_smoke_runbook


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


def _run_cli(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    command = [sys.executable, "-m", "codex_orchestrator", *args]
    selected_env = os.environ.copy() if env is None else env
    selected_env["PYTHONPATH"] = str(repo_root / "src") + (
        os.pathsep + selected_env["PYTHONPATH"] if selected_env.get("PYTHONPATH") else ""
    )
    return subprocess.run(
        command,
        cwd=cwd,
        env=selected_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _hash_tree(path: Path) -> dict[str, str]:
    return {
        file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(p for p in path.rglob("*") if p.is_file())
    }


def test_cli_list_real_codex_smoke_runbooks_json_outputs_structured_result(tmp_path: Path):
    _dry_run_bundle(tmp_path)
    root = tmp_path / "runs" / "real-codex-smoke"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--json"], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "real_codex_smoke_runbook_list"
    assert payload["count"] == 1


def test_cli_list_real_codex_smoke_runbooks_json_includes_generated_dry_run_bundle(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    root = tmp_path / "runs" / "real-codex-smoke"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--json"], cwd=tmp_path)

    payload = json.loads(result.stdout)
    assert payload["bundles"][0]["run_dir"] == str(run_dir)
    assert payload["bundles"][0]["outcome"] == "dry_run"


def test_cli_list_real_codex_smoke_runbooks_custom_root(tmp_path: Path):
    _dry_run_bundle(tmp_path)
    root = tmp_path / "runs" / "real-codex-smoke"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--json"], cwd=Path.cwd())

    payload = json.loads(result.stdout)
    assert payload["root"] == str(root)


def test_cli_list_real_codex_smoke_runbooks_missing_root_outputs_empty_result(tmp_path: Path):
    root = tmp_path / "missing"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--json"], cwd=tmp_path)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 0
    assert payload["bundles"] == []


def test_cli_list_real_codex_smoke_runbooks_does_not_invoke_codex(tmp_path: Path):
    _dry_run_bundle(tmp_path)
    root = tmp_path / "runs" / "real-codex-smoke"
    marker = tmp_path / "codex_invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(f"#!/bin/sh\ntouch {marker}\nexit 99\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--json"], cwd=tmp_path, env=env)

    assert result.returncode == 0
    assert not marker.exists()


def test_cli_list_real_codex_smoke_runbooks_is_read_only(tmp_path: Path):
    _dry_run_bundle(tmp_path)
    root = tmp_path / "runs" / "real-codex-smoke"
    before = _hash_tree(root)

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--json"], cwd=tmp_path)

    assert result.returncode == 0
    assert _hash_tree(root) == before


def test_cli_list_real_codex_smoke_runbooks_human_output_contains_header(tmp_path: Path):
    _dry_run_bundle(tmp_path)
    root = tmp_path / "runs" / "real-codex-smoke"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root)], cwd=tmp_path)

    assert "Run timestamp" in result.stdout
    assert "Outcome" in result.stdout


def test_cli_list_real_codex_smoke_runbooks_human_output_contains_outcome_and_validation(tmp_path: Path):
    _dry_run_bundle(tmp_path)
    root = tmp_path / "runs" / "real-codex-smoke"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root)], cwd=tmp_path)

    assert "dry_run" in result.stdout
    assert "yes" in result.stdout


def test_cli_list_real_codex_smoke_runbooks_human_output_mentions_json_hint(tmp_path: Path):
    _dry_run_bundle(tmp_path)
    root = tmp_path / "runs" / "real-codex-smoke"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root)], cwd=tmp_path)

    assert "Use --json for full paths and validation details." in result.stdout


def test_cli_list_real_codex_smoke_runbooks_human_output_handles_no_bundles(tmp_path: Path):
    root = tmp_path / "missing"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root)], cwd=tmp_path)

    assert "No real-Codex smoke runbooks found" in result.stdout


def test_cli_list_real_codex_smoke_runbooks_human_output_handles_invalid_bundle(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    (root / "2026-07-02T18-45-00-real-codex-smoke").mkdir(parents=True)

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root)], cwd=tmp_path)

    assert "invalid" in result.stdout
    assert "unknown" in result.stdout


def test_cli_latest_json_returns_one_bundle(tmp_path: Path):
    _dry_run_bundle(tmp_path, "2026-07-02T18-45-00")
    _dry_run_bundle(tmp_path, "2026-07-02T18-46-00")
    root = tmp_path / "runs" / "real-codex-smoke"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--latest", "--json"], cwd=tmp_path)

    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["bundles"][0]["timestamp"] == "2026-07-02T18-46-00"


def test_filters_work_with_human_output(tmp_path: Path):
    _dry_run_bundle(tmp_path, "2026-07-02T18-45-00")
    root = tmp_path / "runs" / "real-codex-smoke"
    (root / "2026-07-02T18-46-00-real-codex-smoke").mkdir(parents=True)

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--only-invalid"], cwd=tmp_path)

    assert "invalid" in result.stdout
    assert "dry_run" not in result.stdout


def test_filters_work_with_json_output(tmp_path: Path):
    _dry_run_bundle(tmp_path, "2026-07-02T18-45-00")
    _dry_run_bundle(tmp_path, "2026-07-02T18-46-00")
    root = tmp_path / "runs" / "real-codex-smoke"

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--limit", "1", "--json"], cwd=tmp_path)

    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["bundles"][0]["timestamp"] == "2026-07-02T18-46-00"


def test_cli_json_reports_malformed_bundle_errors(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    (root / "2026-07-02T18-45-00-real-codex-smoke").mkdir(parents=True)

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root), "--json"], cwd=tmp_path)

    payload = json.loads(result.stdout)
    assert payload["bundles"][0]["valid"] is False
    assert payload["bundles"][0]["errors"]


def test_cli_human_reports_malformed_bundle_as_invalid(tmp_path: Path):
    root = tmp_path / "runs" / "real-codex-smoke"
    (root / "2026-07-02T18-45-00-real-codex-smoke").mkdir(parents=True)

    result = _run_cli(["list-real-codex-smoke-runbooks", "--root", str(root)], cwd=tmp_path)

    assert "invalid" in result.stdout
