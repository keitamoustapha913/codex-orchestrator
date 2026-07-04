from pathlib import Path


DOC_PATHS = [
    Path("README.md"),
    Path("docs/semantic_goal_satisfaction.md"),
    Path("docs/cli.md"),
    Path("docs/autonomous_loop.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/release.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/workflow_lifecycle.md"),
    Path("docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOC_PATHS)


def test_docs_explain_semantic_goal_spec():
    assert "semantic_goal_spec.json" in _docs_text()


def test_docs_explain_structured_criteria():
    text = _docs_text()
    assert "structured" in text
    assert "criteria" in text


def test_docs_explain_python_main_return_parser():
    text = _docs_text()
    assert "Python main-return" in text or "Python main return" in text
    assert "app.main()" in text


def test_docs_explain_goal_satisfaction_gate():
    assert "goal_satisfaction_gate_result.json" in _docs_text()


def test_docs_explain_semantic_goal_runner():
    text = _docs_text()
    assert "semantic goal runner" in text
    assert "semantic_goal_check_result.json" in text


def test_docs_explain_verified_no_change_requires_goal_proof():
    text = _docs_text()
    assert "VERIFIED_NO_CHANGE_NEEDED" in text
    assert "independent" in text


def test_docs_explain_done_requires_semantic_pass_for_structured_goals():
    text = _docs_text()
    assert "DONE" in text
    assert "semantic pass" in text
    assert "structured goals" in text


def test_docs_explain_semantic_goal_unsatisfied_diagnosis():
    assert "semantic_goal_unsatisfied" in _docs_text()


def test_docs_explain_status_semantic_goal_fields():
    text = _docs_text()
    assert "cxor status --json" in text
    assert "semantic_goal" in text


def test_docs_include_ok_vs_me_false_positive_example():
    text = _docs_text()
    assert '"ok"' in text
    assert '"me"' in text
    assert "does not satisfy" in text


def test_usage_guide_mentions_semantic_goal_satisfaction():
    text = Path("docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md").read_text(
        encoding="utf-8"
    )
    assert "Semantic Goal Satisfaction" in text
