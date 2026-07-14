from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.operator_events import append_operator_event


EXCLUDED_DIR_PREFIXES = (
    ".codex-orchestrator/",
    ".artifacts/",
    ".git/",
    "__pycache__/",
)


def _is_artifact_path(path: str) -> bool:
    return (
        any(path.startswith(prefix) for prefix in EXCLUDED_DIR_PREFIXES)
        or "/__pycache__/" in path
        or path.endswith(".pyc")
    )


def _docs_are_target(goal_interpretation: dict[str, Any]) -> bool:
    text = " ".join(
        str(item.get("text", ""))
        for item in goal_interpretation.get("goal_items", [])
    ).lower()
    return any(word in text for word in ("readme", "documentation", "docs", "document"))


def _is_product_runtime_file(path: str, goal_interpretation: dict[str, Any]) -> bool:
    if _is_artifact_path(path):
        return False
    name = Path(path).name
    if name in {"master_prompt.md"}:
        return False
    if path.startswith("tests/") or "/tests/" in path or name.startswith("test_") or name.endswith("_test.py"):
        return False
    if path.startswith("docs/") or name.lower().endswith((".md", ".rst")):
        return _docs_are_target(goal_interpretation)
    return True


def _module_to_path(path: str) -> str:
    p = Path(path)
    if p.name == "__init__.py":
        return p.parent.as_posix().replace("/", ".")
    if p.suffix == ".py":
        return p.with_suffix("").as_posix().replace("/", ".")
    return p.as_posix().replace("/", ".")


def _imported_modules(repo_root: Path, path: str) -> list[str]:
    if not path.endswith(".py"):
        return []
    file_path = repo_root / path
    if not file_path.exists():
        return []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return sorted(set(modules))


def _goal_item_ids(goal_interpretation: dict[str, Any]) -> list[str]:
    ids = [item.get("goal_item_id") for item in goal_interpretation.get("goal_items", []) if item.get("goal_item_id")]
    return ids or ["GI001"]


def _proof_obligation_ids(proof_obligations: dict[str, Any]) -> list[str]:
    ids = [item.get("obligation_id") for item in proof_obligations.get("obligations", []) if item.get("obligation_id")]
    return ids or ["PO001"]


def _goal_items(goal_interpretation: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in goal_interpretation.get("goal_items", []) if item.get("goal_item_id")]


def _obligations(proof_obligations: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in proof_obligations.get("obligations", []) if item.get("obligation_id")]


def _row_mentions_file(row: dict[str, Any], path: str) -> bool:
    haystack: list[str] = []
    for key in ("target_boundaries", "affected_runtime_boundaries", "entrypoints"):
        value = row.get(key)
        if isinstance(value, list):
            haystack.extend(str(item) for item in value)
        elif value:
            haystack.append(str(value))
    repo_context = row.get("repo_context")
    if isinstance(repo_context, dict):
        for key in ("target_boundaries", "affected_runtime_boundaries", "entrypoints"):
            value = repo_context.get(key)
            if isinstance(value, list):
                haystack.extend(str(item) for item in value)
            elif value:
                haystack.append(str(value))
    path_name = Path(path).name
    return any(item == path or Path(item).name == path_name for item in haystack)


def _ids_for_file(*, path: str, goal_interpretation: dict[str, Any], proof_obligations: dict[str, Any]) -> tuple[list[str], list[str]]:
    goal_ids = [item["goal_item_id"] for item in _goal_items(goal_interpretation) if _row_mentions_file(item, path)]
    obligation_ids = [item["obligation_id"] for item in _obligations(proof_obligations) if _row_mentions_file(item, path)]
    return goal_ids, obligation_ids


def _match_evidence(row: dict[str, Any], path: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    path_name = Path(path).name
    for location, source in (("row", row), ("repo_context", row.get("repo_context"))):
        if not isinstance(source, dict):
            continue
        for key in ("target_boundaries", "affected_runtime_boundaries", "entrypoints"):
            value = source.get(key)
            values = value if isinstance(value, list) else [value] if value else []
            for item in values:
                text = str(item)
                if text == path or Path(text).name == path_name:
                    evidence.append(
                        {
                            "planning_field": f"{location}.{key}",
                            "matched_value": text,
                            "match_type": "path" if text == path else "basename",
                        }
                    )
    return evidence


def _suggested_slice_types(path: str, *, inbound: bool, outbound: bool, content: str) -> list[str]:
    name = Path(path).name
    lowered = content.lower()
    suggested: list[str] = []
    if name == "app.py" or "def main" in lowered:
        suggested.append("entrypoint_wiring")
    if any(token in name for token in ("service", "pipeline")):
        suggested.append("business_logic_change")
    if "valid" in name or "validate" in lowered:
        suggested.append("validation_adjustment")
    if "format" in name or "format_" in lowered:
        suggested.append("formatting_adjustment")
    if any(token in name for token in ("config", "settings")):
        suggested.append("configuration_adjustment")
    if inbound and outbound:
        suggested.append("dependency_bridge")
    if inbound and name == "app.py":
        suggested.append("final_integration_adjustment")
    return suggested or ["runtime_behavior_change"]


def _expand_slice_types(types: list[str], minimum_count: int) -> list[str]:
    if minimum_count <= len(types):
        return types
    ordered = [
        "configuration_adjustment",
        "validation_adjustment",
        "formatting_adjustment",
        "runtime_behavior_change",
        "final_integration_adjustment",
        "business_logic_change",
        "dependency_bridge",
        "entrypoint_wiring",
    ]
    expanded = list(types)
    for item in ordered:
        if item not in expanded:
            expanded.append(item)
        if len(expanded) >= minimum_count:
            return expanded
    while len(expanded) < minimum_count:
        expanded.append(f"runtime_behavior_change_{len(expanded) + 1}")
    return expanded


_KEY_VALUE_RE = re.compile(r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+)=([^\s,;`]+)")


def _key_value_state(content: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            rows.append({"key": key, "value": value, "line": stripped})
    return rows


def _desired_key_values_for_file(*, path: str, proof_obligations: dict[str, Any]) -> list[dict[str, Any]]:
    desired: list[dict[str, Any]] = []
    for obligation in _obligations(proof_obligations):
        if not _row_mentions_file(obligation, path):
            continue
        text = " ".join(str(obligation.get(key, "")) for key in ("claim", "description", "expected"))
        for match in _KEY_VALUE_RE.finditer(text):
            desired.append(
                {
                    "key": match.group(1),
                    "new_value": match.group(2).rstrip("."),
                    "proof_obligation_ids": [obligation["obligation_id"]],
                    "goal_item_ids": list(obligation.get("goal_item_ids", [])),
                }
            )
    return desired


def build_impact_dependency_analysis(
    *,
    repo_root: Path,
    inventory_graph: dict[str, Any],
    proof_obligations: dict[str, Any],
    goal_interpretation: dict[str, Any],
) -> dict[str, Any]:
    product_nodes = [
        node
        for node in inventory_graph.get("nodes", [])
        if node.get("file") and _is_product_runtime_file(str(node["file"]), goal_interpretation)
    ]
    module_paths = {_module_to_path(str(node["file"])): str(node["file"]) for node in product_nodes}
    imports_by_file: dict[str, list[str]] = {}
    dependency_edges: list[dict[str, Any]] = []
    for node in product_nodes:
        path = str(node["file"])
        imported_files: list[str] = []
        for module in _imported_modules(repo_root, path):
            imported = module_paths.get(module)
            if imported and imported != path:
                imported_files.append(imported)
                dependency_edges.append(
                    {
                        "from_file": imported,
                        "to_file": path,
                        "edge_type": "import_or_runtime_dependency",
                        "confidence": "medium",
                    }
                )
        imports_by_file[path] = sorted(set(imported_files))
    incoming: dict[str, list[str]] = {str(node["file"]): [] for node in product_nodes}
    for edge in dependency_edges:
        incoming.setdefault(edge["from_file"], [])
        incoming.setdefault(edge["to_file"], []).append(edge["from_file"])
    candidate_files: list[dict[str, Any]] = []
    for node in product_nodes:
        path = str(node["file"])
        content = ""
        try:
            content = (repo_root / path).read_text(encoding="utf-8")
        except OSError:
            pass
        dependency_inputs = imports_by_file.get(path, [])
        dependency_outputs = sorted(edge["to_file"] for edge in dependency_edges if edge["from_file"] == path)
        risk = "medium" if dependency_inputs or dependency_outputs else "low"
        file_goal_ids, file_obligation_ids = _ids_for_file(
            path=path,
            goal_interpretation=goal_interpretation,
            proof_obligations=proof_obligations,
        )
        goal_match_evidence = {
            item["goal_item_id"]: _match_evidence(item, path)
            for item in _goal_items(goal_interpretation)
            if _row_mentions_file(item, path)
        }
        obligation_match_evidence = {
            item["obligation_id"]: _match_evidence(item, path)
            for item in _obligations(proof_obligations)
            if _row_mentions_file(item, path)
        }
        suggested_slice_types = _expand_slice_types(
            _suggested_slice_types(
                path,
                inbound=bool(dependency_inputs),
                outbound=bool(dependency_outputs),
                content=content,
            ),
            max(len(file_goal_ids), len(file_obligation_ids), 1) if (file_goal_ids or file_obligation_ids) else 1,
        )
        candidate_files.append(
            {
                "path": path,
                "inventory_node_ids": [str(node.get("id"))],
                "relevance": "candidate product/runtime file connected to goal evidence and inventory graph",
                "goal_item_ids": file_goal_ids,
                "proof_obligation_ids": file_obligation_ids,
                "probe_ids": [],
                "positive_file_link_evidence": bool(file_goal_ids or file_obligation_ids),
                "goal_match_evidence": goal_match_evidence,
                "obligation_match_evidence": obligation_match_evidence,
                "dependency_inputs": dependency_inputs,
                "dependency_outputs": dependency_outputs,
                "risk_level": risk,
                "suggested_slice_types": suggested_slice_types,
                "content": content,
                "text_key_value_state": _key_value_state(content),
                "desired_key_value_changes": _desired_key_values_for_file(
                    path=path,
                    proof_obligations=proof_obligations,
                ),
            }
        )
    return {
        "schema_version": "1.0",
        "kind": "impact_dependency_analysis",
        "workflow_id": proof_obligations.get("workflow_id") or goal_interpretation.get("workflow_id"),
        "run_id": proof_obligations.get("run_id") or goal_interpretation.get("run_id"),
        "master_prompt_sha256": proof_obligations.get("master_prompt_sha256"),
        "candidate_files": sorted(candidate_files, key=lambda row: row["path"]),
        "dependency_edges": sorted(
            dependency_edges,
            key=lambda row: (row["from_file"], row["to_file"], row["edge_type"]),
        ),
    }


def write_impact_dependency_analysis(*, repo_root: Path, workflow_root: Path, analysis: dict[str, Any]) -> Path:
    path = workflow_root / "decomposition" / "impact_dependency_analysis.json"
    write_json(path, analysis)
    append_operator_event(
        repo_root,
        event_type="impact_analysis_written",
        severity="info",
        stage="WORK_DECOMPOSITION",
        summary=f"Impact analysis written for {len(analysis.get('candidate_files', []))} candidate files.",
        artifact_paths=[".codex-orchestrator/decomposition/impact_dependency_analysis.json"],
        details={"candidate_file_count": len(analysis.get("candidate_files", []))},
    )
    return path
