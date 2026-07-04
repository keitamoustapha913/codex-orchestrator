from __future__ import annotations

from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _compile(repo: Path):
    ctx = resolve_target_repo(repo=repo)
    init_workflow(ctx, master=repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(
        ctx,
        build_workflow_identity(
            ctx,
            master=repo / "master_prompt.md",
            worker_mode="mock",
            use_worktree=True,
            until="DONE",
            workflow_id="WF000001",
            run_id="R0001",
        ),
    )
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _complex_repo(git_repo: Path) -> Path:
    files = {
        "app.py": "from pipeline import run_pipeline\n\ndef main():\n    return run_pipeline('raw')\n",
        "pipeline.py": "from service import transform\n\ndef run_pipeline(value):\n    return transform(value)\n",
        "service.py": "from formatter import format_value\nfrom validator import is_allowed\n\ndef transform(value):\n    if not is_allowed(value):\n        return 'not ok'\n    return format_value(value)\n",
        "formatter.py": "def format_value(value):\n    return 'ok'\n",
        "validator.py": "def is_allowed(value):\n    return True\n",
        "config.py": "TARGET_VALUE = 'me'\n",
        "master_prompt.md": "Make the app pipeline return me through the entrypoint and prove it.\n",
    }
    for rel, content in files.items():
        (git_repo / rel).write_text(content, encoding="utf-8")
    run(["git", "add", "."], git_repo)
    run(["git", "commit", "-m", "complex target"], git_repo)
    return git_repo


def _same_file_repo(git_repo: Path) -> Path:
    (git_repo / "app.py").write_text(
        "def parse_input(value):\n    return value\n\n"
        "def validate_input(value):\n    return True\n\n"
        "def transform_value(value):\n    return value\n\n"
        "def format_output(value):\n    return 'ok'\n\n"
        "def main():\n    return format_output(transform_value(parse_input('raw')))\n",
        encoding="utf-8",
    )
    (git_repo / "master_prompt.md").write_text(
        "Make app process the input through validation, transformation, and formatting so main returns me and prove it.\n",
        encoding="utf-8",
    )
    run(["git", "add", "."], git_repo)
    run(["git", "commit", "-m", "same file target"], git_repo)
    return git_repo


def test_complex_multi_file_target_generates_at_least_five_patchlets(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    index = read_json(ctx.paths.patchlet_index)
    assert len(index["patchlets"]) >= 5


def test_multi_patchlet_generation_uses_real_decomposition_artifacts(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert (ctx.paths.workflow_dir / "decomposition/work_decomposition_plan.json").exists()
    assert (ctx.paths.workflow_dir / "decomposition/work_slices.json").exists()
    assert (ctx.paths.workflow_dir / "decomposition/patchlet_plan.json").exists()


def test_every_generated_patchlet_has_exactly_one_allowed_file(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    for patchlet in read_json(ctx.paths.patchlet_index)["patchlets"]:
        assert patchlet["allowed_product_runtime_file"]
        assert patchlet["allowed_product_runtime_files"] == [patchlet["allowed_product_runtime_file"]]


def test_generated_patchlets_have_work_slice_ids(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert all(p.get("work_slice_id") for p in read_json(ctx.paths.patchlet_index)["patchlets"])


def test_generated_patchlets_have_time_budget_seconds(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert all(p.get("time_budget_seconds") == 600 for p in read_json(ctx.paths.patchlet_index)["patchlets"])


def test_generated_patchlets_have_dependency_metadata(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert any(p.get("dependency_patchlet_ids") for p in read_json(ctx.paths.patchlet_index)["patchlets"])


def test_generated_patchlets_reference_proof_obligations(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert all("PO001" in p.get("proof_obligation_ids", []) for p in read_json(ctx.paths.patchlet_index)["patchlets"])


def test_same_file_can_generate_multiple_ordered_patchlets(git_repo: Path):
    ctx = _compile(_same_file_repo(git_repo))
    patchlets = read_json(ctx.paths.patchlet_index)["patchlets"]
    app_patchlets = [p for p in patchlets if p["allowed_product_runtime_file"] == "app.py"]
    assert len(app_patchlets) >= 2
    assert any(p.get("dependency_patchlet_ids") for p in app_patchlets[1:])


def test_same_file_multiple_patchlets_are_not_parallel_by_default(git_repo: Path):
    ctx = _compile(_same_file_repo(git_repo))
    graph = read_json(ctx.paths.workflow_dir / "decomposition/dependency_graph.json")
    assert graph["edges"]


def test_multi_patchlet_plan_writes_transaction_group_plan(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert (ctx.paths.workflow_dir / "decomposition/transaction_group_plan.json").exists()


def test_multi_patchlet_plan_updates_goal_progress(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    from codex_orchestrator.goal_progress import update_goal_progress

    update_goal_progress(workflow_root=ctx.paths.workflow_dir, event_reason="test", workflow_iteration=1)
    assert read_json(ctx.paths.workflow_dir / "goal_progress.json")["decomposition"]["patchlet_count"] >= 5


def test_no_manual_artifact_tampering_required(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert validate_json_file(ctx.paths.workflow_dir / "decomposition/patchlet_plan.json", "patchlet_plan.schema.json") == []
