from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.paths import relative_to_repo
from codex_orchestrator.state import now_iso


ARTIFACT_PREFIXES = (".codex-orchestrator/", ".artifacts/")


def run_target_hygiene_gate(
    *,
    target_repo_root: Path,
    workflow_dir: Path,
    probe_dir: Path,
    run_dir: Path,
    patchlet_id: str,
    attempt_id: str,
    allowed_product_runtime_file: str | None,
    cache_cleanup_enabled: bool = True,
) -> dict[str, Any]:
    target_repo_root = Path(target_repo_root).resolve()
    run_dir = Path(run_dir)
    gates_dir = run_dir / "gates"
    gates_dir.mkdir(parents=True, exist_ok=True)

    before_lines = _git_status_lines(target_repo_root)
    before_paths = _parse_status_paths(before_lines)
    classification = _classify_paths(target_repo_root, before_paths, allowed_product_runtime_file)

    removed: list[dict[str, Any]] = []
    if cache_cleanup_enabled:
        for path in classification["cache_artifacts_detected"]:
            removed.extend(_remove_cache_artifact(target_repo_root, path))

    after_lines = _git_status_lines(target_repo_root)
    after_paths = _parse_status_paths(after_lines)
    after_classification = _classify_paths(target_repo_root, after_paths, allowed_product_runtime_file)

    reasons: list[str] = []
    for path in after_classification["product_runtime_dirty_paths"]:
        reasons.append(f"product/runtime dirty target path remains: {path}")
    for path in after_classification["unknown_dirty_paths"]:
        reasons.append(f"unknown dirty target path remains: {path}")

    artifact_dirs_present = _artifact_dirs_present(before_paths, after_paths)
    ignored = [prefix for prefix in ARTIFACT_PREFIXES if prefix in artifact_dirs_present]
    whole_repo_clean_after_hygiene = not after_classification["product_runtime_dirty_paths"] and not after_classification["unknown_dirty_paths"]
    accepted = whole_repo_clean_after_hygiene

    result_path = gates_dir / "target_hygiene_gate_result.json"
    result = {
        "schema_version": "1.0",
        "kind": "target_hygiene_gate_result",
        "gate": "target_hygiene",
        "accepted": accepted,
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "checked_at": now_iso(),
        "product_runtime_clean": not after_classification["product_runtime_dirty_paths"],
        "artifact_dirs_present": artifact_dirs_present,
        "artifact_dirs_ignored": ignored,
        "cache_artifacts_detected": classification["cache_artifact_records"],
        "cache_artifacts_removed": removed,
        "unknown_dirty_paths": after_classification["unknown_dirty_paths"],
        "product_runtime_dirty_paths": after_classification["product_runtime_dirty_paths"],
        "git_status_before_hygiene": before_lines,
        "git_status_after_hygiene": after_lines,
        "whole_repo_clean_after_hygiene": whole_repo_clean_after_hygiene,
        "target_working_tree_clean_after_checkpoint": accepted,
        "workflow_dir": relative_to_repo(target_repo_root, workflow_dir),
        "probe_dir": relative_to_repo(target_repo_root, probe_dir),
        "result_path": relative_to_repo(target_repo_root, result_path),
        "reasons": reasons,
    }
    write_json(result_path, result)
    return result


def _git_status_lines(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _parse_status_paths(lines: list[str]) -> list[str]:
    paths: list[str] = []
    for line in lines:
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def _classify_paths(repo_root: Path, paths: list[str], allowed_product_runtime_file: str | None) -> dict[str, Any]:
    product_runtime_dirty_paths: list[str] = []
    unknown_dirty_paths: list[str] = []
    cache_artifacts_detected: list[str] = []
    cache_artifact_records: list[dict[str, Any]] = []

    for path in sorted(set(paths)):
        normalized = path.rstrip("/")
        if _is_artifact_path(path):
            continue
        if _is_python_cache_path(path):
            cache_artifacts_detected.append(path)
            cache_artifact_records.extend(_cache_records(repo_root, normalized))
            continue
        if _is_product_runtime_path(path, allowed_product_runtime_file):
            product_runtime_dirty_paths.append(path)
            continue
        unknown_dirty_paths.append(path)

    return {
        "product_runtime_dirty_paths": sorted(product_runtime_dirty_paths),
        "unknown_dirty_paths": sorted(unknown_dirty_paths),
        "cache_artifacts_detected": sorted(cache_artifacts_detected),
        "cache_artifact_records": cache_artifact_records,
    }


def _is_artifact_path(path: str) -> bool:
    return path.startswith(ARTIFACT_PREFIXES)


def _is_python_cache_path(path: str) -> bool:
    parts = Path(path.rstrip("/")).parts
    return "__pycache__" in parts or path.endswith(".pyc") or path.endswith(".pyo")


def _is_product_runtime_path(path: str, allowed_product_runtime_file: str | None) -> bool:
    normalized = path.rstrip("/")
    if allowed_product_runtime_file and normalized == allowed_product_runtime_file:
        return True
    return normalized.endswith(".py")


def _artifact_dirs_present(before_paths: list[str], after_paths: list[str]) -> list[str]:
    paths = before_paths + after_paths
    present: list[str] = []
    if any(path.startswith(".artifacts/") or path == ".artifacts/" for path in paths):
        present.append(".artifacts/")
    if any(path.startswith(".codex-orchestrator/") or path == ".codex-orchestrator/" for path in paths):
        present.append(".codex-orchestrator/")
    return present


def _cache_records(repo_root: Path, rel_path: str) -> list[dict[str, Any]]:
    path = repo_root / rel_path
    if path.is_dir():
        files = sorted(child for child in path.rglob("*") if child.is_file())
    elif path.exists():
        files = [path]
    else:
        files = []
    if not files:
        return [
            {
                "path": rel_path if rel_path.endswith("/") else f"{rel_path}/",
                "absolute_path": str(path),
                "size_bytes": None,
                "sha256": None,
                "mtime": path.stat().st_mtime if path.exists() else None,
                "tracked": _is_tracked(repo_root, rel_path),
                "classification": "python_cache",
                "cleanup_action": "remove",
            }
        ]
    records = []
    for file_path in files:
        records.append(_cache_file_record(repo_root, file_path))
    return records


def _cache_file_record(repo_root: Path, path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    rel = relative_to_repo(repo_root, path)
    return {
        "path": rel,
        "absolute_path": str(path),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mtime": path.stat().st_mtime,
        "tracked": _is_tracked(repo_root, rel),
        "classification": "python_cache",
        "cleanup_action": "remove",
    }


def _remove_cache_artifact(repo_root: Path, rel_path: str) -> list[dict[str, Any]]:
    normalized = rel_path.rstrip("/")
    if _is_artifact_path(normalized):
        return []
    path = (repo_root / normalized).resolve()
    try:
        path.relative_to(repo_root)
    except ValueError:
        return []
    records = _cache_records(repo_root, normalized)
    if any(record.get("tracked") for record in records):
        return [
            {
                "path": record["path"],
                "removed": False,
                "reason": "tracked cache artifact was not removed",
            }
            for record in records
        ]
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
    _remove_empty_cache_parents(repo_root, path.parent)
    return [{"path": record["path"], "removed": True} for record in records]


def _remove_empty_cache_parents(repo_root: Path, path: Path) -> None:
    while path != repo_root:
        if path.name != "__pycache__":
            break
        try:
            path.rmdir()
        except OSError:
            break
        path = path.parent


def _is_tracked(repo_root: Path, rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", rel_path.rstrip("/")],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode == 0
