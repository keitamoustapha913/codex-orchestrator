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


def test_docs_explain_goal_interpretation_artifacts():
    assert "goal_interpretation/goal_interpretation.json" in _docs_text()


def test_docs_explain_model_mediated_planning():
    text = _docs_text()
    assert "model-mediated goal interpretation" in text
    assert "proof planning" in text
    assert "probe planning" in text


def test_docs_explain_no_python_main_return_parser():
    text = _docs_text()
    assert "no longer supports" in text
    assert "Python-specific" in text
    assert "app.main-specific" in text


def test_docs_explain_goal_coverage_gate():
    assert "goal_coverage_gate_result.json" in _docs_text()


def test_docs_explain_independent_probe_rerun():
    text = _docs_text()
    assert "independent_probe_rerun_result.json" in text
    assert "orchestrator-owned rerun or validation" in text or "independent proof rerun or validation" in text


def test_docs_explain_verified_no_change_requires_goal_proof():
    text = _docs_text()
    assert "VERIFIED_NO_CHANGE_NEEDED" in text
    assert "independent" in text


def test_docs_explain_done_requires_master_prompt_satisfaction():
    text = _docs_text()
    assert "DONE" in text
    assert "master-prompt satisfaction" in text


def test_docs_explain_missing_decomposition_no_fallback():
    assert "do not fall back" in _docs_text()


def test_docs_explain_status_master_prompt_fields():
    text = _docs_text()
    assert "cxor status --json" in text
    assert "master_prompt" in text or "master-prompt" in text


def test_docs_include_one_file_patchlet_rule():
    text = _docs_text()
    assert "exactly one allowed product/runtime file" in text
    assert "Multiple patchlets may target the same file" in text


def test_usage_guide_mentions_master_prompt_satisfaction():
    text = Path("docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md").read_text(
        encoding="utf-8"
    )
    assert "Master Prompt Satisfaction" in text
