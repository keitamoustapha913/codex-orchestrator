from __future__ import annotations

import os
from pathlib import Path

from codex_orchestrator.probe_artifact_refs import normalize_probe_artifact_refs


def _probe(repo: Path, rel: str, content: str = "probe\n") -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_normalizes_relative_flat_probe_file_string(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/comparison.txt")

    result = normalize_probe_artifact_refs([".artifacts/probes/P0001/comparison.txt"], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors == []
    assert result.normalization_applied is True
    assert result.normalized_refs[0]["probe_root"] == ".artifacts/probes/P0001"
    assert result.normalized_refs[0]["run_id"] == "default"


def test_normalizes_absolute_flat_probe_file_string(git_repo: Path):
    path = _probe(git_repo, ".artifacts/probes/P0001/comparison.txt")

    result = normalize_probe_artifact_refs([str(path)], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors == []
    assert result.normalized_refs[0]["files"][0]["path"] == ".artifacts/probes/P0001/comparison.txt"


def test_normalizes_nested_run_probe_file_string(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/run_001/before_state.json")

    result = normalize_probe_artifact_refs([".artifacts/probes/P0001/run_001/before_state.json"], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.normalized_refs[0]["probe_root"] == ".artifacts/probes/P0001/run_001"
    assert result.normalized_refs[0]["run_id"] == "run_001"


def test_groups_multiple_files_in_same_probe_root(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/a.txt")
    _probe(git_repo, ".artifacts/probes/P0001/b.txt")

    result = normalize_probe_artifact_refs([".artifacts/probes/P0001/b.txt", ".artifacts/probes/P0001/a.txt"], target_repo_root=git_repo, patchlet_id="P0001")

    assert len(result.normalized_refs) == 1
    assert [item["path"] for item in result.normalized_refs[0]["files"]] == [
        ".artifacts/probes/P0001/a.txt",
        ".artifacts/probes/P0001/b.txt",
    ]


def test_separates_multiple_run_roots(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/run_001/a.txt")
    _probe(git_repo, ".artifacts/probes/P0001/run_002/a.txt")

    result = normalize_probe_artifact_refs([".artifacts/probes/P0001/run_002/a.txt", ".artifacts/probes/P0001/run_001/a.txt"], target_repo_root=git_repo, patchlet_id="P0001")

    assert [ref["run_id"] for ref in result.normalized_refs] == ["run_001", "run_002"]


def test_derives_patchlet_id_probe_root_and_run_id(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/run_001/after_state.json")

    ref = normalize_probe_artifact_refs([".artifacts/probes/P0001/run_001/after_state.json"], target_repo_root=git_repo, patchlet_id="P0001").normalized_refs[0]

    assert ref["patchlet_id"] == "P0001"
    assert ref["probe_root"] == ".artifacts/probes/P0001/run_001"
    assert ref["run_id"] == "run_001"


def test_derives_file_kind_from_stem(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/repeat_probes.txt")

    file_item = normalize_probe_artifact_refs([".artifacts/probes/P0001/repeat_probes.txt"], target_repo_root=git_repo, patchlet_id="P0001").normalized_refs[0]["files"][0]

    assert file_item["kind"] == "repeat_probes"


def test_includes_sha256_and_size_bytes(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/summary.json", "{}\n")

    file_item = normalize_probe_artifact_refs([".artifacts/probes/P0001/summary.json"], target_repo_root=git_repo, patchlet_id="P0001").normalized_refs[0]["files"][0]

    assert len(file_item["sha256"]) == 64
    assert file_item["size_bytes"] == 3


def test_output_is_deterministically_sorted(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/run_b/a.txt")
    _probe(git_repo, ".artifacts/probes/P0001/run_a/z.txt")

    result = normalize_probe_artifact_refs([".artifacts/probes/P0001/run_b/a.txt", ".artifacts/probes/P0001/run_a/z.txt"], target_repo_root=git_repo, patchlet_id="P0001")

    assert [ref["run_id"] for ref in result.normalized_refs] == ["run_a", "run_b"]


def test_preserves_safe_object_ref(git_repo: Path):
    ref = {"patchlet_id": "P0001", "probe_root": ".artifacts/probes/P0001", "run_id": "default"}

    result = normalize_probe_artifact_refs([ref], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors == []
    assert result.normalized_refs[0] == ref


def test_validates_safe_object_ref_files(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/a.txt")
    ref = {"patchlet_id": "P0001", "probe_root": ".artifacts/probes/P0001", "run_id": "default", "files": [{"path": ".artifacts/probes/P0001/a.txt"}]}

    result = normalize_probe_artifact_refs([ref], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors == []
    assert result.normalized_refs[0]["files"][0]["path"] == ".artifacts/probes/P0001/a.txt"


def test_mixed_object_and_string_refs_merge_when_same_probe_root(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0001/a.txt")
    ref = {"patchlet_id": "P0001", "probe_root": ".artifacts/probes/P0001", "run_id": "default"}

    result = normalize_probe_artifact_refs([ref, ".artifacts/probes/P0001/a.txt"], target_repo_root=git_repo, patchlet_id="P0001")

    assert len(result.normalized_refs) == 1
    assert result.normalized_refs[0]["files"][0]["path"] == ".artifacts/probes/P0001/a.txt"


def test_rejects_missing_probe_file(git_repo: Path):
    result = normalize_probe_artifact_refs([".artifacts/probes/P0001/missing.txt"], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_missing_file"


def test_rejects_path_outside_target_repo(git_repo: Path, tmp_path: Path):
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")

    result = normalize_probe_artifact_refs([str(outside)], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_rejects_path_outside_artifacts_probes(git_repo: Path):
    _probe(git_repo, ".artifacts/not-probes/file.txt")

    result = normalize_probe_artifact_refs([".artifacts/not-probes/file.txt"], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_rejects_product_file_path(git_repo: Path):
    result = normalize_probe_artifact_refs(["app.py"], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_rejects_patchlet_id_mismatch(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P9999/file.txt")

    result = normalize_probe_artifact_refs([".artifacts/probes/P9999/file.txt"], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_patchlet_mismatch"


def test_rejects_symlink_escape(git_repo: Path, tmp_path: Path):
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    link = git_repo / ".artifacts/probes/P0001/symlink_to_outside"
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(outside, link)

    result = normalize_probe_artifact_refs([".artifacts/probes/P0001/symlink_to_outside"], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_rejects_non_string_non_object_item(git_repo: Path):
    result = normalize_probe_artifact_refs([123], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors[0]["normalized_signature"] == "patchlet_report_schema_violation"


def test_empty_refs_remain_empty_without_error(git_repo: Path):
    result = normalize_probe_artifact_refs([], target_repo_root=git_repo, patchlet_id="P0001")

    assert result.errors == []
    assert result.normalized_refs == []
