from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

from codex_orchestrator.real_codex_operator_runbook import CommandCapture, run_real_codex_smoke_runbook
from codex_orchestrator.real_codex_smoke_runbook_export import export_real_codex_smoke_runbook


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


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_tree(path: Path) -> dict[str, str]:
    return {
        file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink())
    }


def _zip_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def test_export_valid_dry_run_bundle_creates_zip_archive(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is True
    assert Path(result["archive_path"]).exists()
    assert Path(result["archive_path"]).suffix == ".zip"


def test_export_valid_dry_run_bundle_writes_sidecar_manifest(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    manifest_path = Path(result["manifest_path"])
    assert manifest_path.exists()
    manifest = _read_json(manifest_path)
    assert manifest["kind"] == "real_codex_smoke_runbook_export_manifest"


def test_export_archive_contains_export_manifest(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    assert "export_manifest.json" in _zip_names(Path(result["archive_path"]))


def test_export_archive_contains_required_bundle_files(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    names = set(_zip_names(Path(result["archive_path"])))
    assert {
        "README.md",
        "environment.txt",
        "git_status.txt",
        "codex_version.txt",
        "selected_policy.json",
        "default_skip_stdout.txt",
        "default_skip_stderr.txt",
        "explicit_smoke_stdout.txt",
        "explicit_smoke_stderr.txt",
        "result.json",
        "diagnosis_paths.json",
        "validation_result.json",
    }.issubset(names)


def test_export_manifest_lists_all_bundle_files(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    manifest = _read_json(Path(result["manifest_path"]))
    listed = {entry["path"] for entry in manifest["files"]}
    expected = {file.relative_to(run_dir).as_posix() for file in run_dir.rglob("*") if file.is_file() and not file.is_symlink()}
    assert listed == expected
    assert manifest["file_count"] == len(expected)


def test_export_manifest_records_sha256_for_each_file(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    manifest = _read_json(Path(result["manifest_path"]))
    for entry in manifest["files"]:
        expected = hashlib.sha256((run_dir / entry["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == expected


def test_export_manifest_records_file_sizes(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    manifest = _read_json(Path(result["manifest_path"]))
    for entry in manifest["files"]:
        assert entry["size_bytes"] == (run_dir / entry["path"]).stat().st_size


def test_export_refuses_invalid_bundle_without_force(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "result.json").unlink()

    result = export_real_codex_smoke_runbook(run_dir)

    assert result["valid"] is False
    assert result["exported"] is False
    assert not Path(result["archive_path"]).exists()


def test_export_force_exports_invalid_bundle_with_bundle_valid_false(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    (run_dir / "result.json").unlink()

    result = export_real_codex_smoke_runbook(run_dir, force=True)

    assert result["exported"] is True
    manifest = _read_json(Path(result["manifest_path"]))
    assert manifest["bundle_valid"] is False


def test_export_is_read_only_for_source_bundle(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    before = _hash_tree(run_dir)

    export_real_codex_smoke_runbook(run_dir)

    assert _hash_tree(run_dir) == before


def test_export_does_not_invoke_codex(tmp_path: Path, monkeypatch):
    run_dir = _dry_run_bundle(tmp_path)
    marker = tmp_path / "codex_invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(f"#!/bin/sh\ntouch {marker}\nexit 99\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")

    export_real_codex_smoke_runbook(run_dir)

    assert not marker.exists()


def test_export_does_not_run_pytest(tmp_path: Path, monkeypatch):
    run_dir = _dry_run_bundle(tmp_path)
    marker = tmp_path / "pytest_invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_pytest = fake_bin / "pytest"
    fake_pytest.write_text(f"#!/bin/sh\ntouch {marker}\nexit 99\n", encoding="utf-8")
    fake_pytest.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")

    export_real_codex_smoke_runbook(run_dir)

    assert not marker.exists()


def test_export_archive_uses_relative_paths(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    for name in _zip_names(Path(result["archive_path"])):
        assert not name.startswith("/")


def test_export_archive_does_not_include_parent_directory_entries(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    assert all(".." not in Path(name).parts for name in _zip_names(Path(result["archive_path"])))


def test_export_archive_file_order_is_deterministic(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)

    result = export_real_codex_smoke_runbook(run_dir)

    names = _zip_names(Path(result["archive_path"]))
    assert names == sorted(names)


def test_export_rejects_or_ignores_symlink_escape(tmp_path: Path):
    run_dir = _dry_run_bundle(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (run_dir / "escape.txt").symlink_to(outside)

    result = export_real_codex_smoke_runbook(run_dir)

    names = _zip_names(Path(result["archive_path"]))
    assert "escape.txt" not in names
