from __future__ import annotations

import pytest

from codex_orchestrator.codex_execution_policy import (
    ExecutionPolicyError,
    resolve_patchlet_timeout_seconds,
    resolve_progress_interval_seconds,
)


def test_invalid_codex_patchlet_timeout_seconds_reports_structured_error():
    with pytest.raises(ExecutionPolicyError) as exc:
        resolve_patchlet_timeout_seconds({"CODEX_PATCHLET_TIMEOUT_SECONDS": "abc"})

    message = str(exc.value)
    assert "CODEX_PATCHLET_TIMEOUT_SECONDS" in message
    assert "abc" in message
    assert "expected positive integer seconds" in message


def test_invalid_codex_timeout_seconds_reports_structured_error():
    with pytest.raises(ExecutionPolicyError) as exc:
        resolve_patchlet_timeout_seconds({"CODEX_TIMEOUT_SECONDS": "abc"})

    message = str(exc.value)
    assert "CODEX_TIMEOUT_SECONDS" in message
    assert "abc" in message
    assert "expected positive integer seconds" in message


def test_zero_timeout_seconds_reports_structured_error():
    with pytest.raises(ExecutionPolicyError) as exc:
        resolve_patchlet_timeout_seconds({"CODEX_TIMEOUT_SECONDS": "0"})

    message = str(exc.value)
    assert "CODEX_TIMEOUT_SECONDS" in message
    assert "0" in message
    assert "expected positive integer seconds" in message


def test_negative_timeout_seconds_reports_structured_error():
    with pytest.raises(ExecutionPolicyError) as exc:
        resolve_patchlet_timeout_seconds({"CODEX_PATCHLET_TIMEOUT_SECONDS": "-1"})

    message = str(exc.value)
    assert "CODEX_PATCHLET_TIMEOUT_SECONDS" in message
    assert "-1" in message
    assert "expected positive integer seconds" in message


def test_invalid_progress_interval_reports_structured_error():
    with pytest.raises(ExecutionPolicyError) as exc:
        resolve_progress_interval_seconds({"CODEX_PROGRESS_INTERVAL_SECONDS": "fast"})

    message = str(exc.value)
    assert "CODEX_PROGRESS_INTERVAL_SECONDS" in message
    assert "fast" in message
    assert "expected positive integer seconds" in message
