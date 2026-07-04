from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.state import now_iso


FROZEN_ARTIFACT = "master_prompt_frozen.json"
FROZEN_COPY = "master_prompt.md"


def freeze_master_prompt(
    *,
    repo_root: Path,
    workflow_root: Path,
    master_prompt_path: Path,
    workflow_id: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    workflow_root.mkdir(parents=True, exist_ok=True)
    source = master_prompt_path.expanduser().resolve()
    frozen_copy = workflow_root / FROZEN_COPY
    if source != frozen_copy.resolve():
        shutil.copyfile(source, frozen_copy)
    text = frozen_copy.read_text(encoding="utf-8")
    payload = {
        "schema_version": "1.0",
        "kind": "master_prompt_frozen",
        "workflow_id": workflow_id,
        "run_id": run_id,
        "source_path": str(source),
        "frozen_copy_path": _relative_to_repo(repo_root, frozen_copy),
        "sha256": _sha256_bytes(text.encode("utf-8")),
        "size_bytes": len(text.encode("utf-8")),
        "created_at": now_iso(),
        "read_only_source_of_truth": True,
        "source_spans": _source_spans(text),
    }
    write_json(workflow_root / FROZEN_ARTIFACT, payload)
    append_operator_event(
        repo_root,
        event_type="master_prompt_frozen",
        severity="info",
        stage="MASTER_PROMPT_SAVED",
        summary=f"master prompt frozen sha256={payload['sha256']}.",
        artifact_paths=[_relative_to_repo(repo_root, workflow_root / FROZEN_ARTIFACT), payload["frozen_copy_path"]],
        details={"master_prompt_sha256": payload["sha256"]},
    )
    return payload


def load_master_prompt_frozen(workflow_root: Path) -> dict[str, Any]:
    return read_json(workflow_root / FROZEN_ARTIFACT)


def check_master_prompt_source_unchanged(
    *,
    frozen: dict[str, Any],
    current_source_path: Path | None = None,
) -> dict[str, Any]:
    source = Path(current_source_path or frozen.get("source_path", ""))
    expected = frozen.get("sha256")
    if not source.exists():
        return {
            "kind": "master_prompt_source_check",
            "source_available": False,
            "source_changed_after_freeze": False,
            "expected_sha256": expected,
            "actual_sha256": None,
            "decision": "USE_FROZEN_COPY",
            "failure_signature": "prompt_source_missing_after_freeze",
        }
    actual = _sha256_file(source)
    changed = actual != expected
    return {
        "kind": "master_prompt_source_check",
        "source_available": True,
        "source_changed_after_freeze": changed,
        "expected_sha256": expected,
        "actual_sha256": actual,
        "decision": "USE_FROZEN_COPY" if changed else "SOURCE_UNCHANGED",
        "failure_signature": "prompt_source_changed_after_freeze" if changed else None,
    }


def make_master_prompt_reference_payload(frozen: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_id": frozen.get("workflow_id"),
        "run_id": frozen.get("run_id"),
        "master_prompt_sha256": frozen.get("sha256"),
        "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
    }


def _source_spans(text: str) -> list[dict[str, Any]]:
    spans = [_span("MPS001", text, 0, len(text), "goal_statement")]
    offset = 0
    next_id = 2
    for lineno, line in enumerate(text.splitlines(keepends=True), start=1):
        stripped = line.strip()
        line_start_offset = offset
        offset += len(line)
        if not stripped:
            continue
        spans.append(
            {
                "span_id": f"MPS{next_id:03d}",
                "start_offset": line_start_offset,
                "end_offset": line_start_offset + len(line),
                "line_start": lineno,
                "line_end": lineno,
                "column_start": 1,
                "column_end": len(line.rstrip("\n\r")) + 1,
                "text": line,
                "role": "goal_statement",
            }
        )
        next_id += 1
    return spans


def _span(span_id: str, text: str, start: int, end: int, role: str) -> dict[str, Any]:
    lines = text.splitlines() or [""]
    return {
        "span_id": span_id,
        "start_offset": start,
        "end_offset": end,
        "line_start": 1,
        "line_end": max(1, len(lines)),
        "column_start": 1,
        "column_end": len(lines[-1]) + 1,
        "text": text,
        "role": role,
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
