from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import stat
import subprocess
import tempfile
from typing import Any

from codex_orchestrator.integration_state import ensure_integration_state
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.paths import relative_to_repo
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.diff_validator import validate_changed_paths
from codex_orchestrator.worker_evidence import (
    inventory_staged_worker_evidence,
    preserve_worker_evidence,
    write_worker_evidence_inventory,
)


NON_PRODUCT_PATH_ENTERED_CANONICAL_PATCH = "NON_PRODUCT_PATH_ENTERED_CANONICAL_PATCH"
RAW_WORKER_SANDBOX_SCOPE = "raw_worker_sandbox"
PATCH_PROPOSAL_SCOPE = "patch_proposal"
CLEAN_RECONSTRUCTION_SCOPE = "clean_reconstruction"
PROMOTED_CANDIDATE_SCOPE = "promoted_candidate"
MAX_SANDBOX_ENTRIES = 5000
MAX_SANDBOX_DIAGNOSTIC_BYTES = 20 * 1024 * 1024
MAX_SANDBOX_ENTRY_BYTES = 5 * 1024 * 1024
MAX_SANDBOX_PATH_LENGTH = 512
MAX_SANDBOX_DIRECTORY_DEPTH = 8


@dataclass
class PatchOnlyPromotionResult:
    hygiene_result: dict[str, Any]
    patch_manifest: dict[str, Any]
    patch_validation: dict[str, Any]
    reconstruction_result: dict[str, Any]
    preparation_result_path: Path
    promotion_result_path: Path
    patch_path: Path
    verification_root: Path
    changed_paths: list[str]
    diff_text: str
    diagnostic_diff_text: str
    accepted: bool


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result


def _run_ok(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = _run(args, cwd=cwd, env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {' '.join(args)}")
    return result.stdout


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _object_type(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "missing"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "regular_file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
        return "device"
    return "special"


def _status_entries(repo_root: Path) -> list[tuple[str, str]]:
    output = _run_ok(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root)
    entries: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        code = line[:2]
        path = line[3:]
        if " -> " in path:
            entries.append((code, path.split(" -> ", 1)[0]))
            entries.append((code, path.split(" -> ", 1)[1]))
        else:
            entries.append((code, path))
    return entries


def _raw_changed_paths(repo_root: Path) -> list[str]:
    return sorted({path for _code, path in _status_entries(repo_root)})


def _filesystem_unsafe_entries(repo_root: Path) -> list[tuple[str, str]]:
    root_device = repo_root.lstat().st_dev
    found: list[tuple[str, str]] = []
    tracked_proc = _run(["git", "ls-files"], cwd=repo_root)
    tracked_dirs = {""}
    if tracked_proc.returncode == 0:
        for tracked_file in tracked_proc.stdout.splitlines():
            parent = Path(tracked_file).parent
            while parent.as_posix() != ".":
                tracked_dirs.add(parent.as_posix())
                parent = parent.parent

    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as iterator:
                children = sorted(iterator, key=lambda item: item.name)
        except OSError:
            return
        for child in children:
            if directory == repo_root and child.name == ".git":
                continue
            path = Path(child.path)
            try:
                info = child.stat(follow_symlinks=False)
            except OSError:
                continue
            rel_path = path.relative_to(repo_root).as_posix()
            kind = _object_type(path)
            if kind == "directory" and info.st_dev == root_device:
                before_count = len(found)
                visit(path)
                try:
                    empty = not any(path.iterdir())
                except OSError:
                    empty = False
                if empty and rel_path not in tracked_dirs and len(found) == before_count:
                    found.append(("??", rel_path))
            elif kind not in {"regular_file", "directory"} or info.st_dev != root_device:
                found.append(("??", rel_path))
    visit(repo_root)
    return found


def _raw_diff(repo_root: Path) -> str:
    result = _run(["git", "diff", "--binary", "--full-index", "--no-ext-diff", "--no-renames", "HEAD"], cwd=repo_root)
    return result.stdout if result.returncode == 0 else result.stdout + result.stderr


def _bounded_directory_regular(path: Path) -> tuple[bool, str | None, int, int]:
    count = 0
    total = 0
    base_depth = len(path.parts)
    for child in sorted(path.rglob("*")):
        rel_depth = len(child.parts) - base_depth
        if rel_depth > MAX_SANDBOX_DIRECTORY_DEPTH:
            return False, "INSPECTION_DEPTH_LIMIT_EXCEEDED", count, total
        count += 1
        if count > MAX_SANDBOX_ENTRIES:
            return False, "INSPECTION_ENTRY_LIMIT_EXCEEDED", count, total
        kind = _object_type(child)
        if kind == "directory":
            continue
        if kind != "regular_file":
            return False, "UNSUPPORTED_DIRECTORY_ENTRY_TYPE", count, total
        size = child.stat().st_size
        if size > MAX_SANDBOX_ENTRY_BYTES:
            return False, "INSPECTION_SINGLE_ENTRY_SIZE_LIMIT_EXCEEDED", count, total
        total += size
        if total > MAX_SANDBOX_DIAGNOSTIC_BYTES:
            return False, "INSPECTION_TOTAL_SIZE_LIMIT_EXCEEDED", count, total
    return True, None, count, total


def _report_references_path(report_path: Path | None, rel_path: str) -> bool:
    if report_path is None or not report_path.exists():
        return False
    try:
        text = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return rel_path in text


def _allowed_product_paths(patchlet: dict[str, Any]) -> list[str]:
    configured = patchlet.get("allowed_product_runtime_files")
    if isinstance(configured, list) and configured:
        return sorted({str(path) for path in configured if str(path)})
    singular = str(patchlet.get("allowed_product_runtime_file") or "")
    return [singular] if singular else []


def _lexically_inside_execution_root(root: Path, rel_path: str) -> bool:
    candidate = Path(rel_path)
    if candidate.is_absolute() or not rel_path:
        return False
    try:
        (root / candidate).resolve(strict=False).relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return not any(part == ".." for part in candidate.parts)


def _symlink_target_inside_execution_root(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _path_inside_boundary(path: Path, boundary: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(boundary.resolve())
    except (OSError, ValueError):
        return False
    return True


def inspect_worker_sandbox(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    report_path: Path | None,
) -> dict[str, Any]:
    allowed_paths = _allowed_product_paths(patchlet)
    allowed = set(allowed_paths)
    entries: list[dict[str, Any]] = []
    debris: list[dict[str, Any]] = []
    allowed_path_violations: list[dict[str, Any]] = []
    containment_violations: list[dict[str, Any]] = []
    include_paths: list[str] = []
    errors: list[str] = []
    inventory_truncated = False
    accepted_checkpoint = str(ensure_integration_state(ctx).get("integration_sha") or "")
    status_entries = _status_entries(run_ctx.execution_root)
    known_status_paths = {path for _code, path in status_entries}
    status_entries.extend(
        row for row in _filesystem_unsafe_entries(run_ctx.execution_root) if row[1] not in known_status_paths
    )
    status_by_path = {path: code for code, path in status_entries}
    status_entries = sorted(
        ((code, path) for path, code in status_by_path.items()),
        key=lambda row: row[1],
    )

    def add_entry(
        *,
        rel_path: str,
        status_code: str | None,
        object_type: str,
        tracked: bool,
        classification: str,
        allowed_product_match: bool,
        inside_execution_boundary: bool,
        diagnostic_role: str | None = None,
    ) -> dict[str, Any]:
        blocking = classification in {
            "ALLOWED_PRODUCT_PATH_VIOLATION",
            "SANDBOX_CONTAINMENT_VIOLATION",
        }
        entry = {
            "path": rel_path,
            "status_code": status_code,
            "tracked": tracked,
            "object_type": object_type,
            "inside_execution_boundary": inside_execution_boundary,
            "allowed_product_match": allowed_product_match,
            "classification": classification,
            "severity": "ERROR" if blocking else "INFO",
            "excluded_from_promotion": classification != "ALLOWED_PRODUCT_CHANGE",
            "promotion_eligible": classification == "ALLOWED_PRODUCT_CHANGE",
            "blocking": blocking,
            "diagnostic_role": diagnostic_role,
            "authoritative": classification == "ALLOWED_PRODUCT_CHANGE",
        }
        entries.append(entry)
        if classification == "SANDBOX_DEBRIS":
            debris.append(entry)
        elif classification == "ALLOWED_PRODUCT_PATH_VIOLATION":
            allowed_path_violations.append(entry)
        elif classification == "SANDBOX_CONTAINMENT_VIOLATION":
            containment_violations.append(entry)
        return entry

    for code, rel_path in status_entries:
        is_allowed = rel_path in allowed
        lexical_inside = _lexically_inside_execution_root(run_ctx.execution_root, rel_path)
        full = run_ctx.execution_root / rel_path
        kind = _object_type(full)
        tracked_at_checkpoint = (
            _blob_id(ctx.root, accepted_checkpoint, rel_path) is not None if lexical_inside else False
        )
        symlink_escapes = kind == "symlink" and not _symlink_target_inside_execution_root(
            run_ctx.execution_root,
            full,
        )
        if not lexical_inside or symlink_escapes:
            add_entry(
                rel_path=rel_path,
                status_code=code,
                object_type=kind,
                tracked=tracked_at_checkpoint,
                classification="SANDBOX_CONTAINMENT_VIOLATION",
                allowed_product_match=is_allowed,
                inside_execution_boundary=False,
            )
            errors.append(f"sandbox containment violation: {rel_path}")
            continue
        if is_allowed:
            if kind in {"regular_file", "missing"}:
                add_entry(
                    rel_path=rel_path,
                    status_code=code,
                    object_type=kind,
                    tracked=tracked_at_checkpoint,
                    classification="ALLOWED_PRODUCT_CHANGE",
                    allowed_product_match=True,
                    inside_execution_boundary=True,
                )
                include_paths.append(rel_path)
            else:
                add_entry(
                    rel_path=rel_path,
                    status_code=code,
                    object_type=kind,
                    tracked=tracked_at_checkpoint,
                    classification="ALLOWED_PRODUCT_PATH_VIOLATION",
                    allowed_product_match=True,
                    inside_execution_boundary=True,
                )
                errors.append(f"invalid allowlisted path object: {rel_path} ({kind})")
            continue
        if len(debris) >= MAX_SANDBOX_ENTRIES:
            inventory_truncated = True
            continue
        diagnostic_role = "REPORT_REFERENCED" if _report_references_path(report_path, rel_path) else None
        add_entry(
            rel_path=rel_path,
            status_code=code,
            object_type=kind,
            tracked=tracked_at_checkpoint,
            classification="SANDBOX_DEBRIS",
            allowed_product_match=False,
            inside_execution_boundary=True,
            diagnostic_role=diagnostic_role,
        )

    required_change = patchlet.get("required_allowed_product_change") is True
    if (
        required_change
        and not include_paths
        and not allowed_path_violations
        and not containment_violations
    ):
        for required_path in allowed_paths:
            entry = add_entry(
                rel_path=required_path,
                status_code=None,
                object_type=_object_type(run_ctx.execution_root / required_path),
                tracked=_blob_id(ctx.root, accepted_checkpoint, required_path) is not None,
                classification="ALLOWED_PRODUCT_PATH_VIOLATION",
                allowed_product_match=True,
                inside_execution_boundary=True,
                diagnostic_role="REQUIRED_CHANGE_ABSENT",
            )
            entry["violation_reason"] = "REQUIRED_ALLOWED_CHANGE_ABSENT"
            errors.append(f"required allowlisted change absent: {required_path}")

    boundary_root = run_ctx.execution_boundary_root
    if boundary_root is None:
        boundary_root = run_ctx.worktree_path.parent if run_ctx.worktree_path is not None else run_ctx.execution_root
    evidence_root = run_ctx.worker_evidence_dir
    evidence_root_escaped = evidence_root.is_symlink() and not _path_inside_boundary(evidence_root, boundary_root)
    if evidence_root_escaped:
        add_entry(
            rel_path="$CXOR_WORKER_EVIDENCE_DIR",
            status_code=None,
            object_type="symlink",
            tracked=False,
            classification="SANDBOX_CONTAINMENT_VIOLATION",
            allowed_product_match=False,
            inside_execution_boundary=False,
            diagnostic_role="PROBE_EVIDENCE",
        )
        errors.append("worker evidence path escapes execution boundary")
        staged_inventory: list[dict[str, Any]] = []
        staged_errors: list[str] = []
    else:
        staged_inventory, staged_errors = inventory_staged_worker_evidence(
            ctx=ctx,
            run_ctx=run_ctx,
            patchlet=patchlet,
            accepted_checkpoint=accepted_checkpoint,
        )
    for record in staged_inventory:
        if len(debris) >= MAX_SANDBOX_ENTRIES:
            inventory_truncated = True
            continue
        entry = add_entry(
            rel_path=f"$CXOR_WORKER_EVIDENCE_DIR/{record['relative_path']}",
            status_code=None,
            object_type=record["object_type"],
            tracked=False,
            classification="SANDBOX_DEBRIS",
            allowed_product_match=False,
            inside_execution_boundary=True,
            diagnostic_role="PROBE_EVIDENCE",
        )
        entry["capture_status"] = record.get("capture_status")
        entry["probe_id"] = record.get("probe_id")
    evidence_entries = staged_inventory
    inventory_errors = staged_errors
    inventory = write_worker_evidence_inventory(
        run_ctx=run_ctx,
        patchlet=patchlet,
        entries=evidence_entries,
        errors=inventory_errors,
    )
    preservation = preserve_worker_evidence(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        entries=evidence_entries,
    )
    del inventory, preservation
    if containment_violations:
        status = "CONTAINMENT_VIOLATION"
    elif allowed_path_violations:
        status = "ALLOWED_PATH_VIOLATION"
    elif debris:
        status = "DEBRIS_PRESENT"
    else:
        status = "CLEAN"
    promotion_blocked = bool(allowed_path_violations or containment_violations)
    if promotion_blocked:
        include_paths = []
    result = {
        "schema_version": "1.0",
        "kind": "worker_sandbox_hygiene_result",
        "candidate_scope": RAW_WORKER_SANDBOX_SCOPE,
        "patchlet_id": patchlet.get("patchlet_id"),
        "attempt_id": run_ctx.run_dir.name,
        "sandbox_root": str(run_ctx.execution_root),
        "accepted_checkpoint": accepted_checkpoint,
        "status": status,
        "entries": entries,
        "debris_entries": debris,
        "allowed_path_violations": allowed_path_violations,
        "containment_violations": containment_violations,
        "inspection_complete": True,
        "inspection_limits": {
            "maximum_entry_count": MAX_SANDBOX_ENTRIES,
            "maximum_total_diagnostic_bytes": MAX_SANDBOX_DIAGNOSTIC_BYTES,
            "maximum_single_entry_size": MAX_SANDBOX_ENTRY_BYTES,
            "maximum_path_length": MAX_SANDBOX_PATH_LENGTH,
            "maximum_traversal_depth": MAX_SANDBOX_DIRECTORY_DEPTH,
        },
        "promotion_blocked": promotion_blocked,
        "include_paths": sorted(set(include_paths)),
        "change_classification_ledger": entries,
        "sandbox_debris_count": len(debris),
        "allowed_product_change_count": sum(
            row["classification"] == "ALLOWED_PRODUCT_CHANGE" for row in entries
        ),
        "allowed_path_violation_count": len(allowed_path_violations),
        "containment_violation_count": len(containment_violations),
        "inventory_truncated": inventory_truncated,
        "worker_evidence_inventory": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "worker_evidence_inventory.json"),
        "worker_evidence_preservation_result": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "worker_evidence_preservation_result.json"),
        "errors": errors,
    }
    out = run_ctx.run_dir / "gates" / "worker_sandbox_hygiene_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, result)
    write_json(run_ctx.run_dir / "gates" / "worker_change_classification_ledger.json", {
        "schema_version": "1.0",
        "kind": "worker_change_classification_ledger",
        "patchlet_id": patchlet.get("patchlet_id"),
        "attempt_id": run_ctx.run_dir.name,
        "entries": entries,
        "every_path_classified_once": len({row["path"] for row in entries}) == len(entries),
        "promotion_blocked": promotion_blocked,
    })
    return result


def _blob_id(repo_root: Path, ref: str, path: str) -> str | None:
    result = _run(["git", "rev-parse", f"{ref}:{path}"], cwd=repo_root)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _index_blob_id(repo_root: Path, index_file: Path, path: str) -> str | None:
    result = _run(["git", "ls-files", "-s", "--", path], cwd=repo_root, env={"GIT_INDEX_FILE": str(index_file)})
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.split()[1]


def _tree_id(repo_root: Path, ref: str) -> str:
    return _run_ok(["git", "rev-parse", f"{ref}^{{tree}}"], cwd=repo_root).strip()


def _record_slice_boundary_violation(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    hygiene_result: dict[str, Any],
    allowed_path: str,
) -> None:
    entry = next(
        (
            row
            for row in hygiene_result.get("change_classification_ledger", [])
            if row.get("path") == allowed_path
            and row.get("classification") == "ALLOWED_PRODUCT_CHANGE"
        ),
        None,
    )
    if entry is None:
        return
    entry.update(
        {
            "classification": "ALLOWED_PRODUCT_PATH_VIOLATION",
            "promotion_eligible": False,
            "excluded_from_promotion": True,
            "blocking": True,
            "severity": "ERROR",
            "authoritative": False,
            "violation_reason": "SLICE_BOUNDARY_VIOLATION",
        }
    )
    violations = hygiene_result.setdefault("allowed_path_violations", [])
    if entry not in violations:
        violations.append(entry)
    hygiene_result["include_paths"] = [
        path for path in hygiene_result.get("include_paths", []) if path != allowed_path
    ]
    hygiene_result["allowed_product_change_count"] = sum(
        row.get("classification") == "ALLOWED_PRODUCT_CHANGE"
        for row in hygiene_result.get("change_classification_ledger", [])
    )
    hygiene_result["allowed_path_violation_count"] = len(violations)
    hygiene_result["promotion_blocked"] = True
    hygiene_result["status"] = "ALLOWED_PATH_VIOLATION"
    hygiene_result.setdefault("errors", []).append(
        f"allowlisted change violates slice boundary: {allowed_path}"
    )
    write_json(run_ctx.run_dir / "gates" / "worker_sandbox_hygiene_result.json", hygiene_result)
    write_json(
        run_ctx.run_dir / "gates" / "worker_change_classification_ledger.json",
        {
            "schema_version": "1.0",
            "kind": "worker_change_classification_ledger",
            "patchlet_id": hygiene_result.get("patchlet_id"),
            "attempt_id": hygiene_result.get("attempt_id"),
            "entries": hygiene_result.get("change_classification_ledger", []),
            "every_path_classified_once": True,
            "promotion_blocked": True,
        },
    )


def build_patch_proposal(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    hygiene_result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], Path, str]:
    proposal_dir = run_ctx.run_dir / "patch_promotion"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    patch_path = proposal_dir / "patch_proposal.patch"
    base = str(hygiene_result.get("accepted_checkpoint") or ensure_integration_state(ctx).get("integration_sha"))
    base_tree = _tree_id(ctx.root, base)
    index_file = proposal_dir / "temporary_index"
    if index_file.exists():
        index_file.unlink()
    _run_ok(["git", "read-tree", base], cwd=ctx.root, env={"GIT_INDEX_FILE": str(index_file)})
    changed_paths: list[str] = []
    errors: list[str] = []
    allowed_paths = set(_allowed_product_paths(patchlet))
    classifications = {
        row["path"]: row.get("classification")
        for row in hygiene_result.get("change_classification_ledger", hygiene_result.get("entries", []))
    }
    for rel_path in hygiene_result.get("include_paths", []):
        if rel_path not in allowed_paths or classifications.get(rel_path) != "ALLOWED_PRODUCT_CHANGE":
            errors.append(f"{NON_PRODUCT_PATH_ENTERED_CANONICAL_PATCH}: {rel_path}")
            continue
        full = run_ctx.execution_root / rel_path
        if _object_type(full) == "regular_file":
            _run_ok(["git", f"--work-tree={run_ctx.execution_root}", "add", "--", rel_path], cwd=ctx.root, env={"GIT_INDEX_FILE": str(index_file)})
            changed_paths.append(rel_path)
        else:
            _run_ok(["git", "update-index", "--force-remove", "--", rel_path], cwd=ctx.root, env={"GIT_INDEX_FILE": str(index_file)})
            changed_paths.append(rel_path)
    diff_proc = _run(
        ["git", "diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "--no-renames", base],
        cwd=ctx.root,
        env={"GIT_INDEX_FILE": str(index_file)},
    )
    if diff_proc.returncode != 0:
        errors.append(diff_proc.stderr.strip() or "canonical patch generation failed")
    patch_text = diff_proc.stdout
    patch_bytes = patch_text.encode("utf-8")
    patch_path.write_bytes(patch_bytes)
    validation_diff = validate_changed_paths(sorted(set(changed_paths)), patchlet, diff_text=patch_text)
    if validation_diff.slice_boundary_violations:
        for violation_path in sorted(
            {str(row.get("path")) for row in validation_diff.slice_boundary_violations if row.get("path")}
        ):
            _record_slice_boundary_violation(
                ctx=ctx,
                run_ctx=run_ctx,
                hygiene_result=hygiene_result,
                allowed_path=violation_path,
            )
            classifications[violation_path] = "ALLOWED_PRODUCT_PATH_VIOLATION"
    manifest_paths = []
    for rel_path in sorted(set(changed_paths)):
        manifest_paths.append(
            {
                "path": rel_path,
                "change_type": "modified_or_added",
                "old_blob_id": _blob_id(ctx.root, base, rel_path),
                "new_blob_id": _index_blob_id(ctx.root, index_file, rel_path),
                "allowed_product_path_match": rel_path in allowed_paths,
                "classification": classifications.get(rel_path),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "kind": "patch_proposal_manifest",
        "candidate_scope": PATCH_PROPOSAL_SCOPE,
        "patchlet_id": patchlet.get("patchlet_id"),
        "attempt_id": run_ctx.run_dir.name,
        "accepted_checkpoint_commit": base,
        "accepted_checkpoint_tree": base_tree,
        "patch_path": str(patch_path),
        "patch_sha256": _sha256_bytes(patch_bytes),
        "patch_size_bytes": len(patch_bytes),
        "changed_paths": manifest_paths,
        "goal_item_ids": patchlet.get("goal_item_ids", []),
        "proof_obligation_ids": patchlet.get("proof_obligation_ids", []),
        "probe_ids": patchlet.get("probe_ids", []),
        "current_slice_boundary": patchlet.get("current_slice_boundary"),
        "future_slice_boundaries": patchlet.get("future_slice_boundaries", []),
        "excluded_sandbox_paths": [row["path"] for row in hygiene_result.get("debris_entries", [])],
        "worker_hygiene_status": hygiene_result.get("status"),
        "canonical_patch_path_count": len(manifest_paths),
    }
    product_only = all(
        row.get("classification") in {
            "ALLOWED_PRODUCT_CHANGE",
            "ALLOWED_PRODUCT_PATH_VIOLATION",
        }
        and row.get("path") in allowed_paths
        for row in manifest_paths
    )
    if not product_only:
        errors.append(NON_PRODUCT_PATH_ENTERED_CANONICAL_PATCH)
    allowed_path_violations = hygiene_result.get("allowed_path_violations", [])
    containment_violations = hygiene_result.get("containment_violations", [])
    blocking_paths = [
        str(row.get("path"))
        for row in [*allowed_path_violations, *containment_violations]
        if row.get("path")
    ]
    current_boundary_valid = not any(
        row.get("reason") != "future_slice_change"
        for row in validation_diff.slice_boundary_violations or []
    )
    future_boundary_valid = not any(
        row.get("reason") == "future_slice_change"
        for row in validation_diff.slice_boundary_violations or []
    )
    validation = {
        "schema_version": "1.0",
        "kind": "patch_proposal_validation_result",
        "candidate_scope": PATCH_PROPOSAL_SCOPE,
        "patchlet_id": patchlet.get("patchlet_id"),
        "attempt_id": run_ctx.run_dir.name,
        "schema_valid": True,
        "allowed_file_validation": validation_diff.allowed and not allowed_path_violations,
        "current_boundary_validation": current_boundary_valid,
        "future_boundary_validation": future_boundary_valid,
        "support_file_validation": validation_diff.allowed,
        "verification_file_validation": validation_diff.allowed,
        "allowed_path_validation": not allowed_path_violations,
        "containment_validation": not containment_violations,
        "binary_patch_validation": diff_proc.returncode == 0,
        "product_classification_invariant": product_only,
        "accepted": (
            validation_diff.allowed
            and not allowed_path_violations
            and not containment_violations
            and diff_proc.returncode == 0
            and product_only
            and not errors
        ),
        "errors": errors + validation_diff.unauthorized_paths + blocking_paths,
    }
    write_json(proposal_dir / "patch_proposal_manifest.json", manifest)
    write_json(proposal_dir / "patch_proposal_validation_result.json", validation)
    if index_file.exists():
        index_file.unlink()
    return manifest, validation, patch_path, patch_text


def reconstruct_clean_candidate(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    manifest: dict[str, Any],
    validation: dict[str, Any],
    patch_path: Path,
) -> tuple[dict[str, Any], Path]:
    recon_dir = run_ctx.run_dir / "patch_promotion"
    base = str(manifest["accepted_checkpoint_commit"])
    verification_root = Path(tempfile.mkdtemp(prefix=f"cxor-clean-{patchlet['patchlet_id'].lower()}-", dir="/tmp")).resolve()
    errors: list[str] = []
    apply_check = None
    apply_result = None
    try:
        _run_ok(["git", "worktree", "add", "--detach", str(verification_root), base], cwd=ctx.root)
        clean_before = _run_ok(["git", "status", "--porcelain"], cwd=verification_root).strip() == ""
        if patch_path.stat().st_size == 0:
            apply_check = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            apply_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        else:
            apply_check = _run(
                ["git", "apply", "--check", "--index", "--binary", "--whitespace=error-all", str(patch_path)],
                cwd=verification_root,
            )
            if apply_check.returncode == 0:
                apply_result = _run(
                    ["git", "apply", "--index", "--binary", "--whitespace=error-all", str(patch_path)],
                    cwd=verification_root,
                )
                if apply_result.returncode != 0:
                    errors.append(apply_result.stderr.strip() or "patch application failed")
            else:
                errors.append(apply_check.stderr.strip() or "patch apply check failed")
        changed_paths = [
            line[3:].strip()
            for line in _run_ok(["git", "status", "--porcelain"], cwd=verification_root).splitlines()
            if line.strip()
        ]
        reconstructed_diff = _run_ok(["git", "diff", "--binary", "--full-index", "--no-ext-diff", "--no-renames", "HEAD"], cwd=verification_root)
        reconstructed_hash = _sha256_bytes(reconstructed_diff.encode("utf-8"))
        proposal_bytes = patch_path.read_bytes()
        proposal_hash = _sha256_bytes(proposal_bytes)
        proposal_equality = reconstructed_hash == proposal_hash
        if not proposal_equality:
            errors.append("reconstructed diff hash differs from patch proposal")
        expected_paths = sorted(row["path"] for row in manifest.get("changed_paths", []))
        unexpected_paths = sorted(set(changed_paths) - set(expected_paths))
        if unexpected_paths:
            errors.append("unexpected reconstructed paths: " + ", ".join(unexpected_paths))
        accepted = validation.get("accepted") is True and clean_before and apply_check.returncode == 0 and not errors
        result = {
            "schema_version": "1.0",
            "kind": "patch_reconstruction_result",
            "candidate_scope": CLEAN_RECONSTRUCTION_SCOPE,
            "patchlet_id": patchlet.get("patchlet_id"),
            "attempt_id": run_ctx.run_dir.name,
            "base_checkpoint": base,
            "base_tree": manifest.get("accepted_checkpoint_tree"),
            "patch_sha256": proposal_hash,
            "verification_root": str(verification_root),
            "apply_check_returncode": apply_check.returncode if apply_check else None,
            "apply_returncode": apply_result.returncode if apply_result else None,
            "reconstructed_changed_paths": changed_paths,
            "reconstructed_diff_sha256": reconstructed_hash,
            "proposal_reconstructed_equality": proposal_equality,
            "unexpected_paths": unexpected_paths,
            "clean_before": clean_before,
            "clean_after_relative_to_proposal": not unexpected_paths,
            "accepted": accepted,
            "errors": errors,
        }
    except Exception as exc:
        result = {
            "schema_version": "1.0",
            "kind": "patch_reconstruction_result",
            "candidate_scope": CLEAN_RECONSTRUCTION_SCOPE,
            "patchlet_id": patchlet.get("patchlet_id"),
            "attempt_id": run_ctx.run_dir.name,
            "base_checkpoint": base,
            "base_tree": manifest.get("accepted_checkpoint_tree"),
            "patch_sha256": manifest.get("patch_sha256"),
            "verification_root": str(verification_root),
            "apply_check_returncode": apply_check.returncode if apply_check else None,
            "apply_returncode": apply_result.returncode if apply_result else None,
            "reconstructed_changed_paths": [],
            "reconstructed_diff_sha256": None,
            "proposal_reconstructed_equality": False,
            "unexpected_paths": [],
            "clean_before": False,
            "clean_after_relative_to_proposal": False,
            "accepted": False,
            "errors": [str(exc)],
        }
    write_json(recon_dir / "patch_reconstruction_result.json", result)
    return result, verification_root


def prepare_clean_patch_candidate(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    report_path: Path | None,
) -> PatchOnlyPromotionResult:
    hygiene = inspect_worker_sandbox(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=report_path)
    manifest, validation, patch_path, diff_text = build_patch_proposal(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        hygiene_result=hygiene,
    )
    reconstruction, verification_root = reconstruct_clean_candidate(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        manifest=manifest,
        validation=validation,
        patch_path=patch_path,
    )
    allowed_path_violations = hygiene.get("allowed_path_violations", [])
    containment_violations = hygiene.get("containment_violations", [])
    accepted = (
        validation.get("accepted") is True
        and reconstruction.get("accepted") is True
        and not allowed_path_violations
        and not containment_violations
    )
    changed_paths = [row["path"] for row in manifest.get("changed_paths", [])]
    diagnostic_diff_text = diff_text
    preparation_result_path = run_ctx.run_dir / "patch_promotion" / "clean_candidate_preparation_result.json"
    promotion_result_path = run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json"
    write_json(
        preparation_result_path,
        {
            "schema_version": "1.0",
            "kind": "clean_candidate_preparation_result",
            "candidate_scope": CLEAN_RECONSTRUCTION_SCOPE,
            "patchlet_id": patchlet.get("patchlet_id"),
            "attempt_id": run_ctx.run_dir.name,
            "base_commit": manifest.get("accepted_checkpoint_commit"),
            "base_tree": manifest.get("accepted_checkpoint_tree"),
            "proposal_patch_sha256": manifest.get("patch_sha256"),
            "verification_candidate_root": str(verification_root),
            "worker_hygiene_status": hygiene.get("status"),
            "worker_warning_count": len(hygiene.get("debris_entries", [])),
            "candidate_prepared": accepted,
            "durable_integration_updated": False,
        },
    )
    return PatchOnlyPromotionResult(
        hygiene_result=hygiene,
        patch_manifest=manifest,
        patch_validation=validation,
        reconstruction_result=reconstruction,
        preparation_result_path=preparation_result_path,
        promotion_result_path=promotion_result_path,
        patch_path=patch_path,
        verification_root=verification_root,
        changed_paths=changed_paths,
        diff_text=diff_text,
        diagnostic_diff_text=diagnostic_diff_text,
        accepted=accepted,
    )


def write_worker_report_integrity_result(
    *,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    report_ingestion_result: dict[str, Any] | None,
    validation_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    accepted = bool(report_ingestion_result and report_ingestion_result.get("accepted"))
    errors = list(validation_errors or [])
    result = {
        "schema_version": "1.0",
        "kind": "worker_report_integrity_result",
        "candidate_scope": RAW_WORKER_SANDBOX_SCOPE,
        "patchlet_id": patchlet.get("patchlet_id"),
        "attempt_id": run_ctx.run_dir.name,
        "accepted": accepted,
        "report_exists": bool(report_ingestion_result and report_ingestion_result.get("raw_report_path")),
        "schema_valid": accepted,
        "required_structural_fields_present": accepted,
        "declared_artifact_references_valid": accepted,
        "excluded_debris_references_rejected": accepted,
        "required_evidence_references_valid": accepted,
        "raw_report_sha256": (report_ingestion_result or {}).get("raw_report_sha256"),
        "contract_fingerprint": (report_ingestion_result or {}).get("contract_fingerprint"),
        "report_parsed": bool(report_ingestion_result and (report_ingestion_result.get("raw_envelope") or {}).get("parseable")),
        "required_fields_present": bool(report_ingestion_result and (report_ingestion_result.get("validation") or {}).get("valid")),
        "known_fields_valid": accepted,
        "unknown_fields": list((report_ingestion_result or {}).get("unknown_fields", [])),
        "unknown_field_status": (report_ingestion_result or {}).get("unknown_field_status", "NONE"),
        "report_reorganization_used": bool((report_ingestion_result or {}).get("report_reorganization_used")),
        "report_reorganization_result": (report_ingestion_result or {}).get("report_reorganization_result", "NOT_REQUIRED"),
        "blocking_errors": errors if not accepted else [],
    }
    out = run_ctx.run_dir / "gates" / "worker_report_integrity_result.json"
    write_json(out, result)
    return result


def classify_worker_report_semantic_quality(
    *,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    report: dict[str, Any] | None,
    normalization_result: dict[str, Any] | None,
    probe_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings = list((normalization_result or {}).get("semantic_quality_warnings", []))
    warning_codes = {row.get("error_code") for row in warnings}
    contradictions = [row for row in warnings if row.get("error_code") == "WORKER_PROOF_CLAIM_NOT_ALLOWED"]
    overclaims = [row for row in warnings if row.get("error_code") in {"FUTURE_SLICE_CLAIM", "FUTURE_GOAL_ITEM", "UNLINKED_GOAL_ITEM"}]
    accepted_claims = list((normalization_result or {}).get("accepted_raw_claims", []))
    status = "COMPLETE" if accepted_claims and not warnings else "INCOMPLETE"
    if contradictions:
        status = "CONTRADICTORY"
    elif overclaims:
        status = "OVERCLAIMED"
    missing_components = []
    if "CURRENT_BOUNDARY_NOT_MENTIONED" in warning_codes:
        missing_components.append("current_boundary")
    if "VAGUE_RESULT_TEXT" in warning_codes:
        missing_components.extend(["file", "current_boundary", "expected_observation", "probe_id"])
    if not accepted_claims and not warnings and report and report.get("semantic_goal_results_raw"):
        missing_components.append("canonical_semantic_link")
    matched_components = []
    if accepted_claims:
        matched_components = ["file", "current_boundary", "expected_observation", "probe_id"]
    selected_probes = []
    if probe_plan:
        probe_ids = set(patchlet.get("probe_ids") or [])
        for probe in probe_plan.get("probes", []):
            if probe.get("probe_id") in probe_ids:
                selected_probes.append({"probe_id": probe.get("probe_id"), "command": probe.get("command")})
    result = {
        "schema_version": "1.0",
        "kind": "worker_report_semantic_quality_result",
        "candidate_scope": CLEAN_RECONSTRUCTION_SCOPE,
        "patchlet_id": patchlet.get("patchlet_id"),
        "attempt_id": run_ctx.run_dir.name,
        "status": status,
        "expected_components": {
            "file": patchlet.get("allowed_product_runtime_file") or "",
            "current_boundary": patchlet.get("current_slice_boundary") or patchlet.get("slice_change_boundary") or {},
            "expected_observation": "",
            "probe_ids": list(patchlet.get("probe_ids") or []),
            "probes": selected_probes,
        },
        "matched_components": matched_components,
        "missing_components": sorted(set(missing_components)),
        "contradictions": contradictions,
        "overclaims": overclaims,
        "blocking": False,
        "warnings": warnings,
        "errors": [],
    }
    out = run_ctx.run_dir / "gates" / "worker_report_semantic_quality_result.json"
    write_json(out, result)
    return result


def build_canonical_patchlet_semantic_result(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    patch_promotion_result: PatchOnlyPromotionResult,
    worker_report_integrity_result: dict[str, Any],
    worker_report_semantic_quality_result: dict[str, Any],
    independent_proof_result: dict[str, Any],
    goal_coverage_result: dict[str, Any],
) -> dict[str, Any]:
    proof_ok = independent_proof_result.get("accepted") is True
    coverage_ok = goal_coverage_result.get("accepted") is True
    accepted = (
        worker_report_integrity_result.get("accepted") is True
        and patch_promotion_result.patch_validation.get("accepted") is True
        and patch_promotion_result.reconstruction_result.get("accepted") is True
        and patch_promotion_result.hygiene_result.get("status") != "REJECTED"
        and proof_ok
        and coverage_ok
    )
    result = {
        "schema_version": "1.0",
        "kind": "canonical_patchlet_semantic_result",
        "candidate_scope": CLEAN_RECONSTRUCTION_SCOPE,
        "patchlet_id": patchlet.get("patchlet_id"),
        "attempt_id": run_ctx.run_dir.name,
        "goal_item_ids": list(patchlet.get("goal_item_ids") or []),
        "proof_obligation_ids": list(patchlet.get("proof_obligation_ids") or []),
        "probe_ids": list(patchlet.get("probe_ids") or []),
        "allowed_product_file": patchlet.get("allowed_product_runtime_file") or "",
        "current_boundary": patchlet.get("current_slice_boundary") or patchlet.get("slice_change_boundary") or {},
        "future_boundaries": list(patchlet.get("future_slice_boundaries") or []),
        "canonical_patch_sha256": patch_promotion_result.patch_manifest.get("patch_sha256") or "",
        "clean_candidate_commit": "",
        "clean_candidate_tree": patch_promotion_result.reconstruction_result.get("base_tree") or "",
        "effective_source_manifest_ref": {"path": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "independent_proof_effective_source_manifest.json")},
        "independent_proof_result_ref": {"path": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "independent_probe_rerun_result.json")},
        "goal_coverage_result_ref": {"path": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "goal_coverage_gate_result.json")},
        "worker_report_integrity_ref": {"path": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "worker_report_integrity_result.json")},
        "worker_report_semantic_quality_ref": {"path": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "worker_report_semantic_quality_result.json")},
        "worker_report_semantic_status": worker_report_semantic_quality_result.get("status"),
        "current_obligation_proven": proof_ok and coverage_ok,
        "future_obligations_advanced": [],
        "accepted": accepted,
        "errors": [] if accepted else ["canonical semantic gates did not all pass"],
    }
    out = run_ctx.run_dir / "gates" / "canonical_patchlet_semantic_result.json"
    write_json(out, result)
    return result


def write_clean_candidate_promotion_result(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    patch_promotion_result: PatchOnlyPromotionResult,
    base_integration_ref: str,
    integration_ref_before: str,
    expected_old_commit: str,
    candidate_commit: str,
    candidate_tree: str,
    integration_ref_after: str,
) -> dict[str, Any]:
    result = {
        "schema_version": "1.0",
        "kind": "clean_candidate_promotion_result",
        "candidate_scope": PROMOTED_CANDIDATE_SCOPE,
        "patchlet_id": patchlet.get("patchlet_id"),
        "attempt_id": run_ctx.run_dir.name,
        "base_integration_ref": base_integration_ref,
        "integration_ref_before": integration_ref_before,
        "expected_old_commit": expected_old_commit,
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "canonical_patch_sha256": patch_promotion_result.patch_manifest.get("patch_sha256"),
        "independent_proof_result_ref": {"path": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "independent_probe_rerun_result.json")},
        "goal_coverage_result_ref": {"path": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "goal_coverage_gate_result.json")},
        "canonical_semantic_result_ref": {"path": relative_to_repo(ctx.root, run_ctx.run_dir / "gates" / "canonical_patchlet_semantic_result.json")},
        "integration_ref_after": integration_ref_after,
        "durable_ref_update_completed": integration_ref_after == candidate_commit,
        "promotion_accepted": integration_ref_after == candidate_commit,
        "errors": [],
    }
    write_json(patch_promotion_result.promotion_result_path, result)
    return result


def _selected_probes_for_patchlet(probe_plan: dict[str, Any], patchlet: dict[str, Any]) -> list[dict[str, Any]]:
    probe_ids = set(patchlet.get("probe_ids") or [])
    obligation_ids = set(patchlet.get("proof_obligation_ids") or [])
    selected = []
    for probe in probe_plan.get("probes", []):
        if probe.get("probe_id") in probe_ids or obligation_ids.intersection(set(probe.get("obligation_ids") or [])):
            selected.append(probe)
    return selected


def _candidate_git_blob_id(root: Path, rel_path: str) -> tuple[str | None, str | None]:
    result = _run(["git", "ls-files", "-s", "--", rel_path], cwd=root)
    if result.returncode != 0 or not result.stdout.strip():
        return None, None
    parts = result.stdout.split()
    return parts[1], parts[0]


def _probe_source_paths(probe_plan: dict[str, Any], patchlet: dict[str, Any], verification_root: Path) -> set[str]:
    paths: set[str] = set()
    for probe in _selected_probes_for_patchlet(probe_plan, patchlet):
        command = probe.get("command")
        if isinstance(command, str):
            try:
                tokens = shlex.split(command)
            except ValueError:
                tokens = command.split()
            for token in tokens:
                if token.startswith("-") or token.startswith("/") or ".." in Path(token).parts:
                    continue
                candidate = verification_root / token
                if candidate.is_file():
                    paths.add(Path(token).as_posix())
        expected = probe.get("expected_observation")
        if isinstance(expected, dict):
            rel_path = expected.get("path") or expected.get("file")
            if isinstance(rel_path, str) and not rel_path.startswith("/") and ".." not in Path(rel_path).parts and (verification_root / rel_path).is_file():
                paths.add(Path(rel_path).as_posix())
    return paths


def write_independent_proof_effective_source_manifest(
    *,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    patch_manifest: dict[str, Any],
    verification_root: Path,
    probe_plan: dict[str, Any],
) -> dict[str, Any]:
    paths: set[str] = {row["path"] for row in patch_manifest.get("changed_paths", []) if row.get("path")}
    boundary = patchlet.get("current_slice_boundary") or patchlet.get("current_boundary") or {}
    if isinstance(boundary, dict) and boundary.get("file"):
        paths.add(Path(str(boundary["file"])).as_posix())
    allowed = patchlet.get("allowed_product_runtime_file")
    if allowed:
        paths.add(Path(str(allowed)).as_posix())
    paths.update(_probe_source_paths(probe_plan, patchlet, verification_root))
    effective_sources: list[dict[str, Any]] = []
    for rel_path in sorted(paths):
        if rel_path.startswith("/") or ".." in Path(rel_path).parts:
            continue
        full = verification_root / rel_path
        if not full.is_file():
            continue
        git_blob_id, mode = _candidate_git_blob_id(verification_root, rel_path)
        effective_sources.append(
            {
                "path": rel_path,
                "blob_sha256": _sha256_file(full),
                "git_blob_id": git_blob_id,
                "mode": mode,
            }
        )
    selected = _selected_probes_for_patchlet(probe_plan, patchlet)
    first_probe = selected[0] if selected else {}
    result = {
        "schema_version": "1.0",
        "kind": "independent_proof_effective_source_manifest",
        "candidate_scope": CLEAN_RECONSTRUCTION_SCOPE,
        "patchlet_id": patchlet.get("patchlet_id"),
        "attempt_id": run_ctx.run_dir.name,
        "base_checkpoint_commit": patch_manifest.get("accepted_checkpoint_commit"),
        "base_checkpoint_tree": patch_manifest.get("accepted_checkpoint_tree"),
        "patch_sha256": patch_manifest.get("patch_sha256"),
        "verification_root": str(verification_root),
        "probe_id": first_probe.get("probe_id"),
        "probe_command": first_probe.get("command"),
        "probe_cwd": str(verification_root),
        "effective_sources": effective_sources,
    }
    result["manifest_sha256"] = _sha256_bytes(_canonical_json_bytes(result))
    out = run_ctx.run_dir / "gates" / "independent_proof_effective_source_manifest.json"
    write_json(out, result)
    return result


def dispose_patch_only_worktrees(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    worker_root: Path | None,
    verification_root: Path | None,
    promotion_accepted: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    worker_sandbox_root = worker_root.parent if worker_root is not None and worker_root.name == "checkout" else worker_root
    for root in [verification_root, worker_root]:
        if root is None:
            continue
        subprocess.run(
            ["git", "-C", str(ctx.root), "worktree", "remove", "--force", str(root)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if root.exists():
            try:
                shutil.rmtree(root)
            except OSError as exc:
                errors.append(str(exc))
    if worker_sandbox_root is not None and worker_sandbox_root != worker_root and worker_sandbox_root.exists():
        try:
            shutil.rmtree(worker_sandbox_root)
        except OSError as exc:
            errors.append(str(exc))
    result = {
        "schema_version": "1.0",
        "kind": "worker_sandbox_disposal_result",
        "candidate_scope": RAW_WORKER_SANDBOX_SCOPE,
        "patchlet_id": run_ctx.run_dir.name.split("_attempt", 1)[0],
        "attempt_id": run_ctx.run_dir.name,
        "sandbox_root": str(worker_sandbox_root) if worker_sandbox_root else None,
        "attempt_result": "accepted" if promotion_accepted else "rejected",
        "promotion_result": promotion_accepted,
        "evidence_retained": True,
        "excluded_debris_metadata_retained": (run_ctx.run_dir / "gates" / "worker_sandbox_hygiene_result.json").exists(),
        "sandbox_archived": False,
        "cleanup_attempted": True,
        "cleanup_succeeded": not errors,
        "remaining_path_exists": bool((worker_sandbox_root and worker_sandbox_root.exists()) or (verification_root and verification_root.exists())),
        "errors": errors,
    }
    write_json(run_ctx.run_dir / "patch_promotion" / "worker_sandbox_disposal_result.json", result)
    return result
