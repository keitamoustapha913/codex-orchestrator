from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkflowPaths:
    repo_root: Path
    workflow_dir: Path
    probe_dir: Path
    master_prompt: Path
    goal_spec: Path
    config: Path
    state: Path
    run_manifest: Path
    census_dir: Path
    census_repo_files: Path
    census_git_status: Path
    census_rg_files: Path
    census_commands: Path
    census_tool_availability: Path
    search_evidence_jsonl: Path
    search_evidence_md: Path
    inventory_graph: Path
    inventory_table: Path
    invariants: Path
    path_mapping: Path
    patchlets_dir: Path
    patchlet_index: Path
    transaction_groups: Path
    subprompts_dir: Path
    reports_dir: Path
    runs_dir: Path
    failures_dir: Path
    repair_plans_dir: Path
    verifier_dir: Path
    final_verification_md: Path
    final_verification_json: Path
    lock: Path


def build_paths(repo_root: Path) -> WorkflowPaths:
    repo_root = repo_root.resolve()
    workflow = repo_root / ".codex-orchestrator"
    census = workflow / "census"
    patchlets = workflow / "patchlets"
    return WorkflowPaths(
        repo_root=repo_root,
        workflow_dir=workflow,
        probe_dir=repo_root / ".artifacts" / "probes",
        master_prompt=workflow / "master_prompt.md",
        goal_spec=workflow / "goal_spec.json",
        config=workflow / "config.toml",
        state=workflow / "state.json",
        run_manifest=workflow / "run_manifest.json",
        census_dir=census,
        census_repo_files=census / "repo_files.txt",
        census_git_status=census / "git_status.txt",
        census_rg_files=census / "rg_index.jsonl",
        census_commands=census / "commands.jsonl",
        census_tool_availability=census / "tool_availability.json",
        search_evidence_jsonl=workflow / "search_evidence.jsonl",
        search_evidence_md=workflow / "search_evidence.md",
        inventory_graph=workflow / "inventory_graph.json",
        inventory_table=workflow / "inventory_table.md",
        invariants=workflow / "invariants.json",
        path_mapping=workflow / "path_mapping.json",
        patchlets_dir=patchlets,
        patchlet_index=patchlets / "patchlet_index.json",
        transaction_groups=patchlets / "transaction_groups.json",
        subprompts_dir=workflow / "subprompts",
        reports_dir=workflow / "reports",
        runs_dir=workflow / "runs",
        failures_dir=workflow / "failures",
        repair_plans_dir=workflow / "repair_plans",
        verifier_dir=workflow / "verifier",
        final_verification_md=workflow / "final_verification.md",
        final_verification_json=workflow / "final_verification.json",
        lock=workflow / ".lock",
    )


def relative_to_repo(repo_root: Path, path: Path | str) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()
