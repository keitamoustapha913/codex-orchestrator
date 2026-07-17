from __future__ import annotations

import hashlib
import os
from pathlib import Path

from codex_orchestrator.probe_artifact_refs import normalize_probe_artifact_refs
from codex_orchestrator.validators.schema_validator import validate_json


def _probe(repo: Path, rel: str, content: str = "proof\n") -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _object_ref(path: str = ".artifacts/probes/P0002/run_001/cleanup_proof.json", **file_overrides):
    file_item = {
        "path": path,
        "kind": "cleanup_proof",
        "sha256": "0" * 64,
        "size_bytes": 999999,
        "description": "worker supplied cleanup proof metadata",
    }
    file_item.update(file_overrides)
    return {
        "patchlet_id": "P0002",
        "probe_root": ".artifacts/probes/P0002/run_001",
        "run_id": "run_001",
        "files": [file_item],
    }


def _normalize(repo: Path, refs):
    return normalize_probe_artifact_refs(refs, target_repo_root=repo, patchlet_id="P0002")


def test_object_probe_artifact_ref_recomputes_sha256_from_actual_file(git_repo: Path):
    artifact = _probe(git_repo, ".artifacts/probes/P0002/run_001/cleanup_proof.json", '{"ok": true}\n')

    result = _normalize(git_repo, [_object_ref()])

    assert result.errors == []
    assert result.normalized_refs[0]["files"][0]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_object_probe_artifact_ref_recomputes_size_bytes_from_actual_file(git_repo: Path):
    artifact = _probe(git_repo, ".artifacts/probes/P0002/run_001/cleanup_proof.json", '{"ok": true}\n')

    result = _normalize(git_repo, [_object_ref()])

    assert result.errors == []
    assert result.normalized_refs[0]["files"][0]["size_bytes"] == artifact.stat().st_size


def test_object_probe_artifact_ref_discards_stale_worker_sha256(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0002/run_001/cleanup_proof.json")

    result = _normalize(git_repo, [_object_ref(sha256="f" * 64)])

    assert result.errors == []
    assert result.normalized_refs[0]["files"][0]["sha256"] != "f" * 64
    assert result.raw_object_refs[0]["worker_sha256_discarded"] is True


def test_object_probe_artifact_ref_discards_stale_worker_size_bytes(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0002/run_001/cleanup_proof.json")

    result = _normalize(git_repo, [_object_ref(size_bytes=999999)])

    assert result.errors == []
    assert result.normalized_refs[0]["files"][0]["size_bytes"] != 999999
    assert result.raw_object_refs[0]["worker_size_bytes_discarded"] is True


def test_object_probe_artifact_ref_preserves_raw_worker_metadata_in_gate_artifact(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0002/run_001/cleanup_proof.json")

    result = _normalize(git_repo, [_object_ref(sha256="f" * 64, size_bytes=999999)])

    assert result.errors == []
    raw = result.raw_object_refs[0]
    assert raw["raw_item"]["files"][0]["sha256"] == "f" * 64
    assert raw["raw_item"]["files"][0]["size_bytes"] == 999999
    assert raw["canonical_sha256"] == result.normalized_refs[0]["files"][0]["sha256"]
    assert raw["canonical_size_bytes"] == result.normalized_refs[0]["files"][0]["size_bytes"]


def test_string_probe_artifact_ref_still_recomputes_metadata(git_repo: Path):
    artifact = _probe(git_repo, ".artifacts/probes/P0002/run_001/cleanup_proof.json", "string-ref\n")

    result = _normalize(git_repo, [".artifacts/probes/P0002/run_001/cleanup_proof.json"])

    assert result.errors == []
    file_item = result.normalized_refs[0]["files"][0]
    assert file_item["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert file_item["size_bytes"] == artifact.stat().st_size


def test_mixed_string_and_object_probe_artifact_refs_canonicalize_consistently(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0002/run_001/cleanup_proof.json")
    _probe(git_repo, ".artifacts/probes/P0002/run_001/trace_ledger.jsonl")

    result = _normalize(
        git_repo,
        [
            _object_ref(),
            ".artifacts/probes/P0002/run_001/trace_ledger.jsonl",
        ],
    )

    assert result.errors == []
    assert [item["path"] for item in result.normalized_refs[0]["files"]] == [
        ".artifacts/probes/P0002/run_001/cleanup_proof.json",
        ".artifacts/probes/P0002/run_001/trace_ledger.jsonl",
    ]


def test_object_probe_artifact_ref_missing_path_is_rejected(git_repo: Path):
    result = _normalize(git_repo, [{"patchlet_id": "P0002", "probe_root": ".artifacts/probes/P0002/run_001", "run_id": "run_001", "files": [{}]}])

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_missing_required_field"


def test_object_probe_artifact_ref_missing_file_is_rejected(git_repo: Path):
    result = _normalize(git_repo, [_object_ref(".artifacts/probes/P0002/run_001/missing.json")])

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_missing_file"


def test_inventory_known_skipped_limit_ref_is_non_blocking_and_excluded(git_repo: Path):
    path = ".artifacts/probes/P0002/run_001/proof_runs.jsonl"
    result = normalize_probe_artifact_refs(
        [_object_ref(path)],
        target_repo_root=git_repo,
        patchlet_id="P0002",
        evidence_inventory={
            "entries": [
                {
                    "relative_path": "GP002/run_001/proof_runs.jsonl",
                    "capture_status": "SKIPPED_LIMIT",
                }
            ]
        },
        evidence_preservation={"files": []},
    )

    assert result.errors == []
    assert result.normalized_refs[0]["files"] == []
    assert result.warnings == [f"probe_artifact_ref_not_durable:SKIPPED_LIMIT:{path}"]


def test_inventory_known_unsafe_object_ref_is_non_blocking_and_excluded(git_repo: Path):
    path = ".artifacts/probes/P0002/run_001/unsafe.json"
    result = normalize_probe_artifact_refs(
        [_object_ref(path)],
        target_repo_root=git_repo,
        patchlet_id="P0002",
        evidence_inventory={
            "entries": [
                {
                    "relative_path": "GP002/run_001/unsafe.json",
                    "capture_status": "SKIPPED_UNSAFE_OBJECT",
                }
            ]
        },
        evidence_preservation={"files": []},
    )

    assert result.errors == []
    assert result.normalized_refs[0]["files"] == []
    assert result.warnings == [f"probe_artifact_ref_not_durable:SKIPPED_UNSAFE_OBJECT:{path}"]


def test_inventory_capture_with_failed_preservation_is_non_blocking(git_repo: Path):
    path = ".artifacts/probes/P0002/run_001/result.json"
    result = normalize_probe_artifact_refs(
        [_object_ref(path)],
        target_repo_root=git_repo,
        patchlet_id="P0002",
        evidence_inventory={
            "entries": [
                {
                    "relative_path": "GP002/run_001/result.json",
                    "capture_status": "CAPTURED",
                }
            ]
        },
        evidence_preservation={"files": [], "preservation_complete": False},
    )

    assert result.errors == []
    assert result.normalized_refs[0]["files"] == []
    assert result.warnings == [f"probe_artifact_ref_not_durable:PRESERVATION_FAILED:{path}"]


def test_object_probe_artifact_ref_outside_repo_is_rejected(git_repo: Path, tmp_path: Path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    result = _normalize(git_repo, [_object_ref(str(outside))])

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_object_probe_artifact_ref_outside_probe_root_is_rejected(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0002/other/cleanup_proof.json")

    result = _normalize(git_repo, [_object_ref(".artifacts/probes/P0002/other/cleanup_proof.json")])

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_object_probe_artifact_ref_patchlet_mismatch_is_rejected(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P9999/run_001/cleanup_proof.json")
    ref = _object_ref(".artifacts/probes/P9999/run_001/cleanup_proof.json")
    ref["patchlet_id"] = "P9999"
    ref["probe_root"] = ".artifacts/probes/P9999/run_001"

    result = _normalize(git_repo, [ref])

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_patchlet_mismatch"


def test_object_probe_artifact_ref_product_file_is_rejected(git_repo: Path):
    (git_repo / "observability.ini").write_text("metrics=enabled\n", encoding="utf-8")

    result = _normalize(git_repo, [_object_ref("observability.ini")])

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_object_probe_artifact_ref_symlink_escape_is_rejected(git_repo: Path, tmp_path: Path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = git_repo / ".artifacts/probes/P0002/run_001/cleanup_proof.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(outside, link)

    result = _normalize(git_repo, [_object_ref()])

    assert result.errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_probe_artifact_refs_normalization_result_schema_validates(git_repo: Path):
    _probe(git_repo, ".artifacts/probes/P0002/run_001/cleanup_proof.json")
    result = _normalize(git_repo, [_object_ref()])
    artifact = {
        "schema_version": "1.0",
        "kind": "probe_artifact_refs_normalization_result",
        "patchlet_id": "P0002",
        "attempt_id": "P0002_attempt1",
        "accepted": not result.errors,
        "canonical_refs": result.normalized_refs,
        "raw_string_refs": result.raw_string_refs,
        "raw_object_refs": result.raw_object_refs,
        "rejected_refs": result.rejected_refs,
        "warnings": result.warnings,
    }

    assert validate_json(artifact, "probe_artifact_refs_normalization_result.schema.json") == []
