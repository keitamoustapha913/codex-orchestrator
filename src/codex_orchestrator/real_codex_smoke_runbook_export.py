from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.validators.real_codex_smoke_runbook_validator import validate_real_codex_smoke_runbook


def export_real_codex_smoke_runbook(
    run_dir: Path,
    *,
    out: Path | None = None,
    archive_format: str = "zip",
    force: bool = False,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    if archive_format != "zip":
        return _result(
            run_dir=run_dir,
            archive_path=_default_archive_path(run_dir, out),
            manifest_path=_default_archive_path(run_dir, out).with_suffix(".zip.manifest.json"),
            valid=False,
            exported=False,
            validation=validate_real_codex_smoke_runbook(run_dir),
            errors=[{"path": str(run_dir), "schema": "archive_format", "message": "only zip export is supported"}],
        )

    validation = validate_real_codex_smoke_runbook(run_dir)
    valid = bool(validation.get("valid"))
    archive_path = _default_archive_path(run_dir, out)
    manifest_path = archive_path.with_suffix(".zip.manifest.json")
    if not valid and not force:
        return _result(
            run_dir=run_dir,
            archive_path=archive_path,
            manifest_path=manifest_path,
            valid=False,
            exported=False,
            validation=validation,
            errors=list(validation.get("errors", [])),
        )

    files = _bundle_file_entries(run_dir)
    result_payload = _read_json_object(run_dir / "result.json")
    policy_payload = _read_json_object(run_dir / "selected_policy.json")
    manifest = {
        "schema_version": "1.0",
        "kind": "real_codex_smoke_runbook_export_manifest",
        "source_run_dir": str(run_dir),
        "archive_path": str(archive_path),
        "archive_format": archive_format,
        "bundle_valid": valid,
        "bundle_validation_result_path": "validation_result.json" if (run_dir / "validation_result.json").exists() else None,
        "outcome": result_payload.get("outcome"),
        "selected_model": policy_payload.get("codex_model"),
        "selected_reasoning": policy_payload.get("codex_reasoning"),
        "timeout_seconds": policy_payload.get("codex_patchlet_timeout_seconds") or result_payload.get("timeout_seconds"),
        "timed_out": result_payload.get("timed_out") if isinstance(result_payload.get("timed_out"), bool) else None,
        "diagnosis_primary_category": result_payload.get("diagnosis_primary_category"),
        "attempt_consistency": result_payload.get("attempt_consistency") if isinstance(result_payload.get("attempt_consistency"), dict) else None,
        "file_count": len(files),
        "files": files,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    names = sorted([entry["path"] for entry in files] + ["export_manifest.json"])
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            if name == "export_manifest.json":
                archive.writestr(name, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            else:
                archive.write(run_dir / name, arcname=name)
    write_json(manifest_path, manifest)

    return _result(
        run_dir=run_dir,
        archive_path=archive_path,
        manifest_path=manifest_path,
        valid=valid,
        exported=True,
        validation=validation,
        errors=[],
    )


def _bundle_file_entries(run_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not run_dir.exists() or not run_dir.is_dir():
        return entries
    for path in sorted(run_dir.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(run_dir)
        if _unsafe_relative_path(relative):
            continue
        entries.append(
            {
                "path": relative.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return entries


def _unsafe_relative_path(path: Path) -> bool:
    text = path.as_posix()
    return text.startswith("/") or ".." in path.parts


def _default_archive_path(run_dir: Path, out: Path | None) -> Path:
    if out is not None:
        return Path(out)
    return run_dir.parent.parent / "exports" / f"{run_dir.name}.zip"


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = read_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _result(
    *,
    run_dir: Path,
    archive_path: Path,
    manifest_path: Path,
    valid: bool,
    exported: bool,
    validation: dict[str, Any],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "real_codex_smoke_runbook_export_result",
        "valid": valid,
        "exported": exported,
        "source_run_dir": str(run_dir),
        "archive_path": str(archive_path),
        "manifest_path": str(manifest_path),
        "archive_format": "zip",
        "bundle_validation": validation,
        "errors": errors,
    }
