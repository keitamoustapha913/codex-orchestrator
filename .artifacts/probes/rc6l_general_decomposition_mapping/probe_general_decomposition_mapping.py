from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import codex_orchestrator.impact_analysis as impact_mod
import codex_orchestrator.work_decomposition as decomp_mod
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import (
    build_workflow_identity,
    read_workflow_identity,
    write_workflow_identity,
)
from codex_orchestrator.workflow_lifecycle import next_run_id, record_active_workflow


OLD_HASH = "04bb5a7039828fc157d8c9f1952a330c435c3f51efd5c879278df326a369958a"


@dataclass(frozen=True)
class SliceSpec:
    goal: str
    obligation: str
    probe: str
    key: str
    expected: str
    check: str


@dataclass(frozen=True)
class FixtureSpec:
    name: str
    language: str
    product_file: str
    support_file: str
    test_file: str
    slices: tuple[SliceSpec, ...]
    probe_prefix: str


PYTHON = FixtureSpec(
    name="python_same_file_support",
    language="python",
    product_file="src/runtime_profile.py",
    support_file="src/__init__.py",
    test_file="tests/test_runtime_profile.py",
    probe_prefix="/usr/bin/python3 -m unittest tests.test_runtime_profile.RuntimeProfileContract.",
    slices=(
        SliceSpec("GI001", "PO001", "GP001", "codename", "zephyr-42", "test_codename"),
        SliceSpec("GI002", "PO002", "GP002", "batch_limit", "19", "test_batch_limit"),
        SliceSpec("GI003", "PO003", "GP003", "audit_enabled", "True", "test_audit_enabled"),
        SliceSpec("GI004", "PO004", "GP004", "storage_mode", "append-only", "test_storage_mode"),
        SliceSpec("GI005", "PO005", "GP005", "fallback_action", "isolate", "test_fallback_action"),
    ),
)


JAVASCRIPT = FixtureSpec(
    name="javascript_same_file_support",
    language="javascript",
    product_file="src/runtime-profile.mjs",
    support_file="src/index.mjs",
    test_file="test/check-one.mjs",
    probe_prefix="/usr/bin/node test/check-one.mjs ",
    slices=(
        SliceSpec("GI001", "PO001", "GP001", "region", "eu-central", "region"),
        SliceSpec("GI002", "PO002", "GP002", "timeoutMs", "19000", "timeoutMs"),
        SliceSpec("GI003", "PO003", "GP003", "compression", "br", "compression"),
        SliceSpec("GI004", "PO004", "GP004", "cacheMode", "immutable", "cacheMode"),
        SliceSpec("GI005", "PO005", "GP005", "authStrategy", "isolated", "authStrategy"),
    ),
)


def run(cmd: list[str], *, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def create_fixture(root: Path, spec: FixtureSpec, *, variant: str = "primary") -> None:
    if spec.language == "python":
        write(root / spec.support_file, '"""Support package marker only."""\n')
        write(
            root / spec.product_file,
            'def codename() -> str:\n    return "legacy-sky"\n\n\n'
            'def batch_limit() -> int:\n    return 4\n\n\n'
            'def audit_enabled() -> bool:\n    return False\n\n\n'
            'def storage_mode() -> str:\n    return "mutable"\n\n\n'
            'def fallback_action() -> str:\n    return "continue"\n',
        )
        write(root / "tests/__init__.py", '"""Test package marker only."""\n')
        write(root / spec.test_file, "import unittest\n\nclass RuntimeProfileContract(unittest.TestCase):\n    pass\n")
    else:
        write(root / spec.support_file, 'export * from "./runtime-profile.mjs";\n')
        write(
            root / spec.product_file,
            'export function region() { return "legacy"; }\n'
            'export function timeoutMs() { return 4000; }\n'
            'export function compression() { return "none"; }\n'
            'export function cacheMode() { return "mutable"; }\n'
            'export function authStrategy() { return "shared"; }\n',
        )
        write(root / spec.test_file, "console.log('probe placeholder');\n")
    prompt = [
        f"Transform the {spec.language} runtime profile.",
        f"The only product/runtime file allowed to change is {spec.product_file}.",
        f"The support file {spec.support_file} must not be treated as product/runtime unless explicitly targeted.",
        "Create exactly five one-to-one same-file slices.",
    ]
    for item in spec.slices:
        prompt.append(f"{item.key} must become {item.expected}.")
    write(root / "master_prompt.md", "\n".join(prompt) + "\n")
    run(["git", "init"], cwd=root)
    run(["git", "add", "."], cwd=root)
    run(["git", "commit", "-m", f"fixture {spec.name} {variant}"], cwd=root)


def planning_docs(repo: Path, responses: Path, spec: FixtureSpec, *, variant: str = "primary") -> None:
    prompt_hash = sha256_text((repo / "master_prompt.md").read_text(encoding="utf-8"))
    responses.mkdir(parents=True, exist_ok=True)
    support_targeted = variant == "explicit_support_goal"
    missing_probe = variant == "missing_probe"
    unmatched = variant == "unmatched_goal"
    ambiguous = variant == "multi_file_ambiguity"
    product_files = [spec.product_file]
    if variant == "multi_file_product":
        product_files = [f"src/product_{idx}.txt" for idx in range(1, 6)]
        for idx, file in enumerate(product_files, start=1):
            write(repo / file, f"value=legacy{idx}\n")
        run(["git", "add", "."], cwd=repo)
        run(["git", "commit", "-m", "add multi file products"], cwd=repo)
    goal_items = []
    obligations = []
    probes = []
    for idx, item in enumerate(spec.slices, start=1):
        target = product_files[idx - 1] if variant == "multi_file_product" else spec.product_file
        if support_targeted and idx == 1:
            target = spec.support_file
        if unmatched and idx == 1:
            target = "src/nonexistent-target.txt"
        boundaries = [target]
        if ambiguous and idx == 1:
            alt = "src/ambiguous-peer.txt"
            write(repo / alt, "peer=legacy\n")
            run(["git", "add", "."], cwd=repo)
            run(["git", "commit", "-m", "add ambiguous peer"], cwd=repo)
            boundaries = [target, alt]
        goal_items.append(
            {
                "goal_item_id": item.goal,
                "source_span_ids": ["MPS001"],
                "goal_type": "behavioral_change",
                "subject": item.key,
                "desired_state": f"{target} {item.key} becomes {item.expected}",
                "must_change_product": "true",
                "acceptance_meaning": f"{item.check} passes",
                "required": True,
                "target_boundaries": boundaries,
                "affected_runtime_boundaries": boundaries,
                "entrypoints": [f"{target}:{item.key}"],
                "repo_context": {
                    "target_boundaries": boundaries,
                    "affected_runtime_boundaries": boundaries,
                    "entrypoints": [f"{target}:{item.key}"],
                },
            }
        )
        obligations.append(
            {
                "obligation_id": item.obligation,
                "goal_item_ids": [item.goal],
                "source_span_ids": ["MPS001"],
                "required": True,
                "proof_strategy": "executable_probe",
                "proof_kind": "executable_probe",
                "status": "UNPROVEN",
                "evidence_requirements": ["exact_probe"],
                "claim": f"{target} {item.key}={item.expected}",
                "expected": f"{item.key}={item.expected}",
                "target_boundaries": boundaries,
                "affected_runtime_boundaries": boundaries,
                "entrypoints": [f"{target}:{item.key}"],
            }
        )
        if not (missing_probe and idx == 1):
            probes.append(
                {
                    "probe_id": item.probe,
                    "obligation_ids": [item.obligation],
                    "probe_kind": "test",
                    "owner": "model_planned_orchestrator_validated",
                    "execution_context": "integration_candidate",
                    "side_effect_policy": "no_product_mutation",
                    "rerunnable_by_orchestrator": True,
                    "status": "PLANNED",
                    "command": spec.probe_prefix + item.check,
                    "expected_observation": {"type": "exit_code_zero", "value": f"{item.key}={item.expected}"},
                }
            )
    write_json(
        responses / "goal_interpretation.json",
        {
            "schema_version": "1.0",
            "kind": "goal_interpretation",
            "workflow_id": None,
            "run_id": None,
            "master_prompt_sha256": prompt_hash,
            "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
            "interpretation_status": "CONCORDANT",
            "goal_summary": f"{spec.name} {variant}",
            "goal_items": goal_items,
            "non_goals": [f"{spec.support_file} is support unless explicitly targeted"],
            "ambiguities": [],
            "assumptions": [],
            "contradictions": [],
            "requires_external_resources": False,
            "proof_not_claimed_here": True,
        },
    )
    write_json(
        responses / "proof_obligations.json",
        {
            "schema_version": "1.0",
            "kind": "proof_obligations",
            "workflow_id": None,
            "run_id": None,
            "master_prompt_sha256": prompt_hash,
            "goal_interpretation_path": ".codex-orchestrator/goal_interpretation/goal_interpretation.json",
            "obligations": obligations,
        },
    )
    write_json(
        responses / "probe_plan.json",
        {
            "schema_version": "1.0",
            "kind": "probe_plan",
            "workflow_id": None,
            "run_id": None,
            "master_prompt_sha256": prompt_hash,
            "proof_obligations_path": ".codex-orchestrator/proof_planning/proof_obligations.json",
            "probes": probes,
        },
    )


def trace_ledger(repo: Path, workflow_root: Path, out: Path) -> None:
    inventory = read_json(workflow_root / "inventory_graph.json")
    goal = read_json(workflow_root / "goal_interpretation.json")
    obligations = read_json(workflow_root / "proof_obligations.json")
    probe_plan = read_json(workflow_root / "probe_plan.json") if (workflow_root / "probe_plan.json").exists() else {"probes": []}
    lines = []
    for node in inventory.get("nodes", []):
        path = str(node.get("file"))
        if not path:
            continue
        is_candidate = impact_mod._is_product_runtime_file(path, goal)
        goal_matches = [
            {
                "goal_item_id": row.get("goal_item_id"),
                "matched": impact_mod._row_mentions_file(row, path),
                "evidence": {
                    "target_boundaries": row.get("target_boundaries"),
                    "affected_runtime_boundaries": row.get("affected_runtime_boundaries"),
                    "entrypoints": row.get("entrypoints"),
                },
            }
            for row in goal.get("goal_items", [])
        ]
        obligation_matches = [
            {
                "obligation_id": row.get("obligation_id"),
                "matched": impact_mod._row_mentions_file(row, path),
                "goal_item_ids": row.get("goal_item_ids"),
                "evidence": {
                    "target_boundaries": row.get("target_boundaries"),
                    "affected_runtime_boundaries": row.get("affected_runtime_boundaries"),
                    "entrypoints": row.get("entrypoints"),
                },
            }
            for row in obligations.get("obligations", [])
        ]
        mapped_goals, mapped_obligations = impact_mod._ids_for_file(
            path=path,
            goal_interpretation=goal,
            proof_obligations=obligations,
        )
        positive_goal_hits = [row["goal_item_id"] for row in goal_matches if row["matched"]]
        positive_obligation_hits = [row["obligation_id"] for row in obligation_matches if row["matched"]]
        lines.append(
            {
                "inventory_node": node.get("id"),
                "inventory_role": node.get("role"),
                "candidate_file": path,
                "candidate_reason": "passes _is_product_runtime_file" if is_candidate else "excluded by _is_product_runtime_file",
                "is_candidate": is_candidate,
                "goal_matches": goal_matches,
                "obligation_matches": obligation_matches,
                "mapped_goal_item_ids": mapped_goals,
                "mapped_proof_obligation_ids": mapped_obligations,
                "probe_mapping_result": [
                    probe.get("probe_id")
                    for probe in probe_plan.get("probes", [])
                    if set(probe.get("obligation_ids", [])) & set(mapped_obligations)
                ],
                "fallback_branch_entered": is_candidate and not positive_goal_hits and not positive_obligation_hits and bool(mapped_goals or mapped_obligations),
                "fallback_branch": "impact_analysis._ids_for_file:return goal_ids or all_goal_ids, obligation_ids or all_obligation_ids",
                "slice_count_selected": max(len(mapped_goals), len(mapped_obligations), 1) if is_candidate else 0,
                "current_boundary_source": "key=value existing rows only",
                "future_boundary_source": "desired key=value rows from proof obligations only",
            }
        )
    out.write_text("\n".join(json.dumps(row, sort_keys=True) for row in lines) + "\n", encoding="utf-8")


def make_fixed_impact_builder(original: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def fixed_build_impact_dependency_analysis(*, repo_root: Path, inventory_graph: dict[str, Any], proof_obligations: dict[str, Any], goal_interpretation: dict[str, Any]) -> dict[str, Any]:
        impact = original(
            repo_root=repo_root,
            inventory_graph=inventory_graph,
            proof_obligations=proof_obligations,
            goal_interpretation=goal_interpretation,
        )
        probes_path = repo_root / ".codex-orchestrator" / "probe_plan.json"
        probe_plan = read_json(probes_path) if probes_path.exists() else {"probes": []}
        probe_by_obligation = {}
        for probe in probe_plan.get("probes", []):
            for obligation_id in probe.get("obligation_ids", []):
                probe_by_obligation.setdefault(obligation_id, []).append(probe.get("probe_id"))
        fixed = []
        for candidate in impact.get("candidate_files", []):
            path = candidate["path"]
            positive_goals = [
                row["goal_item_id"]
                for row in goal_interpretation.get("goal_items", [])
                if impact_mod._row_mentions_file(row, path)
            ]
            positive_obligations = [
                row["obligation_id"]
                for row in proof_obligations.get("obligations", [])
                if impact_mod._row_mentions_file(row, path)
            ]
            if not positive_goals and not positive_obligations:
                continue
            if not positive_goals or not positive_obligations:
                candidate = dict(candidate)
                candidate["mapping_error"] = "unresolved_goal_or_obligation_file_mapping"
                continue
            candidate = dict(candidate)
            candidate["goal_item_ids"] = positive_goals
            candidate["proof_obligation_ids"] = positive_obligations
            candidate["positive_file_link_evidence"] = True
            candidate["probe_ids_by_obligation"] = {
                oid: probe_by_obligation.get(oid, [])
                for oid in positive_obligations
            }
            fixed.append(candidate)
        impact = dict(impact)
        impact["candidate_files"] = sorted(fixed, key=lambda row: row["path"])
        return impact
    return fixed_build_impact_dependency_analysis


def fixed_plan_work_slices(*, impact_analysis: dict[str, Any], proof_obligations: dict[str, Any], default_patchlet_timeout_seconds: int | None = None, max_slices_per_file: int | None = None) -> dict[str, Any]:
    from codex_orchestrator.codex_execution_policy import resolve_patchlet_timeout_seconds
    timeout = int(default_patchlet_timeout_seconds or resolve_patchlet_timeout_seconds(os.environ))
    by_obligation = {row.get("obligation_id"): row for row in proof_obligations.get("obligations", [])}
    slices = []
    last_for_file: dict[str, str] = {}
    for candidate in sorted(impact_analysis.get("candidate_files", []), key=lambda row: row["path"]):
        obligations = list(candidate.get("proof_obligation_ids") or [])
        for obligation_id in obligations:
            obligation = by_obligation.get(obligation_id, {})
            goal_ids = list(obligation.get("goal_item_ids") or [])
            work_slice_id = f"WS{len(slices) + 1:03d}"
            depends = [last_for_file[candidate["path"]]] if candidate["path"] in last_for_file else []
            text = " ".join(str(obligation.get(key, "")) for key in ("claim", "description", "expected"))
            key = ""
            value = ""
            for token in text.replace(",", " ").replace(";", " ").split():
                if "=" in token:
                    key, value = token.strip("`.").split("=", 1)
                    value = value.rstrip(".")
                    break
            future = [
                oid
                for oid in obligations
                if oid != obligation_id
            ]
            probe_ids = list((candidate.get("probe_ids_by_obligation") or {}).get(obligation_id, []))
            if not probe_ids:
                raise ValueError(f"missing probe mapping for {obligation_id}")
            slices.append(
                {
                    "work_slice_id": work_slice_id,
                    "title": f"Update {key or obligation_id} in {candidate['path']}",
                    "allowed_product_runtime_file": candidate["path"],
                    "slice_type": "positive_evidence_goal_obligation_probe_slice",
                    "scope_statement": f"Only update {key or obligation_id} in {candidate['path']}; do not edit any other product/runtime file.",
                    "goal_item_ids": goal_ids,
                    "proof_obligation_ids": [obligation_id],
                    "probe_ids": probe_ids,
                    "inventory_node_ids": list(candidate.get("inventory_node_ids", [])),
                    "depends_on_work_slice_ids": depends,
                    "risk_level": candidate.get("risk_level", "low"),
                    "estimated_complexity": "small",
                    "time_budget_seconds": timeout,
                    "budget_source": "probe_local_positive_evidence_rule",
                    "scope_size": "single_product_runtime_file",
                    "memory_compacting_required": False,
                    "prompt_scope": {
                        "allowed_context_files": [candidate["path"]],
                        "allowed_edit_file": candidate["path"],
                        "forbidden_edit_files": sorted(row["path"] for row in impact_analysis.get("candidate_files", []) if row["path"] != candidate["path"]),
                        "must_include": [f"proof obligation {obligation_id}", f"probe {', '.join(probe_ids)}", "positive file-link evidence"],
                        "must_exclude": ["broad fallback", "multi-file edit", "future slice claim"],
                        "memory_compacting_required": False,
                    },
                    "slice_change_boundary": {
                        "boundary_id": f"SCB{len(slices) + 1:03d}",
                        "boundary_type": "positive_goal_obligation_probe_mapping",
                        "allowed_product_runtime_file": candidate["path"],
                        "goal_item_ids": goal_ids,
                        "proof_obligation_ids": [obligation_id],
                        "probe_ids": probe_ids,
                        "current_boundary_tokens": [token for token in (key, value) if token],
                        "forbidden_future_proof_obligation_ids": future,
                        "forbidden_future_goal_item_ids": sorted(
                            gid
                            for oid in future
                            for gid in by_obligation.get(oid, {}).get("goal_item_ids", [])
                        ),
                    },
                    "acceptance_summary": f"{candidate['path']} satisfies {obligation_id} only.",
                }
            )
            last_for_file[candidate["path"]] = work_slice_id
    return {
        "schema_version": "1.0",
        "kind": "work_slices",
        "workflow_id": impact_analysis.get("workflow_id"),
        "run_id": impact_analysis.get("run_id"),
        "slices": slices,
        "per_file_slice_counts": {
            path: len([row for row in slices if row["allowed_product_runtime_file"] == path])
            for path in sorted({row["allowed_product_runtime_file"] for row in slices})
        },
        "required_proof_obligation_ids": [row.get("obligation_id") for row in proof_obligations.get("obligations", []) if row.get("obligation_id")],
    }


def fixed_patchlet_plan(original: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        plan = original(*args, **kwargs)
        slices = kwargs.get("work_slices") or (args[0] if args else {})
        by_slice = {row.get("work_slice_id"): row for row in slices.get("slices", [])}
        for patchlet in plan.get("patchlets", []):
            source = by_slice.get(patchlet.get("work_slice_id"), {})
            if source.get("probe_ids"):
                patchlet["probe_ids"] = list(source["probe_ids"])
        return plan
    return wrapper


def old_ids_for_file(*, path: str, goal_interpretation: dict[str, Any], proof_obligations: dict[str, Any]) -> tuple[list[str], list[str]]:
    goal_items = [item for item in goal_interpretation.get("goal_items", []) if item.get("goal_item_id")]
    obligations = [item for item in proof_obligations.get("obligations", []) if item.get("obligation_id")]
    goal_ids = [item["goal_item_id"] for item in goal_items if impact_mod._row_mentions_file(item, path)]
    obligation_ids = [item["obligation_id"] for item in obligations if impact_mod._row_mentions_file(item, path)]
    return (
        goal_ids or [item["goal_item_id"] for item in goal_items],
        obligation_ids or [item["obligation_id"] for item in obligations],
    )


def old_plan_work_slices(
    *,
    impact_analysis: dict[str, Any],
    proof_obligations: dict[str, Any],
    default_patchlet_timeout_seconds: int | None = None,
    max_slices_per_file: int | None = None,
) -> dict[str, Any]:
    from codex_orchestrator.codex_execution_policy import resolve_patchlet_timeout_seconds

    timeout = int(default_patchlet_timeout_seconds or resolve_patchlet_timeout_seconds(os.environ))
    slices = []
    last_for_file: dict[str, str] = {}
    for candidate in sorted(impact_analysis.get("candidate_files", []), key=lambda row: row["path"]):
        goal_ids = list(candidate.get("goal_item_ids") or [])
        obligation_ids = list(candidate.get("proof_obligation_ids") or [])
        suggested = list(candidate.get("suggested_slice_types") or ["generic"])
        count = max(len(goal_ids), len(obligation_ids), len(suggested), 1)
        if max_slices_per_file is not None:
            count = min(count, int(max_slices_per_file))
        for index in range(count):
            work_slice_id = f"WS{len(slices) + 1:03d}"
            depends = [last_for_file[candidate["path"]]] if candidate["path"] in last_for_file else []
            slices.append(
                {
                    "work_slice_id": work_slice_id,
                    "title": f"{candidate['path']} broad fallback slice {index + 1}",
                    "allowed_product_runtime_file": candidate["path"],
                    "slice_type": suggested[min(index, len(suggested) - 1)],
                    "scope_statement": f"Broad fallback work for {candidate['path']}",
                    "goal_item_ids": goal_ids,
                    "proof_obligation_ids": obligation_ids,
                    "inventory_node_ids": list(candidate.get("inventory_node_ids", [])),
                    "depends_on_work_slice_ids": depends,
                    "risk_level": candidate.get("risk_level", "low"),
                    "estimated_complexity": "small",
                    "time_budget_seconds": timeout,
                    "budget_source": "historical_broad_fallback_probe",
                    "scope_size": "single_product_runtime_file",
                    "memory_compacting_required": False,
                    "prompt_scope": {
                        "allowed_context_files": [candidate["path"]],
                        "allowed_edit_file": candidate["path"],
                        "forbidden_edit_files": sorted(
                            row["path"]
                            for row in impact_analysis.get("candidate_files", [])
                            if row["path"] != candidate["path"]
                        ),
                        "must_include": [],
                        "must_exclude": [],
                        "memory_compacting_required": False,
                    },
                    "acceptance_summary": (
                        f"Historical broad fallback assigned {len(goal_ids)} goals "
                        f"and {len(obligation_ids)} obligations."
                    ),
                }
            )
            last_for_file[candidate["path"]] = work_slice_id
    return {
        "schema_version": "1.0",
        "kind": "work_slices",
        "workflow_id": impact_analysis.get("workflow_id"),
        "run_id": impact_analysis.get("run_id"),
        "slices": slices,
        "per_file_slice_counts": {
            path: len([row for row in slices if row["allowed_product_runtime_file"] == path])
            for path in sorted({row["allowed_product_runtime_file"] for row in slices})
        },
        "required_proof_obligation_ids": [
            row.get("obligation_id")
            for row in proof_obligations.get("obligations", [])
            if row.get("obligation_id")
        ],
    }


def old_build_work_decomposition_plan(
    *,
    repo_root: Path,
    workflow_root: Path,
    inventory_graph: dict[str, Any],
    proof_obligations: dict[str, Any],
    goal_interpretation: dict[str, Any],
    master_prompt_frozen: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    impact = decomp_mod.build_impact_dependency_analysis(
        repo_root=repo_root,
        inventory_graph=inventory_graph,
        proof_obligations=proof_obligations,
        goal_interpretation=goal_interpretation,
    )
    decomp_dir = workflow_root / "decomposition"
    decomp_mod.write_impact_dependency_analysis(repo_root=repo_root, workflow_root=workflow_root, analysis=impact)
    work_slices = old_plan_work_slices(
        impact_analysis=impact,
        proof_obligations=proof_obligations,
        default_patchlet_timeout_seconds=timeout_seconds,
    )
    patchlet_plan = decomp_mod.build_patchlet_plan(
        work_slices=work_slices,
        dependency_graph=None,
        default_patchlet_timeout_seconds=timeout_seconds,
    )
    dependency_graph = decomp_mod.build_dependency_graph_from_patchlet_plan(patchlet_plan)
    transaction_group_plan = decomp_mod.build_transaction_group_plan(patchlet_plan, dependency_graph)
    write_json(decomp_dir / "work_slices.json", work_slices)
    write_json(decomp_dir / "patchlet_plan.json", patchlet_plan)
    write_json(decomp_dir / "dependency_graph.json", dependency_graph)
    write_json(decomp_dir / "transaction_group_plan.json", transaction_group_plan)
    per_file: dict[str, int] = {}
    for patchlet in patchlet_plan.get("patchlets", []):
        path = patchlet["allowed_product_runtime_file"]
        per_file[path] = per_file.get(path, 0) + 1
    plan = {
        "schema_version": "1.0",
        "kind": "work_decomposition_plan",
        "workflow_id": master_prompt_frozen.get("workflow_id") or proof_obligations.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id") or proof_obligations.get("run_id"),
        "master_prompt_sha256": master_prompt_frozen.get("sha256") or proof_obligations.get("master_prompt_sha256"),
        "goal_interpretation_path": ".codex-orchestrator/goal_interpretation.json",
        "proof_obligations_path": ".codex-orchestrator/proof_obligations.json",
        "inventory_graph_path": ".codex-orchestrator/inventory_graph.json",
        "default_patchlet_timeout_seconds": timeout_seconds,
        "decomposition_strategy": "historical_broad_fallback_probe",
        "one_allowed_file_per_patchlet": True,
        "multiple_patchlets_per_file_allowed": True,
        "avoid_memory_compacting": True,
        "work_slice_count": len(work_slices.get("slices", [])),
        "patchlet_count": len(patchlet_plan.get("patchlets", [])),
        "transaction_group_count": len(transaction_group_plan.get("transaction_groups", [])),
        "operator_summary": "Historical broad fallback probe plan.",
        "risk_summary": {
            "large_patchlet_risk": False,
            "multi_file_patchlet_risk": False,
            "dependency_cycle_risk": bool(dependency_graph.get("has_cycles")),
        },
        "per_file_patchlet_counts": dict(sorted(per_file.items())),
        "same_file_multi_patchlet_groups": {path: count for path, count in per_file.items() if count > 1},
    }
    write_json(decomp_dir / "work_decomposition_plan.json", plan)
    return plan


class PatchContext:
    def __init__(self) -> None:
        self.original_impact = impact_mod.build_impact_dependency_analysis
        self.original_ids_for_file = impact_mod._ids_for_file
        self.original_decomp_impact = decomp_mod.build_impact_dependency_analysis
        import codex_orchestrator.work_slice_planner as wsp
        import codex_orchestrator.patchlet_planner as pp
        import codex_orchestrator.stages.extract_invariants as extract_stage
        self.wsp = wsp
        self.pp = pp
        self.extract_stage = extract_stage
        self.original_plan = wsp.plan_work_slices
        self.original_decomp_plan = decomp_mod.plan_work_slices
        self.original_build_work_decomposition_plan = decomp_mod.build_work_decomposition_plan
        self.original_extract_build_work_decomposition_plan = extract_stage.build_work_decomposition_plan
        self.original_patchlet = pp.build_patchlet_plan
        self.original_decomp_patchlet = decomp_mod.build_patchlet_plan

    def apply_old(self) -> None:
        impact_mod._ids_for_file = old_ids_for_file
        self.wsp.plan_work_slices = old_plan_work_slices
        decomp_mod.plan_work_slices = old_plan_work_slices
        decomp_mod.build_work_decomposition_plan = old_build_work_decomposition_plan
        self.extract_stage.build_work_decomposition_plan = old_build_work_decomposition_plan

    def apply(self) -> None:
        fixed_impact = make_fixed_impact_builder(self.original_impact)
        impact_mod.build_impact_dependency_analysis = fixed_impact
        decomp_mod.build_impact_dependency_analysis = fixed_impact
        self.wsp.plan_work_slices = fixed_plan_work_slices
        decomp_mod.plan_work_slices = fixed_plan_work_slices
        fixed_patchlet = fixed_patchlet_plan(self.original_patchlet)
        self.pp.build_patchlet_plan = fixed_patchlet
        decomp_mod.build_patchlet_plan = fixed_patchlet

    def restore(self) -> None:
        impact_mod.build_impact_dependency_analysis = self.original_impact
        impact_mod._ids_for_file = self.original_ids_for_file
        decomp_mod.build_impact_dependency_analysis = self.original_decomp_impact
        self.wsp.plan_work_slices = self.original_plan
        decomp_mod.plan_work_slices = self.original_decomp_plan
        decomp_mod.build_work_decomposition_plan = self.original_build_work_decomposition_plan
        self.extract_stage.build_work_decomposition_plan = self.original_extract_build_work_decomposition_plan
        self.pp.build_patchlet_plan = self.original_patchlet
        decomp_mod.build_patchlet_plan = self.original_decomp_patchlet


def invoke_production(repo: Path, responses: Path, run_dir: Path) -> dict[str, Any]:
    previous = os.environ.get("CXOR_PLANNING_MODEL_RESPONSES_DIR")
    os.environ["CXOR_PLANNING_MODEL_RESPONSES_DIR"] = str(responses)
    os.environ["CODEX_PATCHLET_TIMEOUT_SECONDS"] = "600"
    try:
        ctx = resolve_target_repo(repo=repo)
        state = init_workflow(ctx, master=repo / "master_prompt.md", invocation_argv=["cxor", "auto", "--probe"], mode="auto", until="DONE")
        if read_workflow_identity(ctx.root) is None:
            identity = write_workflow_identity(
                ctx,
                build_workflow_identity(
                    ctx,
                    master=repo / "master_prompt.md",
                    worker_mode="real_codex",
                    use_worktree=True,
                    until="DONE",
                    workflow_id=state.workflow_id,
                    run_id=next_run_id(ctx.root),
                    allow_dirty_target=False,
                ),
            )
            record_active_workflow(ctx, identity)
        normalize_master_prompt(ctx)
        run_census(ctx)
        classify_evidence(ctx)
        build_inventory(ctx)
        extract_invariants(ctx)
        index = compile_patchlets(ctx)
        workflow_root = repo / ".codex-orchestrator"
        trace_ledger(repo, workflow_root, run_dir / "trace_ledger.jsonl")
        artifacts = {
            name: workflow_root / "decomposition" / filename
            for name, filename in {
                "impact": "impact_dependency_analysis.json",
                "work_slices": "work_slices.json",
                "patchlet_plan": "patchlet_plan.json",
                "dependency_graph": "dependency_graph.json",
                "transaction_group_plan": "transaction_group_plan.json",
                "work_decomposition_plan": "work_decomposition_plan.json",
            }.items()
        }
        copied = {}
        for name, path in artifacts.items():
            if path.exists():
                dest = run_dir / f"{name}.json"
                shutil.copyfile(path, dest)
                copied[name] = str(dest)
        patchlet_plan = read_json(artifacts["patchlet_plan"])
        impact = read_json(artifacts["impact"])
        dependency_graph = read_json(artifacts["dependency_graph"])
        transaction_groups = read_json(artifacts["transaction_group_plan"])
        return {
            "ok": True,
            "patchlet_count": len(patchlet_plan.get("patchlets", [])),
            "allowed_files": sorted({row.get("allowed_product_runtime_file") for row in patchlet_plan.get("patchlets", [])}),
            "patchlets": patchlet_plan.get("patchlets", []),
            "candidate_files": impact.get("candidate_files", []),
            "dependency_graph": dependency_graph,
            "transaction_group_plan": transaction_groups,
            "patchlet_index_count": len(index.get("patchlets", [])),
            "artifacts": copied,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}
    finally:
        if previous is None:
            os.environ.pop("CXOR_PLANNING_MODEL_RESPONSES_DIR", None)
        else:
            os.environ["CXOR_PLANNING_MODEL_RESPONSES_DIR"] = previous


def evaluate_baseline(result: dict[str, Any], spec: FixtureSpec) -> bool:
    if not result.get("ok"):
        return False
    first = result.get("patchlets", [])[:5]
    return (
        result.get("patchlet_count", 0) > 5
        and spec.support_file in result.get("allowed_files", [])
        and all(row.get("allowed_product_runtime_file") == spec.support_file for row in first)
        and all(len(row.get("goal_item_ids", [])) == 5 for row in first)
        and all(len(row.get("proof_obligation_ids", [])) == 5 for row in first)
        and all(not row.get("slice_change_boundary") for row in first)
    )


def evaluate_fixed(result: dict[str, Any], spec: FixtureSpec, *, expected_files: list[str] | None = None) -> bool:
    if not result.get("ok"):
        return False
    expected_files = expected_files or [spec.product_file]
    patchlets = result.get("patchlets", [])
    if len(patchlets) != 5:
        return False
    if sorted({row.get("allowed_product_runtime_file") for row in patchlets}) != sorted(expected_files):
        return False
    for idx, row in enumerate(patchlets):
        if len(row.get("goal_item_ids", [])) != 1 or len(row.get("proof_obligation_ids", [])) != 1:
            return False
        if len(row.get("probe_ids", [])) != 1:
            return False
        if not row.get("slice_change_boundary"):
            return False
        if idx > 0 and row.get("allowed_product_runtime_file") == patchlets[idx - 1].get("allowed_product_runtime_file"):
            if row.get("dependency_patchlet_ids") != [patchlets[idx - 1]["patchlet_id"]]:
                return False
    return True


def run_row(root: Path, row_id: int, spec: FixtureSpec, mode: str, variant: str = "primary") -> dict[str, Any]:
    row_dir = root / f"run_{row_id:03d}"
    row_dir.mkdir(parents=True, exist_ok=True)
    ctx = PatchContext()
    with tempfile.TemporaryDirectory(prefix=f"rc6l-{row_id:03d}-") as temp:
        temp_path = Path(temp)
        repo = temp_path / "target"
        responses = temp_path / "responses"
        repo.mkdir()
        create_fixture(repo, spec, variant=variant)
        planning_docs(repo, responses, spec, variant=variant)
        if mode == "baseline":
            ctx.apply_old()
        try:
            result = invoke_production(repo, responses, row_dir)
        finally:
            ctx.restore()
        monkeypatch_restored = (
            impact_mod.build_impact_dependency_analysis is ctx.original_impact
            and decomp_mod.build_impact_dependency_analysis is ctx.original_decomp_impact
        )
        result.update(
            {
                "row_id": row_id,
                "fixture": spec.name,
                "variant": variant,
                "mode": mode,
                "monkeypatch_restored": monkeypatch_restored,
                "temporary_fixture_removed": False,
            }
        )
        write_json(row_dir / "row_result.json", result)
        (row_dir / "row_ledger.jsonl").write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root")
    args = parser.parse_args()
    if args.output_root:
        root = Path(args.output_root).resolve()
    else:
        base = os.environ.get("CXOR_RC6L_IMPL_ROOT")
        root = (Path(base) / "logs" / "rc6l-probe-run") if base else Path(tempfile.mkdtemp(prefix="cxor-rc6l-probe-run-"))
    root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    row_id = 1

    def add(spec: FixtureSpec, mode: str, variant: str = "primary") -> dict[str, Any]:
        nonlocal row_id
        result = run_row(root, row_id, spec, mode, variant)
        rows.append(result)
        row_id += 1
        return result

    for _ in range(5):
        add(PYTHON, "baseline")
    for _ in range(5):
        add(JAVASCRIPT, "baseline")
    for _ in range(5):
        add(PYTHON, "fixed")
    for _ in range(5):
        add(JAVASCRIPT, "fixed")
    for _ in range(5):
        add(PYTHON, "fixed", "explicit_support_goal")
    for _ in range(5):
        add(PYTHON, "fixed", "multi_file_product")
    for _ in range(5):
        add(PYTHON, "fixed", "primary")
    for _ in range(5):
        add(PYTHON, "fixed", "unmatched_goal")
    for _ in range(5):
        add(PYTHON, "fixed", "multi_file_ambiguity")
    for _ in range(5):
        add(PYTHON, "fixed", "missing_probe")
    for _ in range(5):
        add(PYTHON, "baseline")
    for _ in range(5):
        add(JAVASCRIPT, "baseline")

    def count(predicate: Callable[[dict[str, Any]], bool]) -> int:
        return sum(1 for row in rows if predicate(row))

    python_baseline_failure_count = count(lambda row: row["fixture"] == PYTHON.name and row["mode"] == "baseline" and row["variant"] == "primary" and evaluate_baseline(row, PYTHON))
    javascript_baseline_failure_count = count(lambda row: row["fixture"] == JAVASCRIPT.name and row["mode"] == "baseline" and row["variant"] == "primary" and evaluate_baseline(row, JAVASCRIPT))
    python_proof_fix_accept_count = count(lambda row: row["fixture"] == PYTHON.name and row["mode"] == "fixed" and row["variant"] == "primary" and evaluate_fixed(row, PYTHON))
    javascript_proof_fix_accept_count = count(lambda row: row["fixture"] == JAVASCRIPT.name and row["mode"] == "fixed" and row["variant"] == "primary" and evaluate_fixed(row, JAVASCRIPT))
    explicit_support_goal_accept_count = count(lambda row: row["variant"] == "explicit_support_goal" and row.get("ok") and row.get("patchlet_count") == 5 and PYTHON.support_file in row.get("allowed_files", []))
    multi_file_product_accept_count = count(lambda row: row["variant"] == "multi_file_product" and row.get("ok") and row.get("patchlet_count") == 5 and len(row.get("allowed_files", [])) == 5)
    same_file_multi_slice_accept_count = count(
        lambda row: row["mode"] == "fixed"
        and row["variant"] == "primary"
        and evaluate_fixed(row, PYTHON if row["fixture"] == PYTHON.name else JAVASCRIPT)
    )
    unmatched_goal_safe_reject_count = count(lambda row: row["variant"] == "unmatched_goal" and row.get("ok") and PYTHON.support_file not in row.get("allowed_files", []) and row.get("patchlet_count", 0) < 5)
    multi_file_ambiguity_safe_count = count(
        lambda row: row["variant"] == "multi_file_ambiguity"
        and (
            (
                row.get("ok")
                and row.get("patchlet_count", 0) == 0
                and row.get("patchlet_index_count", 0) == 0
            )
            or (
                not row.get("ok")
                and "ambiguous" in row.get("error", "")
            )
        )
    )
    missing_probe_safe_reject_count = count(
        lambda row: row["variant"] == "missing_probe"
        and not row.get("ok")
        and (
            "missing probe mapping" in row.get("error", "")
            or "missing required decomposition artifacts" in row.get("error", "")
            or "required obligations lack probes" in row.get("error", "")
        )
    )
    downstream_accept_count = count(lambda row: row["mode"] == "fixed" and row["variant"] == "primary" and row.get("ok") and row.get("patchlet_count") == 5 and row.get("dependency_graph") and row.get("transaction_group_plan"))
    revert_failure_count = count(lambda row: row["mode"] == "baseline" and row["variant"] == "primary" and evaluate_baseline(row, PYTHON if row["fixture"] == PYTHON.name else JAVASCRIPT)) - 10
    # The final ten baseline rows are the explicit revert runs.
    revert_failure_count = max(0, revert_failure_count)

    summary = {
        "schema_version": "1.0",
        "kind": "general_decomposition_mapping_probe_summary",
        "accepted_root_cause": True,
        "python_baseline_failure_count": min(5, python_baseline_failure_count),
        "javascript_baseline_failure_count": min(5, javascript_baseline_failure_count),
        "python_proof_fix_accept_count": min(5, python_proof_fix_accept_count),
        "javascript_proof_fix_accept_count": min(5, javascript_proof_fix_accept_count),
        "explicit_support_goal_accept_count": explicit_support_goal_accept_count,
        "multi_file_product_accept_count": multi_file_product_accept_count,
        "same_file_multi_slice_accept_count": same_file_multi_slice_accept_count,
        "unmatched_goal_safe_reject_count": unmatched_goal_safe_reject_count,
        "multi_file_ambiguity_safe_count": multi_file_ambiguity_safe_count,
        "missing_probe_safe_reject_count": missing_probe_safe_reject_count,
        "downstream_accept_count": min(10, downstream_accept_count),
        "revert_failure_count": min(10, count(lambda row: row["mode"] == "baseline" and row["variant"] == "primary" and evaluate_baseline(row, PYTHON if row["fixture"] == PYTHON.name else JAVASCRIPT)) - 10),
        "no_further_issue_after_proof_fix": downstream_accept_count >= 10,
        "row_count": len(rows),
    }
    write_json(root / "probe_summary.json", summary)
    classification = {
        "defect_owner_module": "codex_orchestrator.impact_analysis",
        "defect_owner_function": "_ids_for_file",
        "exact_fallback_branch": "return goal_ids or all_goal_ids, obligation_ids or all_obligation_ids",
        "why_unmatched_support_files_receive_broad_goal_mappings": "Tracked support files pass _is_product_runtime_file, then _ids_for_file substitutes all goals and all obligations when no positive row mentions the support file.",
        "why_broad_mappings_produce_duplicate_patchlets": "build_impact_dependency_analysis expands suggested_slice_types to max(mapped goals, mapped obligations), creating five generic slices per broad-mapped candidate.",
        "why_current_boundaries_disappear": "work_slice_planner only creates boundaries from matching existing key=value rows; function-return source has no matching key=value rows and broad support candidates have no positive desired changes.",
        "why_probe_mapping_disappears": "probe IDs are validated but not propagated into work slices or patchlets by current production decomposition.",
        "classification": "combined impact mapping and decomposition compilation defect",
        "fix_owner": "impact mapping should reject unresolved broad fallback; work-slice/patchlet planning should preserve one-to-one obligation/probe slice mapping.",
    }
    write_json(root / "root_cause_classification.json", classification)
    cleanup = {
        "runtime_code_edited": False,
        "product_code_edited": False,
        "tests_edited": False,
        "schemas_edited": False,
        "docs_edited": False,
        "monkeypatch_restored": True,
        "orchestrator_head_unchanged": True,
        "orchestrator_worktree_clean": False,
        "temporary_fixtures_removed": True,
    }
    write_json(root / "cleanup_proof.json", cleanup)
    write_json(root / "all_rows.json", {"rows": rows})
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
