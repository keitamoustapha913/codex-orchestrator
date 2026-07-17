"""The single source of truth for the bounded worker-report boundary.

This module deliberately contains no acceptance logic.  It describes what may
cross the raw-report boundary and how fields are classified for reorganization.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, TypedDict


RAW_REPORT_MAX_BYTES = 2 * 1024 * 1024
RAW_REPORT_MAX_DEPTH = 32
RAW_REPORT_MAX_ARRAY_LENGTH = 10_000
RAW_REPORT_MAX_FIELDS = 2_000

SEMANTIC_GOAL_ITEM_ID_FIELD = "goal_item_id"
SEMANTIC_GOAL_RESULT_FIELD = "result"
SEMANTIC_GOAL_RESULT_SHORTHAND_FIELDS: dict[str, dict[str, Any]] = {
    SEMANTIC_GOAL_ITEM_ID_FIELD: {
        "json_type": "string",
        "required": True,
        "description": "Current patchlet goal item identity.",
    },
    SEMANTIC_GOAL_RESULT_FIELD: {
        "json_type": "string",
        "required": True,
        "description": "Descriptive current-slice worker observation.",
    },
}


class WorkerPatchletReportV2(TypedDict, total=False):
    """Typed canonical report shape; worker extensions are never included here."""
    schema_version: str
    kind: str
    patchlet_id: str
    status: str
    changed_product_runtime_file: str | None
    changed_artifact_files: list[str]
    probe_commands: list[str]
    deterministic_run_counts: dict[str, Any]
    root_cause_classification: dict[str, Any]
    before_after_state: list[Any]
    row_ledger: list[Any]
    trace_ledger: list[Any]
    cleanup_proof: str
    probe_artifact_refs: list[dict[str, Any]]
    semantic_goal_results: list[dict[str, Any]]
    blocking_boundary_reason: str
    failed_probe_evidence: str


PROBE_ARTIFACT_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["path", "kind", "sha256", "size_bytes"],
    "properties": {
        "path": {"type": "string"},
        "kind": {"type": "string"},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "size_bytes": {"type": "integer", "minimum": 0},
        "extension": {"type": "string"},
        "mime_type": {"type": "string"},
    },
    "additionalProperties": True,
}

PROBE_ARTIFACT_REF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["patchlet_id", "probe_root", "run_id"],
    "properties": {
        "patchlet_id": {"type": "string"},
        "probe_root": {"type": "string"},
        "run_id": {"type": "string"},
        "files": {"type": "array", "items": PROBE_ARTIFACT_FILE_SCHEMA},
    },
    "additionalProperties": True,
}

CANONICAL_SEMANTIC_GOAL_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["criterion_id", "kind", "expected_value", "actual_value", "passed"],
    "properties": {
        "criterion_id": {"type": "string"},
        "kind": {"type": "string"},
        "expected_value": {},
        "actual_value": {},
        "passed": {"type": "boolean"},
        "probe_artifact_ref": {"type": "object"},
    },
    "additionalProperties": True,
}

SEMANTIC_GOAL_RESULT_SHORTHAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [SEMANTIC_GOAL_ITEM_ID_FIELD, SEMANTIC_GOAL_RESULT_FIELD],
    "properties": {
        SEMANTIC_GOAL_ITEM_ID_FIELD: {"type": "string"},
        SEMANTIC_GOAL_RESULT_FIELD: {"type": "string", "minLength": 1},
    },
    "additionalProperties": True,
}

FIELD_METADATA: dict[str, dict[str, Any]] = {
    "schema_version": {"json_type": "string", "python_types": (str,), "required": True, "description": "WorkerPatchletReportV2 version.", "reference_class": "NONE"},
    "kind": {"json_type": "string", "python_types": (str,), "required": True, "description": "Canonical worker report kind.", "reference_class": "NONE"},
    "patchlet_id": {"json_type": "string", "python_types": (str,), "required": True, "description": "Orchestrator-assigned patchlet identity.", "reference_class": "IDENTITY"},
    "status": {"json_type": "string", "python_types": (str,), "required": True, "description": "Worker lifecycle status; not proof.", "reference_class": "NONE"},
    "changed_product_runtime_file": {"json_type": ["string", "null"], "python_types": (str, type(None)), "required": True, "description": "Reported product file; boundary gates remain authoritative.", "reference_class": "PRODUCT_PATH"},
    "changed_artifact_files": {"json_type": "array", "json_schema": {"type": "array", "items": {"type": "string"}}, "python_types": (list,), "required": True, "description": "Reported evidence artifacts.", "reference_class": "ARTIFACT_PATH"},
    "probe_commands": {"json_type": "array", "json_schema": {"type": "array", "items": {"type": "string"}}, "python_types": (list,), "required": True, "description": "Worker-described probes; independent proof remains authoritative.", "reference_class": "NONE"},
    "deterministic_run_counts": {"json_type": "object", "python_types": (dict,), "required": True, "description": "Declared run counts; not independent proof.", "reference_class": "NONE"},
    "root_cause_classification": {"json_type": "object", "python_types": (dict,), "required": True, "description": "Structured worker diagnosis.", "reference_class": "NONE"},
    "before_after_state": {"json_type": "array", "python_types": (list,), "required": True, "description": "Worker state observations.", "reference_class": "NONE"},
    "row_ledger": {"json_type": "array", "python_types": (list,), "required": True, "description": "Worker evidence ledger.", "reference_class": "NONE"},
    "trace_ledger": {"json_type": "array", "python_types": (list,), "required": True, "description": "Worker trace ledger.", "reference_class": "NONE"},
    "cleanup_proof": {"json_type": "string", "python_types": (str,), "required": True, "description": "Worker cleanup observation; hygiene gates remain authoritative.", "reference_class": "NONE"},
    "probe_artifact_refs": {"json_type": "array", "json_schema": {"type": "array", "items": PROBE_ARTIFACT_REF_SCHEMA}, "python_types": (list,), "required": False, "description": "References to evidence under approved probe roots.", "reference_class": "ARTIFACT_PATH"},
    "semantic_goal_results": {"json_type": "array", "json_schema": {"type": "array", "items": {"oneOf": [CANONICAL_SEMANTIC_GOAL_RESULT_SCHEMA, SEMANTIC_GOAL_RESULT_SHORTHAND_SCHEMA]}}, "python_types": (list,), "required": False, "description": "Worker semantic observations pending independent proof.", "reference_class": "NONE"},
    "blocking_boundary_reason": {"json_type": "string", "python_types": (str,), "required": False, "description": "Worker description of the current blocking boundary.", "reference_class": "NONE"},
    "failed_probe_evidence": {"json_type": "string", "python_types": (str,), "required": False, "description": "Worker description of failed probe evidence.", "reference_class": "NONE"},
}
DERIVED_CANONICAL_REPORT_FIELD_METADATA: dict[str, dict[str, Any]] = {
    "worker_semantic_claims": {
        "json_type": "array",
        "description": "Claims derived only by semantic-result normalization; non-authoritative.",
        "producer": "normalize_semantic_goal_results",
    },
    "worker_semantic_quality_warnings": {
        "json_type": "array",
        "description": "Semantic-quality warnings derived by the orchestrator.",
        "producer": "normalize_semantic_goal_results",
    },
    "semantic_goal_results_raw": {
        "json_type": "array",
        "description": "Raw semantic observations retained by the orchestrator for diagnosis.",
        "producer": "report_ingestion",
    },
}
KNOWN_FIELD_TYPES: dict[str, tuple[type, ...]] = {name: meta["python_types"] for name, meta in FIELD_METADATA.items()}
REQUIRED_V2_FIELDS = frozenset(name for name, meta in FIELD_METADATA.items() if meta["required"])
EXTENSION_POLICY = "Unknown top-level fields are preserved as non-authoritative warnings."


def contract_payload() -> dict[str, Any]:
    fields = {name: {key: ([item.__name__ for item in value] if key == "python_types" else value) for key, value in meta.items()} for name, meta in FIELD_METADATA.items()}
    shorthand_fields = {
        name: dict(metadata)
        for name, metadata in SEMANTIC_GOAL_RESULT_SHORTHAND_FIELDS.items()
    }
    return {
        "name": "WorkerPatchletReportV2",
        "worker_input_fields": fields,
        "derived_canonical_fields": {
            name: dict(metadata)
            for name, metadata in DERIVED_CANONICAL_REPORT_FIELD_METADATA.items()
        },
        "semantic_goal_result_shorthand": {
            "required": [
                name
                for name, metadata in shorthand_fields.items()
                if metadata["required"]
            ],
            "fields": shorthand_fields,
        },
        "extension_policy": EXTENSION_POLICY,
    }


def contract_fingerprint() -> str:
    return hashlib.sha256(json.dumps(contract_payload(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def required_field_list() -> list[str]:
    return [name for name, meta in FIELD_METADATA.items() if meta["required"]]


def known_field_type_table() -> dict[str, str | list[str]]:
    return {name: meta["json_type"] for name, meta in FIELD_METADATA.items()}


def generated_v2_schema() -> dict[str, Any]:
    properties = {
        name: {
            **meta.get("json_schema", {"type": meta["json_type"]}),
            "description": meta["description"],
        }
        for name, meta in FIELD_METADATA.items()
    }
    properties["schema_version"] = {"const": "2.0", "description": FIELD_METADATA["schema_version"]["description"]}
    properties["kind"] = {"const": "worker_patchlet_report", "description": FIELD_METADATA["kind"]["description"]}
    properties["status"]["enum"] = ["COMPLETE", "VERIFIED_NO_CHANGE_NEEDED", "BLOCKED_WITH_EVIDENCE", "FAILED_WITH_EVIDENCE"]
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "WorkerPatchletReportV2", "type": "object", "required": required_field_list(), "properties": properties, "additionalProperties": True}


def contract_drift_errors() -> list[str]:
    """Compare production-loaded contract artifacts with WorkerPatchletReportV2."""
    root = Path(__file__).resolve().parent
    errors: list[str] = []
    schema_path = root / "schemas" / "worker_patchlet_report_v2.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"WORKER_REPORT_CONTRACT_DRIFT: cannot load generated V2 schema: {exc}"]
    if schema != generated_v2_schema():
        errors.append("WORKER_REPORT_CONTRACT_DRIFT: generated V2 schema differs from WorkerPatchletReportV2")
    if schema.get("required") != required_field_list():
        errors.append("WORKER_REPORT_CONTRACT_DRIFT: runtime required fields differ from WorkerPatchletReportV2")
    artifact_checks = (
        (root / "prompt_templates" / "worker_patchlet_report_v2.md", render_primary_worker_report_template()),
        (root / "prompt_templates" / "report_reorganization_worker_instructions.md", render_reorganization_worker_instructions()),
        (root.parent.parent / "examples" / "worker_patchlet_report_v2.json", canonical_example_report()),
        (root.parent.parent / "docs" / "worker_patchlet_report_v2_example.json", canonical_example_report()),
    )
    for path, expected in artifact_checks:
        try:
            actual = path.read_text(encoding="utf-8") if path.suffix == ".md" else json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"WORKER_REPORT_CONTRACT_DRIFT: cannot load {path.name}: {exc}")
            continue
        if actual != expected:
            errors.append(f"WORKER_REPORT_CONTRACT_DRIFT: generated artifact differs: {path}")
    return errors


def canonical_example_report() -> dict[str, Any]:
    return {"schema_version": "2.0", "kind": "worker_patchlet_report", "patchlet_id": "P0005", "status": "VERIFIED_NO_CHANGE_NEEDED", "changed_product_runtime_file": None, "changed_artifact_files": [], "probe_commands": ["<independent probe command>"], "deterministic_run_counts": {}, "root_cause_classification": {}, "before_after_state": [], "row_ledger": [], "trace_ledger": [], "cleanup_proof": "<worker cleanup observation>", "probe_artifact_refs": [], "semantic_goal_results": []}


def semantic_goal_result_shorthand_example() -> dict[str, str]:
    return {
        SEMANTIC_GOAL_ITEM_ID_FIELD: "<current goal item id>",
        SEMANTIC_GOAL_RESULT_FIELD: "<descriptive current-slice result mentioning the allowed boundary>",
    }


def render_semantic_goal_result_shorthand_example() -> str:
    return json.dumps(semantic_goal_result_shorthand_example(), indent=2)


def render_primary_worker_report_template() -> str:
    fields = "\n".join(f"- `{name}` ({meta['json_type']}): {meta['description']}" for name, meta in FIELD_METADATA.items())
    shorthand_fields = ", ".join(f"`{name}`" for name in SEMANTIC_GOAL_RESULT_SHORTHAND_FIELDS)
    return f"# WorkerPatchletReportV2 report contract\n\nContract fingerprint: `{contract_fingerprint()}`\n\nEmit these fields only as evidence; the orchestrator owns acceptance:\n{fields}\n\nSemantic shorthand entries use exactly these fields: {shorthand_fields}.\n\nReport path fields are bounded logical references, never absolute filesystem paths.\nUse `.artifacts/probes/<patchlet-id>/...` for `changed_artifact_files`, `probe_root`, and file `path` values. Never copy `$CXOR_WORKER_EVIDENCE_DIR`, `/tmp/...`, `~`, `..`, or sandbox paths into the report.\n\nUnknown fields are preserved as non-authoritative warnings.\n"


def render_reorganization_worker_instructions() -> str:
    fields = ", ".join(FIELD_METADATA)
    return f"# Report Reorganization Worker\n\nContract: WorkerPatchletReportV2\nFingerprint: `{contract_fingerprint()}`\nKnown fields: {fields}\nCopy values, preserve types, record source paths, and never create proof, coverage, or promotion claims. Unknown fields remain UNRECOGNIZED_WORKER_REPORT_FIELD.\n"


class RawReportError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RawReportError("RAW_WORKER_REPORT_DUPLICATE_KEY", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _walk(value: Any, *, depth: int = 0, fields: list[int] | None = None, key: str = "") -> None:
    fields = fields if fields is not None else [0]
    if depth > RAW_REPORT_MAX_DEPTH:
        raise RawReportError("RAW_WORKER_REPORT_DEPTH_LIMIT_EXCEEDED", "raw report nesting depth exceeded")
    if isinstance(value, dict):
        fields[0] += len(value)
        if fields[0] > RAW_REPORT_MAX_FIELDS:
            raise RawReportError("RAW_WORKER_REPORT_FIELD_LIMIT_EXCEEDED", "raw report field limit exceeded")
        for name, child in value.items():
            _walk(child, depth=depth + 1, fields=fields, key=name)
    elif isinstance(value, list):
        if len(value) > RAW_REPORT_MAX_ARRAY_LENGTH:
            raise RawReportError("RAW_WORKER_REPORT_SIZE_LIMIT_EXCEEDED", "raw report array length exceeded")
        for child in value:
            _walk(child, depth=depth + 1, fields=fields, key=key)
    elif isinstance(value, str) and (
        key.endswith("path")
        or "ref" in key
        or key.endswith("file")
        or key.endswith("files")
        or key in {"probe_root", "path"}
    ):
        if value.startswith("/") or value.startswith("~") or ".." in value.split("/"):
            raise RawReportError("RAW_WORKER_REPORT_UNSAFE_REFERENCE", f"unsafe artifact reference at {key}: {value}")
        if any(part in value.split("/") for part in ("worker_sandbox", "scratch", "__pycache__")):
            raise RawReportError("RAW_WORKER_REPORT_EXCLUDED_DEBRIS_REFERENCE", f"excluded debris reference at {key}: {value}")
        if ".codex-orchestrator" in value and ("integration" in value or "state" in value):
            raise RawReportError("RAW_WORKER_REPORT_UNSAFE_REFERENCE", f"protected workflow reference at {key}: {value}")


@dataclass(frozen=True)
class RawReportEnvelope:
    raw_bytes: bytes
    value: dict[str, Any]
    sha256: str
    byte_size: int
    top_level_field_count: int
    max_depth: int


def parse_raw_report(path) -> RawReportEnvelope:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) > RAW_REPORT_MAX_BYTES:
        raise RawReportError("RAW_WORKER_REPORT_SIZE_LIMIT_EXCEEDED", "raw report byte size exceeded")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RawReportError("RAW_WORKER_REPORT_INVALID_UTF8", "raw report is not valid UTF-8") from exc
    try:
        value = json.loads(text, object_pairs_hook=_pairs)
    except RawReportError:
        raise
    except json.JSONDecodeError as exc:
        raise RawReportError("RAW_WORKER_REPORT_INVALID_JSON", f"invalid raw report JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise RawReportError("RAW_WORKER_REPORT_NOT_OBJECT", "raw report top level must be an object")
    _walk(value)
    return RawReportEnvelope(raw, value, digest, len(raw), len(value), _depth(value))


def _depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max((_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(v) for v in value), default=0)
    return 0


def classify_fields(report: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    known, unknown = {}, []
    for name, value in report.items():
        expected = KNOWN_FIELD_TYPES.get(name)
        if expected is not None and isinstance(value, expected):
            known[name] = value
        else:
            unknown.append({
                "field_name": name,
                "source_path": f"$.{name}",
                "value_type": type(value).__name__,
                "value_sha256": hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(),
                "classification": "UNRECOGNIZED_WORKER_REPORT_FIELD",
            })
    return known, unknown
