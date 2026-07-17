from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
from typing import Any

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.paths import relative_to_repo
from codex_orchestrator.target_repo import TargetRepoContext


MAXIMUM_FILE_COUNT = 64
MAXIMUM_TOTAL_BYTES = 10 * 1024 * 1024
MAXIMUM_SINGLE_FILE_BYTES = 2 * 1024 * 1024
MAXIMUM_DEPTH = 6
MAXIMUM_PATH_LENGTH = 512

SANDBOX_DEBRIS = "SANDBOX_DEBRIS"
PROBE_EVIDENCE = "PROBE_EVIDENCE"
CAPTURED = "CAPTURED"
SKIPPED_LIMIT = "SKIPPED_LIMIT"
SKIPPED_UNSAFE_OBJECT = "SKIPPED_UNSAFE_OBJECT"


def render_worker_evidence_prompt_contract(
    *,
    patchlet: dict[str, Any],
    attempt_id: str,
    evidence_dir: str,
    scratch_dir: str,
) -> str:
    """Render the shared worker-facing durable evidence contract."""
    patchlet_id = patchlet["patchlet_id"]
    probe_ids = sorted(set(patchlet.get("probe_ids") or []))
    probe_paths = "\n".join(
        f"- `{evidence_dir}/{probe_id}/{attempt_id}/`" for probe_id in probe_ids
    )
    return (
        "## Durable probe evidence contract\n\n"
        "durable probe artifacts must be written beneath "
        f"`{evidence_dir}`.\n"
        f"- patchlet: `{patchlet_id}`\n"
        f"- mapped probe IDs: `{', '.join(probe_ids)}`\n"
        "- Expected mapped probe-evidence path(s):\n"
        f"{probe_paths}\n\n"
        f"Temporary output must be written beneath `{scratch_dir}`.\n"
        "Temporary files: write only beneath `$CXOR_WORKER_SCRATCH_DIR`.\n"
        "Product edits must be limited to the assigned product file.\n"
        "Product source edits: write only to the assigned product file in the Git checkout.\n"
        "Probe and diagnostic evidence: write only beneath `$CXOR_WORKER_EVIDENCE_DIR`.\n"
        "Do not create or use checkout-local `.artifacts/probes/`; the "
        "orchestrator preserves validated staged evidence.\n\n"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_type_from_mode(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "regular_file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
        return "device"
    return "special"


def _media_type(path: PurePosixPath) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix in {".jsonl", ".ndjson"}:
        return "application/x-ndjson"
    guessed, _encoding = mimetypes.guess_type(path.name)
    return guessed


def create_worker_evidence_contract(run_ctx: PatchletRunContext, patchlet: dict[str, Any]) -> dict[str, Any]:
    root = run_ctx.worker_evidence_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    contract = {
        "schema_version": "1.0",
        "kind": "worker_evidence_contract",
        "patchlet_id": patchlet["patchlet_id"],
        "attempt_id": run_ctx.run_dir.name,
        "staging_root": str(root),
        "allowed_probe_ids": sorted(set(patchlet.get("probe_ids") or [])),
        "maximum_file_count": MAXIMUM_FILE_COUNT,
        "maximum_total_bytes": MAXIMUM_TOTAL_BYTES,
        "maximum_single_file_bytes": MAXIMUM_SINGLE_FILE_BYTES,
        "maximum_depth": MAXIMUM_DEPTH,
        "allowed_object_types": ["regular_file"],
    }
    out = run_ctx.run_dir / "gates" / "worker_evidence_contract.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, contract)
    return contract


def _tracked_non_product_blob_paths(repo_root: Path, base: str, allowed_product_path: str) -> dict[str, list[str]]:
    proc = subprocess.run(
        ["git", "ls-tree", "-r", base],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    result: dict[str, list[str]] = {}
    if proc.returncode != 0:
        return result
    for line in proc.stdout.splitlines():
        metadata, separator, rel_path = line.partition("\t")
        fields = metadata.split()
        if not separator or len(fields) < 3 or rel_path == allowed_product_path:
            continue
        blob_id = fields[2]
        result.setdefault(blob_id, []).append(rel_path)
    return result


def _git_blob_id(path: Path) -> str | None:
    proc = subprocess.run(
        ["git", "hash-object", "--", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def protected_copy_sources(path: Path, protected_blobs: dict[str, list[str]]) -> list[str]:
    blob_id = _git_blob_id(path)
    return sorted(protected_blobs.get(blob_id or "", []))


def _association_for_staged_path(rel_path: PurePosixPath, allowed_probe_ids: set[str]) -> str | None:
    if len(rel_path.parts) < 2:
        return None
    first = rel_path.parts[0]
    return first if first in allowed_probe_ids else None


def _record(
    *,
    path: Path,
    relative_path: str,
    patchlet_id: str,
    attempt_id: str,
    probe_id: str | None,
    capture_status: str,
    source_kind: str,
    protected_copy_paths: list[str] | None = None,
) -> dict[str, Any]:
    info = path.lstat()
    object_type = object_type_from_mode(info.st_mode)
    captured_file = object_type == "regular_file" and capture_status == CAPTURED
    return {
        "relative_path": relative_path,
        "object_type": object_type,
        "size": info.st_size,
        "mode": f"{stat.S_IMODE(info.st_mode):04o}",
        "sha256": _sha256_file(path) if captured_file else None,
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "probe_id": probe_id,
        "schema_or_media_type": _media_type(PurePosixPath(relative_path)) if captured_file else None,
        "classification": SANDBOX_DEBRIS,
        "diagnostic_role": PROBE_EVIDENCE,
        "capture_status": capture_status,
        "source_kind": source_kind,
        "authoritative": False,
        "protected_copy_paths": protected_copy_paths or [],
    }


def inventory_staged_worker_evidence(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    accepted_checkpoint: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    root = run_ctx.worker_evidence_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    allowed_probe_ids = set(patchlet.get("probe_ids") or [])
    protected_blobs = _tracked_non_product_blob_paths(
        ctx.root,
        accepted_checkpoint,
        str(patchlet.get("allowed_product_runtime_file") or ""),
    )
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    total_bytes = 0
    file_count = 0
    root_stat = root.lstat()
    root_device = root_stat.st_dev

    def visit(directory: Path) -> None:
        nonlocal total_bytes, file_count
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda item: item.name)
        for child in children:
            path = Path(child.path)
            info = child.stat(follow_symlinks=False)
            rel = PurePosixPath(path.relative_to(root).as_posix())
            depth = len(rel.parts)
            kind = object_type_from_mode(info.st_mode)
            if kind == "directory" and info.st_dev == root_device and depth <= MAXIMUM_DEPTH:
                before_count = len(records)
                visit(path)
                if len(records) == before_count:
                    record = _record(
                        path=path,
                        relative_path=rel.as_posix(),
                        patchlet_id=patchlet["patchlet_id"],
                        attempt_id=run_ctx.run_dir.name,
                        probe_id=_association_for_staged_path(rel, allowed_probe_ids),
                        capture_status=SKIPPED_UNSAFE_OBJECT,
                        source_kind="staged",
                    )
                    records.append(record)
                    errors.append(f"{SKIPPED_UNSAFE_OBJECT}: {rel.as_posix()}")
                continue
            probe_id = _association_for_staged_path(rel, allowed_probe_ids)
            capture_status = CAPTURED
            if kind != "regular_file" or info.st_dev != root_device:
                capture_status = SKIPPED_UNSAFE_OBJECT
            elif len(rel.as_posix()) > MAXIMUM_PATH_LENGTH or depth > MAXIMUM_DEPTH:
                capture_status = SKIPPED_LIMIT
            elif probe_id is None:
                capture_status = SKIPPED_UNSAFE_OBJECT
            else:
                file_count += 1
                total_bytes += info.st_size
                if (
                    file_count > MAXIMUM_FILE_COUNT
                    or info.st_size > MAXIMUM_SINGLE_FILE_BYTES
                    or total_bytes > MAXIMUM_TOTAL_BYTES
                ):
                    capture_status = SKIPPED_LIMIT
            copies = protected_copy_sources(path, protected_blobs) if kind == "regular_file" else []
            if copies:
                capture_status = SKIPPED_UNSAFE_OBJECT
            record = _record(
                path=path,
                relative_path=rel.as_posix(),
                patchlet_id=patchlet["patchlet_id"],
                attempt_id=run_ctx.run_dir.name,
                probe_id=probe_id,
                capture_status=capture_status,
                source_kind="staged",
                protected_copy_paths=copies,
            )
            records.append(record)
            if capture_status != CAPTURED:
                errors.append(f"{capture_status}: {rel.as_posix()}")

    visit(root)
    return records, errors


def write_worker_evidence_inventory(
    *, run_ctx: PatchletRunContext, patchlet: dict[str, Any], entries: list[dict[str, Any]], errors: list[str]
) -> dict[str, Any]:
    result = {
        "schema_version": "1.0",
        "kind": "worker_evidence_inventory",
        "patchlet_id": patchlet["patchlet_id"],
        "attempt_id": run_ctx.run_dir.name,
        "staging_root": str(run_ctx.worker_evidence_dir.resolve()),
        "entries": entries,
        "captured_file_count": sum(row["capture_status"] == CAPTURED for row in entries),
        "skipped_file_count": sum(row["capture_status"] != CAPTURED for row in entries),
        "inventory_truncated": any(row["capture_status"] == SKIPPED_LIMIT for row in entries),
        "inventory_complete": True,
        "authoritative_proof": False,
        "promotion_blocked": False,
        "errors": errors,
    }
    write_json(run_ctx.run_dir / "gates" / "worker_evidence_inventory.json", result)
    return result


def preserve_worker_evidence(
    *,
    ctx: TargetRepoContext,
    run_ctx: PatchletRunContext,
    patchlet: dict[str, Any],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    preserved_root = run_ctx.preserved_worker_evidence_dir
    preserved_root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    errors: list[str] = []
    for entry in entries:
        if entry["capture_status"] != CAPTURED:
            continue
        rel = PurePosixPath(entry["relative_path"])
        source = run_ctx.worker_evidence_dir / Path(*rel.parts)
        preserved_rel = PurePosixPath("staged") / rel
        alias_payload = rel.parts[1:]
        try:
            before = source.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise OSError("source ceased to be a regular file")
            source_hash = _sha256_file(source)
            if source_hash != entry["sha256"]:
                raise OSError("source hash changed after inventory")
            destination = preserved_root / Path(*preserved_rel.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination, follow_symlinks=False)
            destination_hash = _sha256_file(destination)
            if destination_hash != source_hash:
                raise OSError("preserved hash mismatch")
            alias = ctx.paths.probe_dir / patchlet["patchlet_id"] / Path(*alias_payload)
            alias.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, alias, follow_symlinks=False)
            alias_hash = _sha256_file(alias)
            if alias_hash != source_hash:
                raise OSError("diagnostic alias hash mismatch")
            files.append(
                {
                    "evidence_reference": entry["relative_path"],
                    "classification": SANDBOX_DEBRIS,
                    "diagnostic_role": PROBE_EVIDENCE,
                    "capture_status": CAPTURED,
                    "probe_id": entry.get("probe_id"),
                    "source_path": str(source),
                    "preserved_path": relative_to_repo(ctx.root, destination),
                    "diagnostic_alias_path": relative_to_repo(ctx.root, alias),
                    "source_sha256": source_hash,
                    "preserved_sha256": destination_hash,
                    "diagnostic_alias_sha256": alias_hash,
                    "size_bytes": before.st_size,
                    "authoritative": False,
                }
            )
        except OSError as exc:
            errors.append(f"{entry['relative_path']}: {exc}")
    expected = sum(
        row["capture_status"] == CAPTURED for row in entries
    )
    complete = not errors and len(files) == expected
    result = {
        "schema_version": "1.0",
        "kind": "worker_evidence_preservation_result",
        "patchlet_id": patchlet["patchlet_id"],
        "attempt_id": run_ctx.run_dir.name,
        "source_staging_root": str(run_ctx.worker_evidence_dir.resolve()),
        "preserved_root": relative_to_repo(ctx.root, preserved_root),
        "files": files,
        "source_hashes_verified": complete,
        "preservation_complete": complete,
        "authoritative_proof": False,
        "promotion_blocked": False,
        "errors": errors,
    }
    write_json(run_ctx.run_dir / "gates" / "worker_evidence_preservation_result.json", result)
    return result
