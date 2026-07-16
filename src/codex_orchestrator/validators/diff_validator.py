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
    slice_boundary_violations: list[dict] | None = None
    path_classifications: dict[str, str] | None = None


def _norm(path: str) -> str:
    p = PurePosixPath(path.replace("\\", "/")).as_posix()
    return p[2:] if p.startswith("./") else p


def _is_under(path: str, prefix: str) -> bool:
    path = _norm(path)
    prefix = _norm(prefix).rstrip("/") + "/"
    return path.startswith(prefix)


def _is_under_or_equal(path: str, prefix: str) -> bool:
    path = _norm(path).rstrip("/")
    prefix = _norm(prefix).rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def _is_approved_artifact_directory_granularity(path: str, prefixes: list[str]) -> bool:
    path = _norm(path).rstrip("/")
    approved_roots = {".artifacts", ".codex-orchestrator"}
    return path in approved_roots and any(_norm(prefix).rstrip("/").startswith(path + "/") or _norm(prefix).rstrip("/") == path for prefix in prefixes)


def _changed_key_values(diff_text: str, allowed_file: str) -> dict[str, tuple[str | None, str | None]]:
    old: dict[str, str] = {}
    new: dict[str, str] = {}
    in_file = False
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            in_file = f" b/{allowed_file}" in line or line.endswith(f" {allowed_file}")
            continue
        if not in_file:
            continue
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@"):
            continue
        if len(line) < 2 or line[0] not in {"-", "+"}:
            continue
        content = line[1:].strip()
        if not content or content.startswith("#") or "=" not in content:
            continue
        key, value = content.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if line[0] == "-":
            old[key] = value
        else:
            new[key] = value
    changed: dict[str, tuple[str | None, str | None]] = {}
    for key in sorted(set(old) | set(new)):
        if old.get(key) != new.get(key):
            changed[key] = (old.get(key), new.get(key))
    return changed


def _slice_boundary_violations(*, diff_text: str | None, patchlet: dict, allowed_product_file: str) -> list[dict]:
    boundary = patchlet.get("slice_change_boundary") or {}
    if not boundary or not diff_text:
        return []
    allowed_keys = {
        row.get("key")
        for row in boundary.get("allowed_changes", [])
        if row.get("key")
    }
    allowed_expected = {
        row.get("key"): (row.get("old_value"), row.get("new_value"))
        for row in boundary.get("allowed_changes", [])
        if row.get("key")
    }
    forbidden_keys = {
        row.get("key")
        for row in boundary.get("forbidden_changes", [])
        if row.get("key")
    }
    changed = _changed_key_values(diff_text, allowed_product_file)
    violations: list[dict] = []
    for key, (old_value, new_value) in changed.items():
        if key in forbidden_keys:
            violations.append({"path": allowed_product_file, "key": key, "reason": "future_slice_change"})
            continue
        if allowed_keys and key not in allowed_keys:
            violations.append({"path": allowed_product_file, "key": key, "reason": "outside_slice_change_boundary"})
            continue
        expected = allowed_expected.get(key)
        if expected and expected != (old_value, new_value):
            violations.append(
                {
                    "path": allowed_product_file,
                    "key": key,
                    "reason": "allowed_change_value_mismatch",
                    "expected": {"old": expected[0], "new": expected[1]},
                    "actual": {"old": old_value, "new": new_value},
                }
            )
    for key, expected in sorted(allowed_expected.items()):
        if key not in changed:
            violations.append(
                {
                    "path": allowed_product_file,
                    "key": key,
                    "reason": "required_slice_change_absent",
                    "expected": {"old": expected[0], "new": expected[1]},
                }
            )
    return violations


def validate_changed_paths(changed_paths: list[str], patchlet: dict, *, diff_text: str | None = None) -> DiffValidationResult:
    allowed_product_file = _norm(patchlet.get("allowed_product_runtime_file", ""))
    allowed_artifact_dirs = patchlet.get("allowed_artifact_dirs") or []
    recorded_artifact_roots = patchlet.get("recorded_execution_artifact_roots") or []
    artifact_paths: list[str] = []
    product_paths: list[str] = []
    unauthorized: list[str] = []
    classifications: dict[str, str] = {}

    for raw in changed_paths:
        path = _norm(raw)
        if path in FROZEN_WORKFLOW_FILES:
            unauthorized.append(path)
            classifications[path] = "FROZEN_WORKFLOW_FILE"
            continue
        if (
            any(_is_under_or_equal(path, prefix) for prefix in allowed_artifact_dirs)
            or any(_is_under_or_equal(path, prefix) for prefix in recorded_artifact_roots)
            or _is_approved_artifact_directory_granularity(path, list(allowed_artifact_dirs) + list(recorded_artifact_roots))
        ):
            artifact_paths.append(path)
            classifications[path] = "ARTIFACT_ALLOWED"
            continue
        product_paths.append(path)
        if path != allowed_product_file:
            unauthorized.append(path)
            classifications[path] = "UNAUTHORIZED_PRODUCT_OR_UNKNOWN"
        else:
            classifications[path] = "PRODUCT_FILE_CANDIDATE_FOR_SLICE_BOUNDARY_CHECK"

    if len(set(product_paths)) > 1:
        for path in product_paths:
            if path != allowed_product_file and path not in unauthorized:
                unauthorized.append(path)

    slice_violations = _slice_boundary_violations(
        diff_text=diff_text,
        patchlet=patchlet,
        allowed_product_file=allowed_product_file,
    )
    if slice_violations and allowed_product_file not in unauthorized:
        unauthorized.append(allowed_product_file)

    return DiffValidationResult(
        allowed=not unauthorized and not slice_violations,
        unauthorized_paths=sorted(set(unauthorized)),
        product_runtime_paths=sorted(set(product_paths)),
        artifact_paths=sorted(set(artifact_paths)),
        slice_boundary_violations=slice_violations,
        path_classifications=classifications,
    )
