from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Mapping

from codex_orchestrator.errors import CxorError


DEFAULT_LIVE_PROGRESS_INTERVAL_SECONDS = 15


class LiveProgressPolicyError(CxorError):
    """Raised when live progress environment variables are invalid."""


@dataclass(frozen=True)
class LiveProgressPolicy:
    enabled: bool
    interval_seconds: int
    sink: str


def resolve_live_progress_policy(env: Mapping[str, str], *, default_enabled: bool = False) -> LiveProgressPolicy:
    enabled = default_enabled
    value = env.get("CXOR_LIVE_CODEX_PROGRESS")
    if value == "1":
        enabled = True
    elif value == "0":
        enabled = False
    elif value:
        raise LiveProgressPolicyError(
            f"CXOR_LIVE_CODEX_PROGRESS={value!r} is invalid; expected 1 or 0"
        )
    elif env.get("CODEX_PROGRESS_STDERR") == "1":
        enabled = True

    interval = _positive_integer_seconds(
        "CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS",
        env.get("CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS"),
        DEFAULT_LIVE_PROGRESS_INTERVAL_SECONDS,
    )
    return LiveProgressPolicy(
        enabled=enabled,
        interval_seconds=interval,
        sink="stderr" if enabled else "none",
    )


def compact_codex_signal(event: Mapping[str, object]) -> str | None:
    event_type = event.get("type") or event.get("event") or event.get("kind")
    if not isinstance(event_type, str) or not event_type:
        return None
    item = event.get("item")
    item_type = item.get("type") if isinstance(item, dict) else None
    if event_type == "item.started" and item_type == "command_execution":
        return "command.started"
    if event_type == "item.completed" and item_type == "command_execution":
        return "command.completed"
    if event_type == "item.completed" and item_type == "agent_message":
        return "message"
    if event_type in {"thread.started", "turn.started", "turn.completed"}:
        return event_type
    if event_type in {"process.started"}:
        return event_type
    return "event"


class LiveProgressReporter:
    def __init__(self, policy: LiveProgressPolicy, *, attempt_id: str) -> None:
        self.policy = policy
        self.attempt_id = attempt_id
        self._last_signal_at: dict[str, float] = {}

    def emit(self, signal: str, elapsed_seconds: float, *, force: bool = False) -> None:
        if not self.policy.enabled or self.policy.sink == "none":
            return
        if not force:
            previous = self._last_signal_at.get(signal)
            if previous is not None and elapsed_seconds - previous < self.policy.interval_seconds:
                return
        self._last_signal_at[signal] = elapsed_seconds
        print(
            f"[cxor:{self.attempt_id} +{int(elapsed_seconds):03d}s] codex: {signal}",
            file=sys.stderr,
            flush=True,
        )

    def emit_status(self, message: str, elapsed_seconds: float, *, force: bool = False) -> None:
        if not self.policy.enabled or self.policy.sink == "none":
            return
        signal = f"status:{message}"
        if not force:
            previous = self._last_signal_at.get(signal)
            if previous is not None and elapsed_seconds - previous < self.policy.interval_seconds:
                return
        self._last_signal_at[signal] = elapsed_seconds
        print(
            f"[cxor:{self.attempt_id} +{int(elapsed_seconds):03d}s] {message}",
            file=sys.stderr,
            flush=True,
        )


def _positive_integer_seconds(env_var: str, value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise LiveProgressPolicyError(
            f"{env_var}={value!r} is invalid; expected positive integer seconds"
        ) from exc
    if parsed <= 0:
        raise LiveProgressPolicyError(
            f"{env_var}={value!r} is invalid; expected positive integer seconds"
        )
    return parsed
