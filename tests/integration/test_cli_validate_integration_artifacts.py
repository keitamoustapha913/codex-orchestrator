from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import read_json

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.target_repo import resolve_target_repo


def _run_cli(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "codex_orchestrator", *args]
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _init_repo(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return ctx


def test_cli_validate_integration_artifacts_succeeds_for_generated_artifacts(git_repo: Path):
    _init_repo(git_repo)

    result = _run_cli(["validate-integration-artifacts", "--repo", str(git_repo)], cwd=git_repo)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "integration_artifact_validation"
    assert payload["valid"] is True


def test_cli_validate_integration_artifacts_fails_for_invalid_integration_state(git_repo: Path):
    ctx = _init_repo(git_repo)
    payload = read_json(ctx.paths.integration_state)
    payload.pop("kind")
    write_json(ctx.paths.integration_state, payload)

    result = _run_cli(["validate-integration-artifacts", "--repo", str(git_repo)], cwd=git_repo)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert any(error["schema"] == "integration_state.schema.json" for error in payload["errors"])


def test_cli_validate_integration_artifacts_outputs_structured_json(git_repo: Path):
    _init_repo(git_repo)

    result = _run_cli(["validate-integration-artifacts", "--repo", str(git_repo)], cwd=git_repo)

    payload = json.loads(result.stdout)
    assert {"schema_version", "kind", "valid", "validated", "errors"}.issubset(payload)


def test_cli_validate_integration_artifacts_is_read_only_for_product_files(git_repo: Path):
    _init_repo(git_repo)
    before = (git_repo / "app.py").read_bytes()

    result = _run_cli(["validate-integration-artifacts", "--repo", str(git_repo)], cwd=git_repo)

    assert result.returncode == 0
    assert (git_repo / "app.py").read_bytes() == before


def test_cli_validate_integration_artifacts_does_not_invoke_codex(git_repo: Path, tmp_path: Path):
    _init_repo(git_repo)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "codex_invoked"
    fake_codex = bin_dir / "codex"
    fake_codex.write_text(
        "#!/bin/sh\n"
        f"touch {marker}\n"
        "exit 99\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    result = _run_cli(["validate-integration-artifacts", "--repo", str(git_repo)], cwd=git_repo, env=env)

    assert result.returncode == 0
    assert not marker.exists()
