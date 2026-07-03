from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.real_codex_operator_runbook import CommandCapture, run_real_codex_smoke_runbook


FIXED_TIMESTAMP = "2026-07-02T18-45-00"


def _fake_runner(args: list[str], cwd: Path, env: dict[str, str]) -> CommandCapture:
    if args[:2] == ["git", "status"]:
        return CommandCapture(exit_code=0, stdout="", stderr="")
    if args[:2] == ["codex", "--version"]:
        return CommandCapture(exit_code=0, stdout="codex-cli 0.142.4\n", stderr="")
    return CommandCapture(exit_code=0, stdout="s\n1 skipped in 0.01s\n", stderr="")


def _dry_run_bundle(tmp_path: Path) -> Path:
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / ".operator-runs",
        timestamp=FIXED_TIMESTAMP,
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
        for file in sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink())
    }


def test_cli_export_real_codex_smoke_runbook_succeeds_for_valid_bundle(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = _run_cli(["export-real-codex-smoke-runbook", "--run-dir", str(run_dir)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["exported"] is True
    assert Path(payload["archive_path"]).exists()


def test_cli_export_real_codex_smoke_runbook_outputs_structured_json(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = _run_cli(["export-real-codex-smoke-runbook", "--run-dir", str(run_dir)], cwd=tmp_path)

    payload = json.loads(result.stdout)
    assert {"schema_version", "kind", "valid", "exported", "archive_path", "manifest_path"}.issubset(payload)


def test_cli_export_real_codex_smoke_runbook_respects_out_path(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    out_path = tmp_path / "custom.zip"

    result = _run_cli(["export-real-codex-smoke-runbook", "--run-dir", str(run_dir), "--out", str(out_path)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["archive_path"]) == out_path
    assert out_path.exists()


def test_cli_export_real_codex_smoke_runbook_refuses_invalid_bundle(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "result.json").unlink()

    result = _run_cli(["export-real-codex-smoke-runbook", "--run-dir", str(run_dir)], cwd=tmp_path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["exported"] is False


def test_cli_export_real_codex_smoke_runbook_force_exports_invalid_bundle(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "result.json").unlink()

    result = _run_cli(["export-real-codex-smoke-runbook", "--run-dir", str(run_dir), "--force"], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["exported"] is True
    assert payload["valid"] is False


def test_cli_export_real_codex_smoke_runbook_is_read_only(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    before = _hash_tree(run_dir)

    result = _run_cli(["export-real-codex-smoke-runbook", "--run-dir", str(run_dir)], cwd=tmp_path)

    assert result.returncode == 0
    assert _hash_tree(run_dir) == before


def test_cli_export_real_codex_smoke_runbook_does_not_invoke_codex(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    marker = tmp_path / "codex_invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(f"#!/bin/sh\ntouch {marker}\nexit 99\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

    result = _run_cli(["export-real-codex-smoke-runbook", "--run-dir", str(run_dir)], cwd=tmp_path, env=env)

    assert result.returncode == 0
    assert not marker.exists()
