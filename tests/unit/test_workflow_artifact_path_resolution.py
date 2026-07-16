from __future__ import annotations

from pathlib import Path

import pytest

from codex_orchestrator.artifact_paths import resolve_artifact_write_path
from codex_orchestrator.errors import ValidationError


def test_resolves_relative_reference_beneath_absolute_root(tmp_path: Path):
    root = tmp_path / "target"
    assert resolve_artifact_write_path(
        owning_root=root, artifact_reference=".codex-orchestrator/runs/result.json"
    ) == root / ".codex-orchestrator/runs/result.json"


def test_preserves_nested_workflow_layout(tmp_path: Path):
    root = tmp_path / "target"
    result = resolve_artifact_write_path(
        owning_root=root, artifact_reference=".codex-orchestrator/runs/P0001_attempt4/gates/result.json"
    )
    assert result == root / ".codex-orchestrator/runs/P0001_attempt4/gates/result.json"


def test_accepts_absolute_path_inside_root(tmp_path: Path):
    root = tmp_path / "target"
    absolute = root / ".codex-orchestrator/result.json"
    assert resolve_artifact_write_path(owning_root=root, artifact_reference=absolute) == absolute


def test_rejects_absolute_path_outside_root(tmp_path: Path):
    with pytest.raises(ValidationError):
        resolve_artifact_write_path(owning_root=tmp_path / "target", artifact_reference=tmp_path / "other/result.json")


def test_rejects_parent_traversal_escape(tmp_path: Path):
    with pytest.raises(ValidationError):
        resolve_artifact_write_path(owning_root=tmp_path / "target", artifact_reference="../outside.json")


def test_rejects_root_itself_when_file_required(tmp_path: Path):
    with pytest.raises(ValidationError):
        resolve_artifact_write_path(owning_root=tmp_path / "target", artifact_reference=".")


def test_rejects_symlink_parent_escape(tmp_path: Path):
    root = tmp_path / "target"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValidationError):
        resolve_artifact_write_path(owning_root=root, artifact_reference="link/result.json")


def test_result_is_absolute(tmp_path: Path):
    result = resolve_artifact_write_path(owning_root=tmp_path / "target", artifact_reference="result.json")
    assert result.is_absolute()


def test_resolution_does_not_depend_on_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "target"
    monkeypatch.chdir(tmp_path)
    first = resolve_artifact_write_path(owning_root=root, artifact_reference="result.json")
    monkeypatch.chdir(tmp_path / "other" if (tmp_path / "other").exists() else tmp_path)
    second = resolve_artifact_write_path(owning_root=root, artifact_reference="result.json")
    assert first == second == root / "result.json"
