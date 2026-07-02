from __future__ import annotations

import pytest

from codex_orchestrator.live_progress import (
    LiveProgressPolicyError,
    compact_codex_signal,
    resolve_live_progress_policy,
)


def test_live_progress_policy_defaults_quiet_for_default_suite():
    policy = resolve_live_progress_policy({})

    assert policy.enabled is False
    assert policy.sink == "none"
    assert policy.interval_seconds == 15


def test_live_progress_policy_enabled_by_env():
    policy = resolve_live_progress_policy({"CXOR_LIVE_CODEX_PROGRESS": "1"})

    assert policy.enabled is True
    assert policy.sink == "stderr"


def test_live_progress_policy_disabled_by_env():
    policy = resolve_live_progress_policy({"CXOR_LIVE_CODEX_PROGRESS": "0"})

    assert policy.enabled is False
    assert policy.sink == "none"


def test_live_progress_policy_validates_positive_interval():
    with pytest.raises(LiveProgressPolicyError) as excinfo:
        resolve_live_progress_policy({"CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS": "0"})

    assert "CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS" in str(excinfo.value)
    assert "expected positive integer seconds" in str(excinfo.value)


def test_live_progress_compacts_known_codex_events():
    assert compact_codex_signal({"type": "thread.started"}) == "thread.started"
    assert compact_codex_signal({"type": "turn.started"}) == "turn.started"
    assert compact_codex_signal({"type": "turn.completed"}) == "turn.completed"
    assert compact_codex_signal({"type": "item.started", "item": {"type": "command_execution"}}) == "command.started"
    assert compact_codex_signal({"type": "item.completed", "item": {"type": "command_execution"}}) == "command.completed"
    assert compact_codex_signal({"type": "item.completed", "item": {"type": "agent_message"}}) == "message"
