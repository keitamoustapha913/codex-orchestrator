from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from codex_orchestrator.jsonio import read_json
from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity
from codex_orchestrator.workers.mock import MockWorker

from test_multi_patchlet_decomposition import _write_planning


PRODUCT_TARGETS = [
    ("entrypoint.mjs", "entrypoint", "ready"),
    ("pipeline.mjs", "pipeline", "ready"),
    ("service.mjs", "service", "ready"),
    ("formatter.mjs", "formatter", "ready"),
    ("limits.mjs", "limits", "ready"),
]

DEBRIS = {
    ".codex/runtime/session.json": "{}\n",
    ".agents/cache/trace.txt": "trace\n",
    ".supervised-hidden": "hidden\n",
    "nested-cache/runtime/value.tmp": "cache\n",
    "temporary-output.log": "temporary\n",
}


class SupervisedDebrisWorker:
    def __init__(self) -> None:
        self.mock = MockWorker()

    def run_patchlet(self, ctx, patchlet, *, run_dir=None, run_ctx=None):
        result = self.mock.run_patchlet(ctx, patchlet, run_dir=run_dir, run_ctx=run_ctx)
        assert run_ctx is not None
        if patchlet["patchlet_id"] in {"P0002", "P0004"}:
            for relative, content in DEBRIS.items():
                path = run_ctx.execution_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        return result


def _commit_javascript_target(git_repo: Path) -> None:
    for target_file, symbol, _expected in PRODUCT_TARGETS:
        (git_repo / target_file).write_text(
            f"export const {symbol} = 'initial';\n",
            encoding="utf-8",
        )
    (git_repo / "master_prompt.md").write_text(
        "Update the five JavaScript runtime boundaries and prove every change.\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "five-patchlet JavaScript target"],
        cwd=git_repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _compile_five_patchlets(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    state = init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(
        ctx,
        build_workflow_identity(
            ctx,
            master=git_repo / "master_prompt.md",
            worker_mode="mock",
            use_worktree=True,
            until="DONE",
            workflow_id=state.workflow_id,
            run_id="R0001",
        ),
    )
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    _write_planning(ctx, targets=PRODUCT_TARGETS)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _git_tree_paths(repo: Path, commit: str) -> set[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return set(result.stdout.splitlines())


def test_supervised_five_patchlet_javascript_allowlist_proof(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _commit_javascript_target(git_repo)
    ctx = _compile_five_patchlets(git_repo)
    initial_patchlets = read_json(ctx.paths.patchlet_index)["patchlets"]
    assert [row["patchlet_id"] for row in initial_patchlets] == [
        "P0001",
        "P0002",
        "P0003",
        "P0004",
        "P0005",
    ]
    assert {
        row["allowed_product_runtime_file"] for row in initial_patchlets
    } == {
        row[0] for row in PRODUCT_TARGETS
    }

    scenario = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    scenario.parent.mkdir(parents=True, exist_ok=True)
    scenario.write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "codex_orchestrator.stages.run_patchlet.worker_for_mode",
        lambda _mode: SupervisedDebrisWorker(),
    )

    final_state = run_auto(
        ctx,
        resume=True,
        until="DONE",
        worker_mode="mock",
        use_worktree=False,
        max_iterations=100,
    )

    final_patchlets = read_json(ctx.paths.patchlet_index)["patchlets"]
    assert final_state.stage == "DONE"
    assert len(final_patchlets) == 5
    assert all(row["status"] == "COMPLETE" for row in final_patchlets)
    assert not list(ctx.paths.failures_dir.glob("F*.json"))
    assert not list(ctx.paths.repair_plans_dir.glob("RP*.json"))

    promoted_tree_paths: set[str] = set()
    for patchlet in final_patchlets:
        allowed_file = patchlet["allowed_product_runtime_file"]
        run_dir = ctx.paths.runs_dir / f"{patchlet['patchlet_id']}_attempt1"
        hygiene = read_json(run_dir / "gates" / "worker_sandbox_hygiene_result.json")
        proposal = read_json(run_dir / "patch_promotion" / "patch_proposal_manifest.json")
        reconstruction = read_json(run_dir / "patch_promotion" / "patch_reconstruction_result.json")
        proof = read_json(run_dir / "gates" / "independent_probe_rerun_result.json")
        coverage = read_json(run_dir / "gates" / "goal_coverage_gate_result.json")
        semantic = read_json(run_dir / "gates" / "canonical_patchlet_semantic_result.json")
        promotion = read_json(run_dir / "patch_promotion" / "clean_candidate_promotion_result.json")

        assert hygiene["promotion_blocked"] is False
        assert [row["path"] for row in proposal["changed_paths"]] == [allowed_file]
        assert reconstruction["accepted"] is True
        assert reconstruction["reconstructed_changed_paths"] == [allowed_file]
        assert reconstruction["unexpected_paths"] == []
        assert proof["accepted"] is True
        assert coverage["accepted"] is True
        assert semantic["accepted"] is True
        assert promotion["promotion_accepted"] is True

        promoted_tree_paths = _git_tree_paths(git_repo, promotion["integration_ref_after"])
        for debris_path in DEBRIS:
            assert debris_path not in promoted_tree_paths

        ledger = {row["path"]: row for row in hygiene["change_classification_ledger"]}
        if patchlet["patchlet_id"] in {"P0002", "P0004"}:
            for debris_path in DEBRIS:
                assert ledger[debris_path]["classification"] == "SANDBOX_DEBRIS"
                assert ledger[debris_path]["blocking"] is False
                assert ledger[debris_path]["promotion_eligible"] is False
                assert ledger[debris_path]["excluded_from_promotion"] is True
        else:
            assert all(path not in ledger for path in DEBRIS)

    assert promoted_tree_paths
    satisfaction = read_json(
        ctx.paths.workflow_dir / "global_verification" / "master_prompt_satisfaction_result.json"
    )
    final_verification = read_json(ctx.paths.final_verification_json)
    assert satisfaction["accepted"] is True
    assert satisfaction["satisfaction_status"] == "SATISFIED"
    assert len(satisfaction["proven_obligation_ids"]) == 5
    assert final_verification["status"] == "DONE"
    assert final_verification["master_prompt_satisfaction_status"] == "SATISFIED"
