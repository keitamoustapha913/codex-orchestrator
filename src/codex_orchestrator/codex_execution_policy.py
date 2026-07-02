from __future__ import annotations

from typing import Mapping

from codex_orchestrator.errors import CxorError


PATCHLET_DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_PROGRESS_INTERVAL_SECONDS = 30


class ExecutionPolicyError(CxorError):
    """Raised when execution policy environment variables are invalid."""


def resolve_patchlet_timeout_seconds(env: Mapping[str, str]) -> int:
    if env.get("CODEX_PATCHLET_TIMEOUT_SECONDS"):
        return _positive_integer_seconds(
            "CODEX_PATCHLET_TIMEOUT_SECONDS",
            env["CODEX_PATCHLET_TIMEOUT_SECONDS"],
        )
    if env.get("CODEX_TIMEOUT_SECONDS"):
        return _positive_integer_seconds("CODEX_TIMEOUT_SECONDS", env["CODEX_TIMEOUT_SECONDS"])
    return PATCHLET_DEFAULT_TIMEOUT_SECONDS


def resolve_progress_interval_seconds(env: Mapping[str, str]) -> int:
    if env.get("CODEX_PROGRESS_INTERVAL_SECONDS"):
        return _positive_integer_seconds(
            "CODEX_PROGRESS_INTERVAL_SECONDS",
            env["CODEX_PROGRESS_INTERVAL_SECONDS"],
        )
    return DEFAULT_PROGRESS_INTERVAL_SECONDS


def soft_deadline_seconds(timeout_seconds: int) -> int:
    return max(1, timeout_seconds - 60)


def _positive_integer_seconds(env_var: str, value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ExecutionPolicyError(
            f"{env_var}={value!r} is invalid; expected positive integer seconds"
        ) from exc
    if parsed <= 0:
        raise ExecutionPolicyError(
            f"{env_var}={value!r} is invalid; expected positive integer seconds"
        )
    return parsed
