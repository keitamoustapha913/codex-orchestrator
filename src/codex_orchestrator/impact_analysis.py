from __future__ import annotations

import ast
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
    return path.endswith((".py", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"))


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
    goal_ids = _goal_item_ids(goal_interpretation)
    obligation_ids = _proof_obligation_ids(proof_obligations)
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
        candidate_files.append(
            {
                "path": path,
                "inventory_node_ids": [str(node.get("id"))],
                "relevance": "candidate product/runtime file connected to goal evidence and inventory graph",
                "goal_item_ids": goal_ids,
                "proof_obligation_ids": obligation_ids,
                "dependency_inputs": dependency_inputs,
                "dependency_outputs": dependency_outputs,
                "risk_level": risk,
                "suggested_slice_types": _suggested_slice_types(
                    path,
                    inbound=bool(dependency_inputs),
                    outbound=bool(dependency_outputs),
                    content=content,
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
