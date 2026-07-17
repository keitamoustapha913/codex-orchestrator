from __future__ import annotations

import hashlib
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from codex_orchestrator.report_validation_errors import report_validation_error_detail


@dataclass(frozen=True)
class ProbeArtifactRefNormalizationResult:
    normalized_refs: list[dict[str, Any]]
    raw_string_refs: list[str]
    normalization_applied: bool
    errors: list[dict[str, Any]]
    warnings: list[str]
    raw_object_refs: list[dict[str, Any]] = dataclass_field(default_factory=list)
    rejected_refs: list[dict[str, Any]] = dataclass_field(default_factory=list)


KNOWN_NON_DURABLE_EVIDENCE_STATUSES = frozenset(
    {"SKIPPED_LIMIT", "SKIPPED_UNSAFE_OBJECT", "PRESERVATION_FAILED"}
)


def evidence_availability_by_alias(
    *,
    patchlet_id: str,
    inventory: dict[str, Any] | None,
    preservation: dict[str, Any] | None,
) -> dict[str, str]:
    """Map logical report aliases to deterministic preservation outcomes.

    Evidence is diagnostic.  This index exists only to distinguish a reference
    to a known staged-but-unavailable object from a fabricated reference.
    """
    preserved_aliases = {
        row.get("diagnostic_alias_path")
        for row in (preservation or {}).get("files", [])
        if isinstance(row, dict) and isinstance(row.get("diagnostic_alias_path"), str)
    }
    result: dict[str, str] = {}
    for entry in (inventory or {}).get("entries", []):
        if not isinstance(entry, dict):
            continue
        relative_path = entry.get("relative_path")
        if not isinstance(relative_path, str):
            continue
        parts = PurePosixPath(relative_path).parts
        if len(parts) < 2:
            continue
        alias = PurePosixPath(".artifacts", "probes", patchlet_id, *parts[1:]).as_posix()
        capture_status = str(entry.get("capture_status") or "")
        if capture_status == "CAPTURED":
            result[alias] = "CAPTURED" if alias in preserved_aliases else "PRESERVATION_FAILED"
        elif capture_status in {"SKIPPED_LIMIT", "SKIPPED_UNSAFE_OBJECT"}:
            result[alias] = capture_status
    return result


def _repo_relative(path: Path, root: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _error(signature: str, message: str, *, value: Any, pointer: str, field: str = "probe_artifact_refs") -> dict[str, Any]:
    actual_type = "string" if isinstance(value, str) else type(value).__name__
    return report_validation_error_detail(
        field=field,
        json_pointer=pointer,
        schema_path="/properties/probe_artifact_refs/items",
        message=message,
        validator="cxor_probe_ref_safety",
        expected_type="object",
        actual_type=actual_type,
        invalid_value_excerpt=str(value),
        normalized_signature=signature,
        repair_hint="Probe artifact refs must be object entries pointing to existing files under .artifacts/probes/.",
    )


def _file_metadata(path: Path, rel: str) -> dict[str, Any]:
    data = path.read_bytes()
    name = path.name
    kind = name.rsplit(".", 1)[0].lower().replace(" ", "_")
    suffix = path.suffix.lower().lstrip(".")
    item = {
        "path": rel,
        "kind": kind,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": path.stat().st_size,
    }
    if suffix:
        item["extension"] = suffix
    return item


def _derive_ref(path: Path, *, rel: str, target_repo_root: Path, patchlet_id: str, pointer: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    parts = rel.split("/")
    if len(parts) < 4 or parts[:2] != [".artifacts", "probes"]:
        return None, _error("probe_artifact_refs_unsafe_path", f"probe artifact ref must be under .artifacts/probes/: {rel}", value=rel, pointer=pointer)
    derived_patchlet = parts[2]
    if derived_patchlet != patchlet_id:
        return None, _error("probe_artifact_refs_patchlet_mismatch", f"probe artifact ref patchlet_id {derived_patchlet} does not match report patchlet_id {patchlet_id}", value=rel, pointer=pointer)
    if len(parts) >= 5:
        run_id = parts[-2]
        probe_root = "/".join(parts[:-1])
    else:
        run_id = "default"
        probe_root = "/".join(parts[:3])
    return {
        "patchlet_id": patchlet_id,
        "probe_root": probe_root,
        "run_id": run_id,
        "files": [_file_metadata(path, rel)],
    }, None


def _resolve_string_ref(value: str, *, target_repo_root: Path, pointer: str) -> tuple[Path | None, str | None, dict[str, Any] | None]:
    raw = Path(value)
    candidate = raw if raw.is_absolute() else target_repo_root / raw
    if not candidate.exists():
        return None, None, _error("probe_artifact_refs_missing_file", f"probe artifact ref does not exist: {value}", value=value, pointer=pointer)
    try:
        resolved = candidate.resolve(strict=True)
        root_resolved = target_repo_root.resolve(strict=True)
    except OSError as exc:
        return None, None, _error("probe_artifact_refs_missing_file", f"probe artifact ref could not be resolved: {value}: {exc}", value=value, pointer=pointer)
    if not _is_under(resolved, root_resolved):
        return None, None, _error("probe_artifact_refs_unsafe_path", f"probe artifact ref resolves outside target repo: {value}", value=value, pointer=pointer)
    rel = _repo_relative(resolved, root_resolved)
    if rel is None:
        return None, None, _error("probe_artifact_refs_unsafe_path", f"probe artifact ref is outside target repo: {value}", value=value, pointer=pointer)
    artifacts = root_resolved / ".artifacts" / "probes"
    if not _is_under(resolved, artifacts):
        return None, None, _error("probe_artifact_refs_unsafe_path", f"probe artifact ref must be under .artifacts/probes/: {value}", value=value, pointer=pointer)
    return resolved, rel, None


def _validate_object_ref(
    item: dict[str, Any],
    *,
    target_repo_root: Path,
    patchlet_id: str,
    pointer: str,
    raw_item_index: int,
    evidence_availability: dict[str, str],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    for field in ("patchlet_id", "probe_root", "run_id"):
        if not item.get(field):
            errors.append(_error("probe_artifact_refs_missing_required_field", f"probe artifact ref missing required field: {field}", value=item, pointer=pointer))
    if errors:
        return None, errors, [], warnings
    if item["patchlet_id"] != patchlet_id:
        return None, [_error("probe_artifact_refs_patchlet_mismatch", f"probe artifact ref patchlet_id {item['patchlet_id']} does not match report patchlet_id {patchlet_id}", value=item, pointer=pointer)], [], warnings
    root = target_repo_root.resolve()
    probe_root_path = (target_repo_root / item["probe_root"]).resolve()
    artifacts = root / ".artifacts" / "probes"
    if not _is_under(probe_root_path, artifacts):
        return None, [_error("probe_artifact_refs_unsafe_path", f"probe_root must be under .artifacts/probes/: {item['probe_root']}", value=item, pointer=pointer)], [], warnings
    copied = dict(item)
    safe_files: list[dict[str, Any]] = []
    raw_audit_items: list[dict[str, Any]] = []
    for index, file_item in enumerate(item.get("files") or []):
        path_value = file_item.get("path") if isinstance(file_item, dict) else None
        if not isinstance(path_value, str):
            errors.append(_error("probe_artifact_refs_missing_required_field", "probe artifact file entry missing path", value=file_item, pointer=f"{pointer}/files/{index}"))
            continue
        unavailable_status = evidence_availability.get(path_value)
        if unavailable_status in KNOWN_NON_DURABLE_EVIDENCE_STATUSES:
            logical = PurePosixPath(path_value)
            root_parts = PurePosixPath(str(item["probe_root"])).parts
            if (
                logical.is_absolute()
                or ".." in logical.parts
                or logical.parts[: len(root_parts)] != root_parts
            ):
                errors.append(_error("probe_artifact_refs_unsafe_path", f"probe artifact file must be under probe_root: {path_value}", value=path_value, pointer=f"{pointer}/files/{index}/path"))
                continue
            warnings.append(
                f"probe_artifact_ref_not_durable:{unavailable_status}:{path_value}"
            )
            continue
        path, rel, error = _resolve_string_ref(path_value, target_repo_root=target_repo_root, pointer=f"{pointer}/files/{index}/path")
        if error:
            errors.append(error)
            continue
        assert path is not None and rel is not None
        if not _is_under(path, probe_root_path):
            errors.append(_error("probe_artifact_refs_unsafe_path", f"probe artifact file must be under probe_root: {rel}", value=rel, pointer=f"{pointer}/files/{index}/path"))
            continue
        metadata = _file_metadata(path, rel)
        merged = dict(file_item)
        merged.setdefault("kind", metadata["kind"])
        merged["path"] = rel
        worker_sha256 = merged.get("sha256")
        worker_size_bytes = merged.get("size_bytes")
        merged["sha256"] = metadata["sha256"]
        merged["size_bytes"] = metadata["size_bytes"]
        if "extension" in metadata:
            merged.setdefault("extension", metadata["extension"])
        safe_files.append(merged)
        raw_audit_items.append(
            {
                "raw_item_index": raw_item_index,
                "raw_file_index": index,
                "raw_item": item,
                "raw_file_item": file_item,
                "path": rel,
                "canonical_sha256": metadata["sha256"],
                "canonical_size_bytes": metadata["size_bytes"],
                "worker_sha256_discarded": worker_sha256 is not None and worker_sha256 != metadata["sha256"],
                "worker_size_bytes_discarded": worker_size_bytes is not None and worker_size_bytes != metadata["size_bytes"],
            }
        )
    if errors:
        return None, errors, [], warnings
    if item.get("files") is not None:
        copied["files"] = sorted(safe_files, key=lambda entry: entry["path"])
    return copied, [], raw_audit_items, warnings


def normalize_probe_artifact_refs(
    raw_refs: list[Any],
    *,
    target_repo_root: Path,
    patchlet_id: str,
    artifact_root: Path | None = None,
    evidence_inventory: dict[str, Any] | None = None,
    evidence_preservation: dict[str, Any] | None = None,
) -> ProbeArtifactRefNormalizationResult:
    del artifact_root
    target_repo_root = Path(target_repo_root)
    raw_string_refs: list[str] = []
    errors: list[dict[str, Any]] = []
    rejected_refs: list[dict[str, Any]] = []
    raw_object_refs: list[dict[str, Any]] = []
    warnings: list[str] = []
    evidence_availability = evidence_availability_by_alias(
        patchlet_id=patchlet_id,
        inventory=evidence_inventory,
        preservation=evidence_preservation,
    )
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    preserved: list[dict[str, Any]] = []
    for index, item in enumerate(raw_refs or []):
        pointer = f"/probe_artifact_refs/{index}"
        if isinstance(item, str):
            raw_string_refs.append(item)
            path, rel, error = _resolve_string_ref(item, target_repo_root=target_repo_root, pointer=pointer)
            if error:
                errors.append(error)
                rejected_refs.append({"raw_item_index": index, "raw_item": item, "errors": [error]})
                continue
            assert path is not None and rel is not None
            ref, error = _derive_ref(path, rel=rel, target_repo_root=target_repo_root, patchlet_id=patchlet_id, pointer=pointer)
            if error:
                errors.append(error)
                rejected_refs.append({"raw_item_index": index, "raw_item": item, "errors": [error]})
                continue
            assert ref is not None
            key = (ref["patchlet_id"], ref["probe_root"], ref["run_id"])
            group = groups.setdefault(key, {"patchlet_id": ref["patchlet_id"], "probe_root": ref["probe_root"], "run_id": ref["run_id"], "files": []})
            group["files"].extend(ref["files"])
        elif isinstance(item, dict):
            ref, ref_errors, raw_audit_items, ref_warnings = _validate_object_ref(
                item,
                target_repo_root=target_repo_root,
                patchlet_id=patchlet_id,
                pointer=pointer,
                raw_item_index=index,
                evidence_availability=evidence_availability,
            )
            errors.extend(ref_errors)
            warnings.extend(ref_warnings)
            if ref_errors:
                rejected_refs.append({"raw_item_index": index, "raw_item": item, "errors": ref_errors})
            if ref:
                preserved.append(ref)
                if raw_audit_items:
                    raw_object_refs.extend(raw_audit_items)
        else:
            error = _error("patchlet_report_schema_violation", "probe_artifact_refs entries must be objects or raw string paths at ingress", value=item, pointer=pointer)
            errors.append(error)
            rejected_refs.append({"raw_item_index": index, "raw_item": item, "errors": [error]})
    normalized = preserved + list(groups.values())
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for ref in normalized:
        key = (ref["patchlet_id"], ref["probe_root"], ref["run_id"])
        target = merged.setdefault(key, {k: v for k, v in ref.items() if k != "files"})
        files = target.setdefault("files", []) if "files" in ref or "files" in target else None
        if files is not None:
            for file_item in ref.get("files", []):
                if file_item not in files:
                    files.append(file_item)
    output = []
    for ref in merged.values():
        if "files" in ref:
            ref["files"] = sorted(ref["files"], key=lambda entry: entry["path"])
        output.append(ref)
    output.sort(key=lambda entry: (entry["probe_root"], entry["run_id"], entry["patchlet_id"]))
    return ProbeArtifactRefNormalizationResult(
        normalized_refs=output,
        raw_string_refs=raw_string_refs,
        normalization_applied=(bool(raw_string_refs) or bool(raw_object_refs)) and not errors,
        errors=errors,
        warnings=(
            (["object_probe_artifact_metadata_recomputed"] if raw_object_refs and not errors else [])
            + sorted(set(warnings))
        ),
        raw_object_refs=raw_object_refs,
        rejected_refs=rejected_refs,
    )
