from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.real_codex_operator_runbook import (
    CommandCapture,
    parse_smoke_stdout,
    run_real_codex_smoke_runbook,
)


FIXED_TIMESTAMP = "2026-07-02T18-45-00"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "codex_orchestrator", *args]
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def fake_runner_factory(calls: list[list[str]], explicit_stdout: str | None = None):
    def fake_runner(args: list[str], cwd: Path, env: dict[str, str]) -> CommandCapture:
        calls.append(args)
        if args[:2] == ["git", "status"]:
            return CommandCapture(exit_code=0, stdout="", stderr="")
        if args[:2] == ["codex", "--version"]:
            return CommandCapture(exit_code=0, stdout="codex-cli 0.142.4\n", stderr="")
        if "--run-real-codex" in args:
            return CommandCapture(exit_code=0, stdout=explicit_stdout or "", stderr="explicit stderr\n")
        return CommandCapture(exit_code=0, stdout="s\n1 skipped in 0.01s\n", stderr="")

    return fake_runner


def test_operator_runbook_dry_run_creates_timestamped_artifact_dir(tmp_path: Path):
    calls: list[list[str]] = []

    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=FIXED_TIMESTAMP,
        dry_run=True,
        run_real_codex=False,
        runner=fake_runner_factory(calls),
    )

    run_dir = Path(result["operator_run_dir"])
    assert run_dir == tmp_path / "runs" / "real-codex-smoke" / f"{FIXED_TIMESTAMP}-real-codex-smoke"
    assert run_dir.is_dir()


def test_operator_runbook_writes_environment_git_status_codex_version_and_policy(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=FIXED_TIMESTAMP,
        dry_run=True,
        run_real_codex=False,
        runner=fake_runner_factory([]),
    )

    run_dir = Path(result["operator_run_dir"])
    assert (run_dir / "environment.txt").exists()
    assert (run_dir / "git_status.txt").read_text(encoding="utf-8") == ""
    assert (run_dir / "codex_version.txt").read_text(encoding="utf-8") == "codex-cli 0.142.4\n"
    policy = read_json(run_dir / "selected_policy.json")
    assert policy["kind"] == "real_codex_smoke_selected_policy"
    assert policy["codex_patchlet_timeout_seconds"] == 600
    assert policy["codex_model"] == "gpt-5.4-mini"
    assert policy["codex_reasoning"] == "medium"
    assert policy["codex_progress_interval_seconds"] == 30
    assert policy["dry_run"] is True
    assert policy["run_real_codex"] is False


def test_operator_runbook_dry_run_writes_default_skip_outputs(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=FIXED_TIMESTAMP,
        dry_run=True,
        run_real_codex=False,
        runner=fake_runner_factory([]),
    )

    run_dir = Path(result["operator_run_dir"])
    assert "1 skipped" in (run_dir / "default_skip_stdout.txt").read_text(encoding="utf-8")
    assert (run_dir / "default_skip_stderr.txt").read_text(encoding="utf-8") == ""


def test_operator_runbook_dry_run_does_not_run_real_codex(tmp_path: Path):
    calls: list[list[str]] = []

    run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=FIXED_TIMESTAMP,
        dry_run=True,
        run_real_codex=False,
        runner=fake_runner_factory(calls),
    )

    assert all("--run-real-codex" not in call for call in calls)
    explicit_stdout = tmp_path / "runs" / "real-codex-smoke" / f"{FIXED_TIMESTAMP}-real-codex-smoke" / "explicit_smoke_stdout.txt"
    assert "explicit real Codex smoke was not run" in explicit_stdout.read_text(encoding="utf-8")


def test_operator_runbook_result_json_records_dry_run_outcome(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=FIXED_TIMESTAMP,
        dry_run=True,
        run_real_codex=False,
        runner=fake_runner_factory([]),
    )

    payload = read_json(Path(result["operator_run_dir"]) / "result.json")
    assert payload["outcome"] == "dry_run"
    assert payload["default_skip"] == {"exit_code": 0, "skipped": True}
    assert payload["explicit_smoke"] == {"run": False, "exit_code": None, "outcome": "not_run"}
    assert payload["diagnosis_paths"] == []


def test_cli_real_codex_runbook_dry_run_outputs_operator_run_dir(tmp_path: Path):
    result = run_cli(
        [
            "real-codex-smoke-runbook",
            "--dry-run",
            "--operator-root",
            str(tmp_path / "runs"),
            "--timestamp",
            FIXED_TIMESTAMP,
            "--default-skip-command",
            f"{sys.executable} -c \"print('s\\n1 skipped in 0.01s')\"",
        ],
        cwd=Path(__file__).resolve().parents[2],
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "dry_run"
    assert "operator_run_dir" in payload


def test_cli_real_codex_runbook_explicit_mode_requires_flag(tmp_path: Path):
    result = run_cli(["real-codex-smoke-runbook", "--operator-root", str(tmp_path / "runs")], cwd=tmp_path)

    assert result.returncode == 2
    assert "one of the arguments --dry-run --run-real-codex is required" in result.stderr


def test_cli_real_codex_runbook_fake_success_records_success_result(tmp_path: Path):
    smoke_script = tmp_path / "fake_success.py"
    smoke_script.write_text(
        "import json\n"
        "print(json.dumps({'outcome': 'success', 'state_stage': 'DONE', 'run_manifest_path': 'manifest.json'}))\n",
        encoding="utf-8",
    )

    result = run_cli(
        [
            "real-codex-smoke-runbook",
            "--run-real-codex",
            "--operator-root",
            str(tmp_path / "runs"),
            "--timestamp",
            FIXED_TIMESTAMP,
            "--default-skip-command",
            f"{sys.executable} -c \"print('s\\n1 skipped in 0.01s')\"",
            "--explicit-smoke-command",
            f"{sys.executable} {smoke_script}",
        ],
        cwd=Path(__file__).resolve().parents[2],
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "success"
    result_path = Path(payload["operator_run_dir"]) / "result.json"
    assert read_json(result_path)["explicit_smoke"]["outcome"] == "success"


def test_cli_real_codex_runbook_fake_safe_failure_records_diagnosis_paths(tmp_path: Path):
    diagnosis_json = tmp_path / "diagnosis.json"
    diagnosis_md = tmp_path / "diagnosis.md"
    diagnosis_json.write_text('{"primary_category":"network_or_api_error"}\n', encoding="utf-8")
    diagnosis_md.write_text("# Diagnosis\n", encoding="utf-8")
    smoke_script = tmp_path / "fake_safe_failure.py"
    smoke_script.write_text(
        "import json\n"
        f"print(json.dumps({{'outcome': 'safe_failure', 'diagnosis_json_path': {str(diagnosis_json)!r}, "
        f"'diagnosis_md_path': {str(diagnosis_md)!r}, 'run_manifest_path': 'manifest.json'}}))\n",
        encoding="utf-8",
    )

    result = run_cli(
        [
            "real-codex-smoke-runbook",
            "--run-real-codex",
            "--operator-root",
            str(tmp_path / "runs"),
            "--timestamp",
            FIXED_TIMESTAMP,
            "--default-skip-command",
            f"{sys.executable} -c \"print('s\\n1 skipped in 0.01s')\"",
            "--explicit-smoke-command",
            f"{sys.executable} {smoke_script}",
        ],
        cwd=Path(__file__).resolve().parents[2],
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    run_dir = Path(payload["operator_run_dir"])
    diagnosis_paths = read_json(run_dir / "diagnosis_paths.json")
    assert diagnosis_paths["diagnosis_json_path"] == str(diagnosis_json)
    assert diagnosis_paths["copied_diagnosis_json"] == "diagnosis.json"
    assert (run_dir / "diagnosis.json").exists()
    assert (run_dir / "diagnosis.md").exists()


def test_cli_real_codex_runbook_is_read_only_for_product_files(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    product_like_file = repo_root / "pyproject.toml"
    before = hashlib.sha256(product_like_file.read_bytes()).hexdigest()

    result = run_cli(
        [
            "real-codex-smoke-runbook",
            "--dry-run",
            "--operator-root",
            str(tmp_path / "runs"),
            "--timestamp",
            FIXED_TIMESTAMP,
            "--default-skip-command",
            f"{sys.executable} -c \"print('s\\n1 skipped in 0.01s')\"",
        ],
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr
    after = hashlib.sha256(product_like_file.read_bytes()).hexdigest()
    assert after == before


def test_operator_runbook_parses_smoke_json_stdout():
    stdout = "prefix\n{\"outcome\": \"safe_failure\", \"diagnosis_json_path\": \"diagnosis.json\"}\n1 passed\n"

    parsed, error = parse_smoke_stdout(stdout)

    assert error is None
    assert parsed["outcome"] == "safe_failure"
    assert parsed["diagnosis_json_path"] == "diagnosis.json"


def test_operator_runbook_records_parse_error_for_non_json_stdout(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=FIXED_TIMESTAMP,
        dry_run=False,
        run_real_codex=True,
        runner=fake_runner_factory([], explicit_stdout="not json\n"),
    )

    payload = read_json(Path(result["operator_run_dir"]) / "result.json")
    assert payload["explicit_smoke"]["outcome"] == "unparsed"
    assert "parse_error" in payload["explicit_smoke"]


def test_operator_runbook_copies_diagnosis_artifacts_when_present(tmp_path: Path):
    diagnosis_json = tmp_path / "source_diagnosis.json"
    diagnosis_md = tmp_path / "source_diagnosis.md"
    diagnosis_json.write_text('{"primary_category":"network_or_api_error"}\n', encoding="utf-8")
    diagnosis_md.write_text("# Diagnosis\n", encoding="utf-8")
    stdout = json.dumps(
        {
            "outcome": "safe_failure",
            "diagnosis_json_path": str(diagnosis_json),
            "diagnosis_md_path": str(diagnosis_md),
            "progress_path": "progress.jsonl",
        }
    )

    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=FIXED_TIMESTAMP,
        dry_run=False,
        run_real_codex=True,
        runner=fake_runner_factory([], explicit_stdout=stdout),
    )

    run_dir = Path(result["operator_run_dir"])
    diagnosis_paths = read_json(run_dir / "diagnosis_paths.json")
    assert diagnosis_paths["copied_diagnosis_json"] == "diagnosis.json"
    assert diagnosis_paths["copied_diagnosis_md"] == "diagnosis.md"
    assert (run_dir / "diagnosis.json").read_text(encoding="utf-8") == diagnosis_json.read_text(encoding="utf-8")
    assert (run_dir / "diagnosis.md").read_text(encoding="utf-8") == diagnosis_md.read_text(encoding="utf-8")


def test_operator_runbook_preserves_raw_stdout_and_stderr_even_when_parse_fails(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp=FIXED_TIMESTAMP,
        dry_run=False,
        run_real_codex=True,
        runner=fake_runner_factory([], explicit_stdout="plain output\n"),
    )

    run_dir = Path(result["operator_run_dir"])
    assert (run_dir / "explicit_smoke_stdout.txt").read_text(encoding="utf-8") == "plain output\n"
    assert (run_dir / "explicit_smoke_stderr.txt").read_text(encoding="utf-8") == "explicit stderr\n"
