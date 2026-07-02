from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    return ctx


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_classify_evidence_generates_schema_valid_jsonl_rows_from_census(git_repo: Path):
    ctx = _ctx(git_repo)

    rows = classify_evidence(ctx)

    saved_rows = _read_jsonl(ctx.paths.search_evidence_jsonl)
    assert rows == saved_rows
    assert saved_rows
    for row in saved_rows:
        assert validate_json(row, "evidence.schema.json") == []


def test_classify_evidence_writes_markdown_table_from_jsonl(git_repo: Path):
    ctx = _ctx(git_repo)

    rows = classify_evidence(ctx)
    markdown = ctx.paths.search_evidence_md.read_text(encoding="utf-8")

    assert "| Evidence | Goal | Role | File | Confidence |" in markdown
    for row in rows:
        assert row["evidence_id"] in markdown
        assert row["goal_id"] in markdown


def test_classify_evidence_ids_are_stable_across_rerun(git_repo: Path):
    ctx = _ctx(git_repo)

    first_rows = classify_evidence(ctx)
    second_rows = classify_evidence(ctx)

    assert [row["evidence_id"] for row in first_rows] == [row["evidence_id"] for row in second_rows]
    assert first_rows == second_rows


def test_classify_evidence_marks_repo_level_when_no_file_applies(git_repo: Path):
    ctx = _ctx(git_repo)
    ctx.paths.census_repo_files.write_text("", encoding="utf-8")

    rows = classify_evidence(ctx)

    assert rows == [{
        "schema_version": "1.0",
        "kind": "evidence_row",
        "evidence_id": "E001",
        "goal_id": "G001",
        "role": "repo_level",
        "file": None,
        "symbol": None,
        "line_range": None,
        "found_by": "deterministic_classifier",
        "command_or_source": "empty repository census",
        "why_relevant": "No tracked files were available; repo-level evidence recorded.",
        "confidence": "low",
        "connected_evidence_ids": []
    }]


def test_classify_evidence_marks_codex_only_or_unsupported_claim_low_confidence(git_repo: Path):
    (git_repo / "master_prompt.md").write_text(
        "# Master Prompt\n\n"
        "Success goals:\n"
        "- G001: Complete the workflow.\n\n"
        "Known failure modes:\n"
        "- Codex-only unsupported claim about external runtime behavior.\n",
        encoding="utf-8",
    )
    ctx = _ctx(git_repo)

    rows = classify_evidence(ctx)

    unsupported = next(row for row in rows if row["role"] == "repo_level")
    assert unsupported["confidence"] == "low"
    assert unsupported["found_by"] == "deterministic_classifier"
    assert unsupported["file"] is None


def test_classify_evidence_links_rows_to_goal_ids(git_repo: Path):
    ctx = _ctx(git_repo)

    rows = classify_evidence(ctx)
    goal_spec = read_json(ctx.paths.goal_spec)

    assert {row["goal_id"] for row in rows} == {goal_spec["success_goals"][0]["goal_id"]}
