from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import read_json

from codex_orchestrator.target_hygiene import run_target_hygiene_gate


def _status(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--short"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _run_gate(repo: Path, *, allowed_file: str | None = "app.py"):
    run_dir = repo / ".codex-orchestrator" / "runs" / "P0001_attempt1"
    return run_target_hygiene_gate(
        target_repo_root=repo,
        workflow_dir=repo / ".codex-orchestrator",
        probe_dir=repo / ".artifacts" / "probes",
        run_dir=run_dir,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
        allowed_product_runtime_file=allowed_file,
    )


def test_target_hygiene_gate_accepts_only_artifact_dirs(git_repo: Path):
    (git_repo / ".codex-orchestrator").mkdir()
    (git_repo / ".artifacts" / "probes").mkdir(parents=True)

    result = _run_gate(git_repo)

    assert result["accepted"] is True
    assert result["product_runtime_clean"] is True
    assert result["unknown_dirty_paths"] == []
    assert result["whole_repo_clean_after_hygiene"] is True


def test_target_hygiene_gate_detects_and_removes_pycache(git_repo: Path):
    cache_dir = git_repo / "__pycache__"
    cache_dir.mkdir()
    cache_file = cache_dir / "app.cpython-310.pyc"
    cache_file.write_bytes(b"cache")

    result = _run_gate(git_repo)

    assert result["accepted"] is True
    assert result["cache_artifacts_detected"][0]["path"] == "__pycache__/app.cpython-310.pyc"
    assert result["cache_artifacts_removed"][0]["path"] == "__pycache__/app.cpython-310.pyc"
    assert not cache_dir.exists()


def test_target_hygiene_gate_records_removed_cache_hashes(git_repo: Path):
    cache_dir = git_repo / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "app.cpython-310.pyc").write_bytes(b"cache")

    result = _run_gate(git_repo)

    detected = result["cache_artifacts_detected"][0]
    assert detected["size_bytes"] == 5
    assert len(detected["sha256"]) == 64
    assert detected["tracked"] is False
    assert detected["cleanup_action"] == "remove"


def test_target_hygiene_gate_rechecks_git_status_after_cache_cleanup(git_repo: Path):
    (git_repo / "__pycache__").mkdir()
    (git_repo / "__pycache__" / "app.cpython-310.pyc").write_bytes(b"cache")

    result = _run_gate(git_repo)

    assert any("__pycache__/" in line for line in result["git_status_before_hygiene"])
    assert all("__pycache__/" not in line for line in result["git_status_after_hygiene"])


def test_target_hygiene_gate_rejects_unknown_dirty_path(git_repo: Path):
    (git_repo / "tmp.txt").write_text("unknown", encoding="utf-8")

    result = _run_gate(git_repo)

    assert result["accepted"] is False
    assert result["unknown_dirty_paths"] == ["tmp.txt"]
    assert (git_repo / "tmp.txt").exists()


def test_target_hygiene_gate_rejects_tracked_product_runtime_dirty_file(git_repo: Path):
    (git_repo / "app.py").write_text("def main():\n    return 'dirty'\n", encoding="utf-8")

    result = _run_gate(git_repo)

    assert result["accepted"] is False
    assert result["product_runtime_dirty_paths"] == ["app.py"]
    assert "dirty" in (git_repo / "app.py").read_text(encoding="utf-8")


def test_target_hygiene_gate_rejects_untracked_product_runtime_file(git_repo: Path):
    (git_repo / "generated.py").write_text("print('x')\n", encoding="utf-8")

    result = _run_gate(git_repo)

    assert result["accepted"] is False
    assert result["product_runtime_dirty_paths"] == ["generated.py"]
    assert (git_repo / "generated.py").exists()


def test_target_hygiene_gate_does_not_delete_unknown_untracked_file(git_repo: Path):
    (git_repo / "tmp.txt").write_text("unknown", encoding="utf-8")

    _run_gate(git_repo)

    assert (git_repo / "tmp.txt").exists()


def test_target_hygiene_gate_does_not_delete_tracked_file(git_repo: Path):
    (git_repo / "app.py").write_text("def main():\n    return 'dirty'\n", encoding="utf-8")

    _run_gate(git_repo)

    assert (git_repo / "app.py").exists()


def test_target_hygiene_gate_does_not_delete_probe_artifacts(git_repo: Path):
    probe = git_repo / ".artifacts" / "probes" / "P0001" / "probe.py"
    probe.parent.mkdir(parents=True)
    probe.write_text("print('probe')\n", encoding="utf-8")

    result = _run_gate(git_repo)

    assert result["accepted"] is True
    assert probe.exists()


def test_target_hygiene_gate_does_not_delete_workflow_artifacts(git_repo: Path):
    artifact = git_repo / ".codex-orchestrator" / "README.md"
    artifact.parent.mkdir()
    artifact.write_text("evidence\n", encoding="utf-8")

    result = _run_gate(git_repo)

    assert result["accepted"] is True
    assert artifact.exists()


def test_target_hygiene_gate_writes_result_json(git_repo: Path):
    result = _run_gate(git_repo)
    path = git_repo / result["result_path"]

    assert path.exists()
    assert read_json(path)["kind"] == "target_hygiene_gate_result"


def test_target_hygiene_gate_result_json_contains_before_and_after_status(git_repo: Path):
    result = _run_gate(git_repo)

    assert "git_status_before_hygiene" in result
    assert "git_status_after_hygiene" in result


def test_target_hygiene_gate_result_json_contains_cache_evidence(git_repo: Path):
    cache_dir = git_repo / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "app.cpython-310.pyc").write_bytes(b"cache")

    result = _run_gate(git_repo)

    assert result["cache_artifacts_detected"]
    assert result["cache_artifacts_removed"]
    assert "sha256" in result["cache_artifacts_detected"][0]


def test_scratch_quarantine_does_not_allow_executable_root_file(git_repo: Path):
    path = git_repo / "report_check.sh"
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)

    result = _run_gate(git_repo)

    assert result["accepted"] is False
    assert "report_check.sh" in result["unknown_dirty_paths"]


def test_scratch_quarantine_result_is_included_in_wrapper_gate_diagnostics(git_repo: Path):
    run_dir = git_repo / ".codex-orchestrator" / "runs" / "P0001_attempt1"
    gates = run_dir / "gates"
    gates.mkdir(parents=True)
    path = gates / "scratch_artifact_quarantine_result.json"
    path.write_text('{"kind":"scratch_artifact_quarantine_result","quarantined":[],"rejected":[]}', encoding="utf-8")

    assert path.exists()
