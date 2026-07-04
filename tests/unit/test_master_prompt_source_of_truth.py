from __future__ import annotations

from pathlib import Path

from codex_orchestrator.master_prompt_source import (
    check_master_prompt_source_unchanged,
    freeze_master_prompt,
    make_master_prompt_reference_payload,
)
from codex_orchestrator.validators.schema_validator import validate_json


def test_freezes_master_prompt_with_hash_and_copy_path(tmp_path: Path):
    master = tmp_path / "master_prompt.md"
    master.write_text("Make app return me and prove it.\n", encoding="utf-8")
    workflow = tmp_path / ".codex-orchestrator"

    frozen = freeze_master_prompt(
        repo_root=tmp_path,
        workflow_root=workflow,
        master_prompt_path=master,
        workflow_id="WF000001",
        run_id="R0001",
    )

    assert (workflow / "master_prompt_frozen.json").exists()
    assert (workflow / "master_prompt.md").read_text(encoding="utf-8") == master.read_text(encoding="utf-8")
    assert frozen["frozen_copy_path"] == ".codex-orchestrator/master_prompt.md"
    assert len(frozen["sha256"]) == 64


def test_freeze_records_read_only_source_of_truth_true(tmp_path: Path):
    master = tmp_path / "master_prompt.md"
    master.write_text("Make app return me and prove it.\n", encoding="utf-8")
    frozen = freeze_master_prompt(repo_root=tmp_path, workflow_root=tmp_path / ".codex-orchestrator", master_prompt_path=master, workflow_id=None, run_id=None)
    assert frozen["read_only_source_of_truth"] is True


def test_source_spans_include_full_prompt_for_simple_prompt(tmp_path: Path):
    master = tmp_path / "master_prompt.md"
    master.write_text("Make app return me and prove it.\n", encoding="utf-8")
    frozen = freeze_master_prompt(repo_root=tmp_path, workflow_root=tmp_path / ".codex-orchestrator", master_prompt_path=master, workflow_id=None, run_id=None)
    assert frozen["source_spans"][0]["span_id"] == "MPS001"
    assert frozen["source_spans"][0]["text"] == "Make app return me and prove it.\n"


def test_source_spans_include_line_and_column_metadata(tmp_path: Path):
    master = tmp_path / "master_prompt.md"
    master.write_text("Line one\nLine two\n", encoding="utf-8")
    frozen = freeze_master_prompt(repo_root=tmp_path, workflow_root=tmp_path / ".codex-orchestrator", master_prompt_path=master, workflow_id=None, run_id=None)
    span = frozen["source_spans"][0]
    assert span["line_start"] == 1
    assert span["line_end"] == 2
    assert span["column_start"] == 1
    assert span["column_end"] == 9


def test_downstream_reference_payload_contains_master_prompt_sha(tmp_path: Path):
    master = tmp_path / "master_prompt.md"
    master.write_text("Make app return me and prove it.\n", encoding="utf-8")
    frozen = freeze_master_prompt(repo_root=tmp_path, workflow_root=tmp_path / ".codex-orchestrator", master_prompt_path=master, workflow_id="WF000001", run_id="R0001")
    payload = make_master_prompt_reference_payload(frozen)
    assert payload["master_prompt_sha256"] == frozen["sha256"]
    assert payload["master_prompt_frozen_path"] == ".codex-orchestrator/master_prompt_frozen.json"
    assert payload["workflow_id"] == "WF000001"
    assert payload["run_id"] == "R0001"


def test_changed_source_prompt_after_freeze_is_detected(tmp_path: Path):
    master = tmp_path / "master_prompt.md"
    master.write_text("A\n", encoding="utf-8")
    frozen = freeze_master_prompt(repo_root=tmp_path, workflow_root=tmp_path / ".codex-orchestrator", master_prompt_path=master, workflow_id=None, run_id=None)
    master.write_text("B\n", encoding="utf-8")
    result = check_master_prompt_source_unchanged(frozen=frozen)
    assert result["source_changed_after_freeze"] is True
    assert result["failure_signature"] == "prompt_source_changed_after_freeze"


def test_changed_source_prompt_after_freeze_decision_uses_frozen_copy(tmp_path: Path):
    master = tmp_path / "master_prompt.md"
    master.write_text("A\n", encoding="utf-8")
    frozen = freeze_master_prompt(repo_root=tmp_path, workflow_root=tmp_path / ".codex-orchestrator", master_prompt_path=master, workflow_id=None, run_id=None)
    master.write_text("B\n", encoding="utf-8")
    assert check_master_prompt_source_unchanged(frozen=frozen)["decision"] == "USE_FROZEN_COPY"


def test_missing_source_prompt_after_freeze_does_not_invalidate_frozen_copy(tmp_path: Path):
    master = tmp_path / "master_prompt.md"
    master.write_text("A\n", encoding="utf-8")
    frozen = freeze_master_prompt(repo_root=tmp_path, workflow_root=tmp_path / ".codex-orchestrator", master_prompt_path=master, workflow_id=None, run_id=None)
    master.unlink()
    result = check_master_prompt_source_unchanged(frozen=frozen)
    assert result["source_available"] is False
    assert result["decision"] == "USE_FROZEN_COPY"


def test_master_prompt_frozen_schema_validates(tmp_path: Path):
    master = tmp_path / "master_prompt.md"
    master.write_text("Make app return me and prove it.\n", encoding="utf-8")
    frozen = freeze_master_prompt(repo_root=tmp_path, workflow_root=tmp_path / ".codex-orchestrator", master_prompt_path=master, workflow_id="WF000001", run_id="R0001")
    assert validate_json(frozen, "master_prompt_frozen.schema.json") == []
