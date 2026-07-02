from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


FROZEN_WORKFLOW_FILES = {
    ".codex-orchestrator/master_prompt.md",
    ".codex-orchestrator/goal_spec.json",
    ".codex-orchestrator/inventory_graph.json",
    ".codex-orchestrator/inventory_table.md",
    ".codex-orchestrator/invariants.json",
    ".codex-orchestrator/path_mapping.json",
}


@dataclass(frozen=True)
class DiffValidationResult:
    allowed: bool
    unauthorized_paths: list[str]
    product_runtime_paths: list[str]
    artifact_paths: list[str]


def _norm(path: str) -> str:
    p = PurePosixPath(path.replace("\\", "/")).as_posix()
    return p[2:] if p.startswith("./") else p


def _is_under(path: str, prefix: str) -> bool:
    path = _norm(path)
    prefix = _norm(prefix).rstrip("/") + "/"
    return path.startswith(prefix)


def validate_changed_paths(changed_paths: list[str], patchlet: dict) -> DiffValidationResult:
    allowed_product_file = _norm(patchlet.get("allowed_product_runtime_file", ""))
    allowed_artifact_dirs = patchlet.get("allowed_artifact_dirs") or []
    artifact_paths: list[str] = []
    product_paths: list[str] = []
    unauthorized: list[str] = []

    for raw in changed_paths:
        path = _norm(raw)
        if path in FROZEN_WORKFLOW_FILES:
            unauthorized.append(path)
            continue
        if any(_is_under(path, prefix) for prefix in allowed_artifact_dirs):
            artifact_paths.append(path)
            continue
        product_paths.append(path)
        if path != allowed_product_file:
            unauthorized.append(path)

    if len(set(product_paths)) > 1:
        for path in product_paths:
            if path != allowed_product_file and path not in unauthorized:
                unauthorized.append(path)

    return DiffValidationResult(
        allowed=not unauthorized,
        unauthorized_paths=sorted(set(unauthorized)),
        product_runtime_paths=sorted(set(product_paths)),
        artifact_paths=sorted(set(artifact_paths)),
    )
