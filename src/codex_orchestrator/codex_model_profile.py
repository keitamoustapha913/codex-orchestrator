from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


PATCHLET_DEFAULT_MODEL = "gpt-5.4-mini"
ORCHESTRATOR_DEFAULT_MODEL = "gpt-5.5"
DEFAULT_REASONING = "medium"


@dataclass(frozen=True)
class CodexModelProfile:
    model: str
    reasoning: str


def resolve_codex_model_profile(kind: str, env: Mapping[str, str]) -> CodexModelProfile:
    if kind == "patchlet":
        return CodexModelProfile(
            model=env.get("CODEX_PATCHLET_MODEL") or env.get("CODEX_MODEL") or PATCHLET_DEFAULT_MODEL,
            reasoning=env.get("CODEX_PATCHLET_REASONING") or env.get("CODEX_REASONING") or DEFAULT_REASONING,
        )
    if kind in {"orchestrator", "master_prompt", "group", "transaction", "global", "repair"}:
        return CodexModelProfile(
            model=env.get("CODEX_ORCHESTRATOR_MODEL") or env.get("CODEX_MODEL") or ORCHESTRATOR_DEFAULT_MODEL,
            reasoning=env.get("CODEX_ORCHESTRATOR_REASONING") or env.get("CODEX_REASONING") or DEFAULT_REASONING,
        )
    raise ValueError(f"unsupported Codex model profile kind: {kind}")
