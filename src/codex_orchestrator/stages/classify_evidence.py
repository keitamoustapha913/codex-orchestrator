from __future__ import annotations

import json

from codex_orchestrator.jsonio import read_json
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import TargetRepoContext


def _repo_files(ctx: TargetRepoContext) -> list[str]:
    if not ctx.paths.census_repo_files.exists():
        return []
    files = []
    for line in ctx.paths.census_repo_files.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith(".codex-orchestrator/") and not line.startswith(".artifacts/"):
            files.append(line)
    return sorted(files)


def _role_for_path(path: str, index: int) -> str:
    if path.endswith((".toml", ".yaml", ".yml", ".json")):
        return "config"
    if "/test" in path or path.startswith("tests/") or path.endswith("_test.py"):
        return "test"
    if index == 1:
        return "runtime_boundary"
    return "consumer"


def _unsupported_repo_level_rows(goal: dict) -> list[dict]:
    rows: list[dict] = []
    for item in sorted(goal.get("known_failure_modes", [])):
        lowered = item.lower()
        if "codex-only" in lowered or "unsupported" in lowered:
            rows.append({
                "role": "repo_level",
                "file": None,
                "symbol": None,
                "line_range": None,
                "found_by": "deterministic_classifier",
                "command_or_source": item,
                "why_relevant": "Known failure mode is unsupported without direct repository evidence.",
                "confidence": "low",
                "connected_evidence_ids": [],
            })
    return rows


def classify_evidence(ctx: TargetRepoContext) -> list[dict]:
    goal = read_json(ctx.paths.goal_spec) if ctx.paths.goal_spec.exists() else {"success_goals": [{"goal_id": "G001"}]}
    goal_id = goal.get("success_goals", [{"goal_id": "G001"}])[0].get("goal_id", "G001")
    rows: list[dict] = []
    for idx, path in enumerate(_repo_files(ctx), start=1):
        rows.append({
            "schema_version": "1.0",
            "kind": "evidence_row",
            "evidence_id": f"E{idx:03d}",
            "goal_id": goal_id,
            "role": _role_for_path(path, idx),
            "file": path,
            "symbol": None,
            "line_range": None,
            "found_by": "git_ls_files",
            "command_or_source": "git ls-files",
            "why_relevant": "Tracked target-repository file available for graph/invariant inspection.",
            "confidence": "medium",
            "connected_evidence_ids": [],
        })
    repo_level_rows = _unsupported_repo_level_rows(goal)
    if not rows:
        rows.append({
            "schema_version": "1.0",
            "kind": "evidence_row",
            "evidence_id": "E001",
            "goal_id": goal_id,
            "role": "repo_level",
            "file": None,
            "symbol": None,
            "line_range": None,
            "found_by": "deterministic_classifier",
            "command_or_source": "empty repository census",
            "why_relevant": "No tracked files were available; repo-level evidence recorded.",
            "confidence": "low",
            "connected_evidence_ids": [],
        })
    else:
        next_index = len(rows) + 1
        for offset, row in enumerate(repo_level_rows, start=0):
            rows.append({
                "schema_version": "1.0",
                "kind": "evidence_row",
                "evidence_id": f"E{next_index + offset:03d}",
                "goal_id": goal_id,
                **row,
            })

    ctx.paths.search_evidence_jsonl.parent.mkdir(parents=True, exist_ok=True)
    ctx.paths.search_evidence_jsonl.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    md = ["# Search Evidence", "", "| Evidence | Goal | Role | File | Confidence |", "|---|---|---|---|---|"]
    for row in rows:
        md.append(f"| {row['evidence_id']} | {row['goal_id']} | {row['role']} | {row['file']} | {row['confidence']} |")
    ctx.paths.search_evidence_md.write_text("\n".join(md) + "\n", encoding="utf-8")

    state = load_state(ctx)
    transition(ctx, state, "EVIDENCE_READY", reason="evidence classified")
    return rows
