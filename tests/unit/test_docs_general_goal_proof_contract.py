from pathlib import Path


def _docs_text() -> str:
    return "\n".join([
        Path("docs/general_goal_proof_contract.md").read_text(encoding="utf-8"),
        Path("README.md").read_text(encoding="utf-8"),
    ])


def test_docs_explain_master_prompt_source_of_truth():
    assert "read-only source of truth" in _docs_text()


def test_docs_explain_master_prompt_frozen_artifact():
    assert "master_prompt_frozen.json" in _docs_text()


def test_docs_explain_goal_interpretation_is_not_proof():
    assert "not proof" in _docs_text()


def test_docs_explain_early_provability():
    assert "provability_result.json" in _docs_text()


def test_docs_explain_proof_obligations():
    assert "proof_obligations.json" in _docs_text()


def test_docs_explain_probe_plan():
    assert "probe_plan.json" in _docs_text()


def test_docs_explain_independent_rerun():
    assert "independent_probe_rerun_result.json" in _docs_text()


def test_docs_explain_goal_coverage_gate():
    assert "goal_coverage_gate_result.json" in _docs_text()


def test_docs_explain_master_prompt_concordance():
    assert "master_prompt_concordance_result.json" in _docs_text()


def test_docs_explain_master_prompt_satisfaction():
    assert "master_prompt_satisfaction_result.json" in _docs_text()


def test_docs_explain_done_requires_master_prompt_satisfaction():
    text = _docs_text()
    assert "DONE requires" in text and "master prompt satisfaction" in text


def test_docs_explain_no_compatibility_fast_path():
    text = _docs_text()
    assert "no compatibility fast path" in text.lower()
    assert "app.py" in text and "app.main" in text


def test_worker_semantic_docs_use_only_canonical_goal_item_id():
    text = "\n".join([
        Path("docs/general_goal_proof_contract.md").read_text(encoding="utf-8"),
        Path("docs/real_codex_smoke.md").read_text(encoding="utf-8"),
        Path("docs/semantic_goal_satisfaction.md").read_text(encoding="utf-8"),
    ])
    assert "goal_item_id" in text
    assert '`{"goal_item":' not in text
    assert "with `goal_item` and" not in text
