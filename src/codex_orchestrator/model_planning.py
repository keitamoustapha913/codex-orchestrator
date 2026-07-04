from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_orchestrator.atomic_io import atomic_write_text
from codex_orchestrator.jsonio import read_json, write_json


class PlanningModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlanningModelResponse:
    raw_text: str


class PlanningModelClient:
    def complete(self, *, kind: str, request: dict[str, Any]) -> PlanningModelResponse:
        raise NotImplementedError


class FilePlanningModelClient(PlanningModelClient):
    def __init__(self, response_dir: Path | None):
        self.response_dir = response_dir

    def complete(self, *, kind: str, request: dict[str, Any]) -> PlanningModelResponse:
        if self.response_dir is None:
            if os.environ.get("CXOR_PLANNING_MODEL_STUB") == "1":
                return PlanningModelResponse(json.dumps(_stub_response(kind, request), indent=2, sort_keys=True))
            raise PlanningModelError(f"missing planning model response for {kind}")
        candidates = [
            self.response_dir / f"{kind}.json",
            self.response_dir / f"{kind}_response.json",
            self.response_dir / f"{kind}.raw.json",
        ]
        for path in candidates:
            if path.exists():
                return PlanningModelResponse(path.read_text(encoding="utf-8"))
        if os.environ.get("CXOR_PLANNING_MODEL_STUB") == "1":
            return PlanningModelResponse(json.dumps(_stub_response(kind, request), indent=2, sort_keys=True))
        raise PlanningModelError(f"missing planning model response for {kind}")


def create_planning_model_client(config: dict[str, Any] | None = None) -> PlanningModelClient:
    response_dir = (config or {}).get("response_dir") or os.environ.get("CXOR_PLANNING_MODEL_RESPONSES_DIR")
    return FilePlanningModelClient(Path(response_dir) if response_dir else None)


def build_goal_interpretation_request(
    *,
    workflow_root: Path,
    master_prompt_frozen: dict[str, Any],
    inventory_graph_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "goal_interpretation_model_request",
        "workflow_id": master_prompt_frozen.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id"),
        "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
        "master_prompt_sha256": master_prompt_frozen.get("sha256"),
        "source_spans": master_prompt_frozen.get("source_spans", []),
        "repo_census_summary_path": ".codex-orchestrator/census/repo_files.jsonl",
        "inventory_graph_path": ".codex-orchestrator/inventory_graph.json"
        if inventory_graph_path and inventory_graph_path.exists()
        else None,
        "output_schema_path": "goal_interpretation.schema.json",
        "instructions": _common_instructions()
        | {
            "proof_not_claimed_here": True,
            "return_goal_items_with_source_spans": True,
        },
    }


def build_proof_planning_request(
    *,
    master_prompt_frozen: dict[str, Any],
    goal_interpretation_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "proof_planning_model_request",
        "workflow_id": master_prompt_frozen.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id"),
        "master_prompt_sha256": master_prompt_frozen.get("sha256"),
        "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
        "goal_interpretation_path": goal_interpretation_path,
        "output_schema_path": "proof_obligations.schema.json",
        "instructions": _common_instructions()
        | {
            "proof_plan_is_not_source_of_truth": True,
            "map_every_required_goal_item_to_obligations": True,
            "require_independent_verifiability": True,
        },
    }


def build_probe_planning_request(
    *,
    master_prompt_frozen: dict[str, Any],
    proof_obligations_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "probe_planning_model_request",
        "workflow_id": master_prompt_frozen.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id"),
        "master_prompt_sha256": master_prompt_frozen.get("sha256"),
        "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
        "proof_obligations_path": proof_obligations_path,
        "output_schema_path": "probe_plan.schema.json",
        "instructions": _common_instructions()
        | {
            "derive_probe_plan_from_obligations": True,
            "require_rerunnable_or_independently_validatable_probes": True,
            "require_no_product_mutation": True,
        },
    }


def run_planning_model(
    *,
    workflow_root: Path,
    stage_dir_name: str,
    response_kind: str,
    request: dict[str, Any],
    model_client: PlanningModelClient,
) -> dict[str, Any]:
    stage_dir = workflow_root / stage_dir_name
    stage_dir.mkdir(parents=True, exist_ok=True)
    write_json(stage_dir / "model_request.json", request)
    try:
        response = model_client.complete(kind=response_kind, request=request)
    except PlanningModelError as exc:
        write_json(
            stage_dir / "validation_result.json",
            {
                "schema_version": "1.0",
                "kind": f"{stage_dir_name}_validation_result",
                "accepted": False,
                "errors": [str(exc)],
                "failure_signature": "planning_model_response_missing",
            },
        )
        raise
    atomic_write_text(stage_dir / "model_response.raw.json", response.raw_text)
    try:
        parsed = json.loads(response.raw_text)
    except json.JSONDecodeError as exc:
        write_json(
            stage_dir / "validation_result.json",
            {
                "schema_version": "1.0",
                "kind": f"{stage_dir_name}_validation_result",
                "accepted": False,
                "errors": [f"malformed model response: {exc}"],
                "failure_signature": "planning_model_response_malformed",
            },
        )
        raise PlanningModelError(f"malformed model response for {response_kind}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PlanningModelError(f"planning model response for {response_kind} must be a JSON object")
    return parsed


def write_validation_result(workflow_root: Path, stage_dir_name: str, *, accepted: bool, errors: list[str]) -> None:
    write_json(
        workflow_root / stage_dir_name / "validation_result.json",
        {
            "schema_version": "1.0",
            "kind": f"{stage_dir_name}_validation_result",
            "accepted": accepted,
            "errors": errors,
            "failure_signature": None if accepted else f"{stage_dir_name}_invalid",
        },
    )


def copy_json_artifact(source: Path, destination: Path) -> None:
    write_json(destination, read_json(source))


def _common_instructions() -> dict[str, Any]:
    return {
        "master_prompt_is_source_of_truth": True,
        "repo_agnostic": True,
        "language_agnostic": True,
        "do_not_assume_app_py": True,
        "do_not_assume_app_main": True,
        "do_not_assume_python": True,
        "derive_repo_context_from_supplied_evidence_only": True,
    }


def _stub_response(kind: str, request: dict[str, Any]) -> dict[str, Any]:
    sha = request.get("master_prompt_sha256")
    workflow_id = request.get("workflow_id")
    run_id = request.get("run_id")
    spans = request.get("source_spans") or [{"span_id": "MPS001", "text": "frozen master prompt"}]
    span_id = spans[0].get("span_id", "MPS001")
    text = str(spans[0].get("text", "frozen master prompt")).strip() or "frozen master prompt"
    if kind == "goal_interpretation":
        subjective = any(word in text.lower() for word in ["delightful", "perfect", "everyone agrees", "feel perfect"])
        return {
            "schema_version": "1.0",
            "kind": "goal_interpretation",
            "workflow_id": workflow_id,
            "run_id": run_id,
            "master_prompt_sha256": sha,
            "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
            "interpretation_status": "AMBIGUOUS" if subjective else "CONCORDANT",
            "goal_summary": text,
            "goal_items": [
                {
                    "goal_item_id": "GI001",
                    "source_span_ids": [span_id],
                    "goal_type": "behavioral_change",
                    "repo_context": {
                        "language_or_framework": "derived_from_repo_or_unknown",
                        "entrypoints": ["derived_from_repo_or_unknown"],
                        "affected_runtime_boundaries": ["derived_from_repo_or_unknown"],
                    },
                    "subject": "target repository behavior",
                    "desired_state": text,
                    "success_conditions": ["accepted integration state satisfies the frozen master prompt"],
                    "must_change_product": "unknown",
                    "acceptance_meaning": "orchestrator-owned probe or validation observes the requested state",
                    "required": True,
                }
            ],
            "non_goals": [],
            "ambiguities": ["Subjective goal lacks objective success conditions."] if subjective else [],
            "assumptions": [],
            "contradictions": [],
            "requires_external_resources": False,
            "proof_not_claimed_here": True,
        }
    if kind == "proof_obligations":
        return {
            "schema_version": "1.0",
            "kind": "proof_obligations",
            "workflow_id": workflow_id,
            "run_id": run_id,
            "master_prompt_sha256": sha,
            "goal_interpretation_path": ".codex-orchestrator/goal_interpretation/goal_interpretation.json",
            "obligations": [
                {
                    "obligation_id": "PO001",
                    "goal_item_ids": ["GI001"],
                    "source_span_ids": [span_id],
                    "obligation_type": "behavioral_runtime_claim",
                    "claim": "The accepted integration state satisfies the requested behavior from the frozen master prompt.",
                    "proof_strategy": "executable_probe",
                    "proof_kind": "executable_probe",
                    "required": True,
                    "language": "derived_or_unknown",
                    "target_boundaries": ["derived_from_repo_or_unknown"],
                    "status": "UNPROVEN",
                    "evidence_requirements": [
                        "expected_actual_record",
                        "orchestrator_rerun_or_validation",
                        "coverage_link_to_master_prompt",
                    ],
                }
            ],
        }
    if kind == "probe_plan":
        return {
            "schema_version": "1.0",
            "kind": "probe_plan",
            "workflow_id": workflow_id,
            "run_id": run_id,
            "master_prompt_sha256": sha,
            "proof_obligations_path": ".codex-orchestrator/proof_planning/proof_obligations.json",
            "probes": [
                {
                    "probe_id": "GP001",
                    "obligation_ids": ["PO001"],
                    "probe_kind": "executable",
                    "owner": "model_planned_orchestrator_validated",
                    "execution_context": "integration_candidate",
                    "command": "true",
                    "expected_observation": {"type": "exit_code_zero"},
                    "rerunnable_by_orchestrator": True,
                    "side_effect_policy": "no_product_mutation",
                    "status": "PLANNED",
                }
            ],
        }
    return {}
