from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _docs_text() -> str:
    paths = [
        ROOT / "README.md",
        ROOT / "IMPLEMENTATION_STATUS.md",
        ROOT / "docs" / "goal_progress_and_partial_apply.md",
        ROOT / "docs" / "workflow_lifecycle.md",
        ROOT / "docs" / "cli.md",
        ROOT / "docs" / "real_codex_smoke.md",
        ROOT / "docs" / "runbooks" / "real_codex_smoke_runbook.md",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths if path.exists()).lower()


def test_docs_explain_stop_after_current_safe_point():
    text = _docs_text()
    assert "after-current" in text
    assert "safe point" in text


def test_docs_explain_no_next_patchlet_after_stop():
    text = _docs_text()
    assert "next patchlet" in text
    assert "does not start" in text or "no next patchlet" in text


def test_docs_explain_stop_result_checkpoint():
    text = _docs_text()
    assert "stop_result.json" in text
    assert "accepted checkpoint" in text


def test_docs_explain_partial_apply_accepted_only():
    text = _docs_text()
    assert "allow-partial" in text
    assert "accepted" in text
    assert "pending" in text


def test_docs_explain_stop_before_checkpoint_no_applyable_progress():
    text = _docs_text()
    assert "no accepted checkpoint" in text
    assert "applyable_progress=false" in text or "applyable progress false" in text
