from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/autonomous_loop.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/release.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_docs_explain_direct_auto_live_progress():
    assert "cxor auto" in _docs_text()
    assert "--live-progress" in _docs_text()


def test_docs_explain_no_live_progress():
    assert "--no-live-progress" in _docs_text()


def test_docs_explain_progress_interval():
    assert "--progress-interval-seconds" in _docs_text()


def test_docs_explain_progress_format_jsonl():
    text = _docs_text()
    assert "--progress-format jsonl" in text
    assert "structured operator events" in text


def test_docs_explain_operator_events_jsonl():
    assert ".codex-orchestrator/operator_events.jsonl" in _docs_text()


def test_docs_explain_monitor_command():
    assert "cxor monitor --repo /tmp/cxor-target --follow" in _docs_text()


def test_docs_explain_status_watch():
    assert "cxor status --repo /tmp/cxor-target --watch" in _docs_text()


def test_docs_explain_prompts_command():
    assert "cxor prompts --repo /tmp/cxor-target --latest" in _docs_text()


def test_docs_explain_prompt_index():
    assert ".codex-orchestrator/prompt_index.json" in _docs_text()


def test_docs_explain_loop_governor():
    assert ".codex-orchestrator/loop_governor.json" in _docs_text()


def test_docs_explain_repeated_repair_loop_visibility():
    assert "Repeated repair-loop warnings" in _docs_text() or "Repeated repair loops" in _docs_text()


def test_docs_explain_loop_governor_safe_failure():
    text = _docs_text()
    assert "--loop-governor-mode safe-fail" in text
    assert "--max-repeated-failure-signature 3" in text


def test_docs_explain_active_but_silent_vs_stalled():
    text = _docs_text()
    assert "active-but-silent" in text or "silent_but_active" in text
    assert "likely stalled" in text or "likely_stalled" in text


def test_docs_explain_prompt_bodies_not_printed_by_default():
    text = _docs_text()
    assert "prompt bodies are not printed by default" in text.lower()


def test_docs_explain_no_real_codex_in_default_tests():
    assert "Default tests do not run real Codex" in _docs_text() or "Default tests do not invoke real Codex" in _docs_text()


def test_docs_include_manual_direct_auto_live_progress_example():
    text = _docs_text()
    assert "CODEX_PATCHLET_TIMEOUT_SECONDS=600" in text
    assert "--worker-mode real_codex" in text
    assert "--use-worktree" in text
