from __future__ import annotations

import json
import re
from pathlib import Path

from codex_orchestrator.operator_events import (
    append_operator_event,
    operator_events_path,
    read_operator_events,
    summarize_latest_operator_event,
)
from codex_orchestrator.validators.schema_validator import validate_json


def test_append_operator_event_creates_operator_events_jsonl(tmp_path: Path):
    event = append_operator_event(tmp_path, "patchlet_started", stage="PATCHLETS_READY")

    assert operator_events_path(tmp_path).exists()
    assert event["event_id"] == "OE000001"


def test_append_operator_event_assigns_monotonic_event_id(tmp_path: Path):
    first = append_operator_event(tmp_path, "patchlet_started")
    second = append_operator_event(tmp_path, "patchlet_worker_started")

    assert first["event_id"] == "OE000001"
    assert second["event_id"] == "OE000002"


def test_append_operator_event_preserves_existing_events(tmp_path: Path):
    append_operator_event(tmp_path, "patchlet_started")
    append_operator_event(tmp_path, "patchlet_worker_started")

    assert len(operator_events_path(tmp_path).read_text(encoding="utf-8").splitlines()) == 2


def test_append_operator_event_contains_required_fields(tmp_path: Path):
    event = append_operator_event(tmp_path, "patchlet_started", stage="STAGE", summary="Started.")

    for key in ["schema_version", "kind", "event_id", "created_at", "event_type", "severity", "stage", "summary", "artifact_paths"]:
        assert key in event
    assert event["kind"] == "operator_event"


def test_append_operator_event_uses_utc_created_at(tmp_path: Path):
    event = append_operator_event(tmp_path, "patchlet_started")

    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", event["created_at"])


def test_append_operator_event_defaults_artifact_paths_to_empty_list(tmp_path: Path):
    event = append_operator_event(tmp_path, "patchlet_started")

    assert event["artifact_paths"] == []


def test_append_operator_event_accepts_patchlet_attempt_and_prompt_fields(tmp_path: Path):
    event = append_operator_event(
        tmp_path,
        "patchlet_prompt_written",
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
        prompt_id="PR000001",
        prompt_path=".codex-orchestrator/runs/P0001_attempt1/codex_task_prompt.md",
    )

    assert event["patchlet_id"] == "P0001"
    assert event["attempt_id"] == "P0001_attempt1"
    assert event["prompt_id"] == "PR000001"
    assert event["prompt_path"].endswith("codex_task_prompt.md")


def test_operator_event_schema_validates_generated_event(tmp_path: Path):
    event = append_operator_event(tmp_path, "patchlet_started")

    assert validate_json(event, "operator_event.schema.json") == []


def test_read_operator_events_returns_events_in_order(tmp_path: Path):
    append_operator_event(tmp_path, "one")
    append_operator_event(tmp_path, "two")

    assert [event["event_type"] for event in read_operator_events(tmp_path)] == ["one", "two"]


def test_read_operator_events_since_event_id(tmp_path: Path):
    append_operator_event(tmp_path, "one")
    append_operator_event(tmp_path, "two")

    assert [event["event_type"] for event in read_operator_events(tmp_path, since="OE000001")] == ["two"]


def test_read_operator_events_limit(tmp_path: Path):
    append_operator_event(tmp_path, "one")
    append_operator_event(tmp_path, "two")

    assert [event["event_type"] for event in read_operator_events(tmp_path, limit=1)] == ["two"]


def test_read_operator_events_filters_by_attempt(tmp_path: Path):
    append_operator_event(tmp_path, "one", attempt_id="A1")
    append_operator_event(tmp_path, "two", attempt_id="A2")

    assert [event["event_type"] for event in read_operator_events(tmp_path, attempt_id="A2")] == ["two"]


def test_read_operator_events_filters_by_patchlet(tmp_path: Path):
    append_operator_event(tmp_path, "one", patchlet_id="P1")
    append_operator_event(tmp_path, "two", patchlet_id="P2")

    assert [event["event_type"] for event in read_operator_events(tmp_path, patchlet_id="P2")] == ["two"]


def test_read_operator_events_filters_by_event_type(tmp_path: Path):
    append_operator_event(tmp_path, "one")
    append_operator_event(tmp_path, "two")

    assert [event["event_type"] for event in read_operator_events(tmp_path, event_type="two")] == ["two"]


def test_read_operator_events_tolerates_missing_file(tmp_path: Path):
    assert read_operator_events(tmp_path) == []


def test_read_operator_events_ignores_blank_lines(tmp_path: Path):
    path = operator_events_path(tmp_path)
    path.parent.mkdir(parents=True)
    event = {
        "schema_version": "1.0",
        "kind": "operator_event",
        "event_id": "OE000001",
        "created_at": "2026-07-03T00:00:00Z",
        "event_type": "one",
        "severity": "info",
        "stage": None,
        "summary": "one",
        "artifact_paths": [],
    }
    path.write_text("\n" + json.dumps(event) + "\n", encoding="utf-8")

    assert len(read_operator_events(tmp_path)) == 1


def test_read_operator_events_ignores_incomplete_trailing_line(tmp_path: Path):
    append_operator_event(tmp_path, "one")
    with operator_events_path(tmp_path).open("a", encoding="utf-8") as handle:
        handle.write("{")

    assert [event["event_type"] for event in read_operator_events(tmp_path)] == ["one"]


def test_summarize_latest_operator_event_returns_latest_event(tmp_path: Path):
    append_operator_event(tmp_path, "one")
    append_operator_event(tmp_path, "two")

    assert summarize_latest_operator_event(tmp_path)["event_type"] == "two"


def test_summarize_latest_operator_event_returns_none_for_missing_file(tmp_path: Path):
    assert summarize_latest_operator_event(tmp_path) is None
