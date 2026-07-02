from __future__ import annotations

from codex_orchestrator.jsonio import read_json
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.report_validator import validate_patchlet_report_file


def validate_report(ctx: TargetRepoContext, patchlet_id: str) -> dict:
    index = read_json(ctx.paths.patchlet_index)
    patchlet = next((p for p in index.get("patchlets", []) if p.get("patchlet_id") == patchlet_id), None)
    if patchlet is None:
        raise KeyError(f"Unknown patchlet: {patchlet_id}")
    return validate_patchlet_report_file(ctx.paths.reports_dir / f"{patchlet_id}.json", patchlet)
