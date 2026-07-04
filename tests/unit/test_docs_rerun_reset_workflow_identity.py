from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/autonomous_loop.md"),
    Path("docs/release.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/workflow_lifecycle.md"),
    Path("docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _combined_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS if path.exists())


def test_docs_explain_workflow_identity():
    assert "workflow_identity.json" in _combined_docs()


def test_docs_explain_goal_fingerprint():
    assert "goal fingerprint" in _combined_docs()


def test_docs_explain_changed_prompt_requires_new_run():
    text = _combined_docs()
    assert "changed prompt" in text
    assert "--new-run" in text


def test_docs_explain_dirty_target_refusal():
    assert "dirty product/runtime" in _combined_docs()


def test_docs_explain_resume_new_run_force_new_run():
    text = _combined_docs()
    assert "--resume" in text
    assert "--new-run" in text
    assert "--force-new-run" in text


def test_docs_explain_archive_reset():
    text = _combined_docs()
    assert "cxor archive" in text
    assert "cxor reset" in text


def test_docs_explain_workflows_command():
    assert "cxor workflows" in _combined_docs()


def test_docs_explain_invocation_scoped_live_progress():
    text = _combined_docs()
    assert "invocation" in text
    assert "not replayed" in text


def test_docs_explain_apply_results_rerun_guidance():
    assert "latest_apply_result.json" in _combined_docs()


def test_usage_guide_mentions_rc3_rerun_reset_workflow():
    text = Path("docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md").read_text(encoding="utf-8")
    assert "v0.1.0-rc3" in text
    assert "Rerun, Reset" in text
