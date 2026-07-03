from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.state import now_iso


def prompt_index_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / ".codex-orchestrator" / "prompt_index.json"


def _repo_relative(repo_root: Path, path: str | Path | None) -> str | None:
    if path is None:
        return None
    path_obj = Path(path)
    if not path_obj.is_absolute():
        return str(path_obj)
    try:
        return str(path_obj.relative_to(repo_root))
    except ValueError:
        return str(path_obj)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _next_prompt_id(prompts: list[dict[str, Any]]) -> str:
    numbers: list[int] = []
    for prompt in prompts:
        prompt_id = str(prompt.get("prompt_id", ""))
        if prompt_id.startswith("PR") and prompt_id[2:].isdigit():
            numbers.append(int(prompt_id[2:]))
    return f"PR{(max(numbers) if numbers else 0) + 1:06d}"


def read_prompt_index(repo_root: Path | str) -> dict[str, Any]:
    path = prompt_index_path(repo_root)
    if not path.exists():
        return {"schema_version": "1.0", "kind": "prompt_index", "prompts": []}
    data = read_json(path)
    if not isinstance(data, dict):
        return {"schema_version": "1.0", "kind": "prompt_index", "prompts": []}
    data.setdefault("schema_version", "1.0")
    data.setdefault("kind", "prompt_index")
    data.setdefault("prompts", [])
    return data


def upsert_prompt_index_entry(repo_root: Path | str, entry: dict[str, Any]) -> dict[str, Any]:
    root = Path(repo_root)
    index = read_prompt_index(root)
    prompts = index.setdefault("prompts", [])
    entry = dict(entry)
    entry["path"] = _repo_relative(root, entry.get("path"))
    entry["subprompt_path"] = _repo_relative(root, entry.get("subprompt_path"))
    entry["artifact_paths"] = [_repo_relative(root, path) for path in entry.get("artifact_paths", [])]
    prompt_file = root / entry["path"] if entry.get("path") and not Path(entry["path"]).is_absolute() else Path(entry["path"])
    if prompt_file.exists() and prompt_file.is_file():
        entry["sha256"] = _sha256(prompt_file)
        entry["size_bytes"] = prompt_file.stat().st_size
    else:
        entry.setdefault("sha256", None)
        entry.setdefault("size_bytes", None)
    entry.setdefault("schema_version", "1.0")
    entry.setdefault("created_at", now_iso())
    entry.setdefault("failure_ids", [])
    entry.setdefault("contracts", [])
    entry.setdefault("artifact_paths", [])
    entry.setdefault("transaction_group_id", None)
    entry.setdefault("verifier_id", None)
    entry.setdefault("repair_plan_id", None)

    existing = next(
        (
            prompt
            for prompt in prompts
            if prompt.get("path") == entry.get("path")
            or (
                prompt.get("attempt_id")
                and prompt.get("attempt_id") == entry.get("attempt_id")
                and prompt.get("kind") == entry.get("kind")
            )
        ),
        None,
    )
    if existing is None:
        entry["prompt_id"] = entry.get("prompt_id") or _next_prompt_id(prompts)
        prompts.append(entry)
        result = entry
    else:
        entry["prompt_id"] = existing["prompt_id"]
        existing.update({key: value for key, value in entry.items() if value is not None})
        result = existing

    index_path = prompt_index_path(root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(index_path, index)
    append_operator_event(
        root,
        event_type="prompt_index_updated",
        severity="info",
        stage=result.get("stage"),
        summary=f"Prompt index updated for {result.get('prompt_id')}.",
        artifact_paths=[_repo_relative(root, index_path), result.get("path")],
        patchlet_id=result.get("patchlet_id"),
        attempt_id=result.get("attempt_id"),
        prompt_id=result.get("prompt_id"),
        prompt_path=result.get("path"),
    )
    return result


def list_prompt_entries(repo_root: Path | str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    prompts = list(read_prompt_index(repo_root).get("prompts", []))
    filters = filters or {}
    for key, value in filters.items():
        if value is None:
            continue
        prompts = [prompt for prompt in prompts if prompt.get(key) == value]
    return prompts


def get_prompt_entry(repo_root: Path | str, prompt_id: str) -> dict[str, Any] | None:
    for prompt in read_prompt_index(repo_root).get("prompts", []):
        if prompt.get("prompt_id") == prompt_id:
            return prompt
    return None
