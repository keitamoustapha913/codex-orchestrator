from pathlib import Path


def _docs_text() -> str:
    return "\n".join([
        Path("docs/goal_progress_and_partial_apply.md").read_text(encoding="utf-8"),
        Path("docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md").read_text(encoding="utf-8"),
    ])


def test_docs_explain_goal_progress_json():
    assert "goal_progress.json" in _docs_text()


def test_docs_explain_goal_progress_jsonl():
    assert "goal_progress.jsonl" in _docs_text()


def test_docs_explain_goal_progress_cli():
    assert "cxor goal-progress" in _docs_text()


def test_docs_explain_progress_after_each_iteration():
    assert "Progress is updated" in _docs_text()


def test_docs_explain_stop_command():
    assert "cxor stop" in _docs_text()


def test_docs_explain_stop_requested_and_stop_result():
    text = _docs_text()
    assert "stop_requested.json" in text and "stop_result.json" in text


def test_docs_explain_partial_apply():
    assert "Partial apply" in _docs_text()


def test_docs_explain_allow_partial():
    assert "--allow-partial" in _docs_text()


def test_docs_explain_unaccepted_work_not_applied():
    assert "unaccepted worker changes are never applied by default" in _docs_text()


def test_usage_guide_mentions_general_goal_proof():
    assert "General goal proof contract" in Path("docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md").read_text(encoding="utf-8")
