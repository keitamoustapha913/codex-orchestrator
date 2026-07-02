from __future__ import annotations

from typing import Mapping


PATCHLET_DEFAULT_TIMEOUT_SECONDS = 600


def resolve_patchlet_timeout_seconds(env: Mapping[str, str]) -> int:
    value = (
        env.get("CODEX_PATCHLET_TIMEOUT_SECONDS")
        or env.get("CODEX_TIMEOUT_SECONDS")
        or str(PATCHLET_DEFAULT_TIMEOUT_SECONDS)
    )
    return int(value)


def soft_deadline_seconds(timeout_seconds: int) -> int:
    return max(1, timeout_seconds - 60)
