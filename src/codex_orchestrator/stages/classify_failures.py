from __future__ import annotations

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import TargetRepoContext


def classify_failures(ctx: TargetRepoContext) -> dict:
    failures = []
    for path in sorted(ctx.paths.failures_dir.glob("F*.json")):
        record = read_json(path)
        record["classification"] = record.get("suspected_scope", "inside_known_graph").upper()
        write_json(path, record)
        failures.append(record)
    result = {
        "schema_version": "1.0",
        "kind": "failure_classification",
        "failures": failures,
    }
    write_json(ctx.paths.failures_dir / "classification.json", result)
    state = load_state(ctx)
    transition(ctx, state, "REPAIR_PLANNING_REQUIRED", reason="failures classified")
    return result
