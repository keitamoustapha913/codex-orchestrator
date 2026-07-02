from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from codex_orchestrator.command_runner import CommandRunner
from codex_orchestrator.errors import WorkerExecutionError, WorkerPreconditionError
from codex_orchestrator.git_guard import repo_head
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.target_repo import TargetRepoContext

from .base import Worker, WorkerResult, ensure_run_context


class CodexExecWorker(Worker):
    def __init__(self, codex_binary: str | None = None) -> None:
        self.codex_binary = codex_binary or os.environ.get("CXOR_CODEX_BINARY", "codex")

    def run_patchlet(
        self,
        ctx: TargetRepoContext,
        patchlet: dict,
        *,
        run_dir: Path | None = None,
        run_ctx: PatchletRunContext | None = None,
    ) -> WorkerResult:
        run_ctx = ensure_run_context(ctx, patchlet=patchlet, run_dir=run_dir, run_ctx=run_ctx)
        run_dir = run_ctx.run_dir
        prompt_path = run_ctx.artifact_root / patchlet["subprompt_path"]
        if not prompt_path.exists():
            raise WorkerPreconditionError(f"Missing patchlet prompt: {prompt_path}")
        if shutil.which(self.codex_binary) is None:
            raise WorkerPreconditionError(f"Codex binary not found: {self.codex_binary}")
        run_dir.mkdir(parents=True, exist_ok=True)
        repo_sha_before = repo_head(run_ctx.execution_root)
        args = [self.codex_binary, "exec", "--json", str(prompt_path)]
        result = CommandRunner().run(
            args,
            cwd=run_ctx.execution_root,
            stdout_path=run_dir / "stdout.txt",
            stderr_path=run_dir / "stderr.txt",
        )
        repo_sha_after = repo_head(run_ctx.execution_root)
        (run_dir / "command.json").write_text(json.dumps({
            **result.to_json(),
            "target_repo_root": str(run_ctx.target_root),
            "execution_root": str(run_ctx.execution_root),
            "artifact_root": str(run_ctx.artifact_root),
            "patchlet_id": patchlet["patchlet_id"],
            "repo_sha_before": repo_sha_before,
            "repo_sha_after": repo_sha_after,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (run_dir / "output.jsonl").write_text(json.dumps({
            "args": args,
            "cwd": str(run_ctx.execution_root),
            "exit_code": result.exit_code,
            "stdout_path": str(run_dir / "stdout.txt"),
            "stderr_path": str(run_dir / "stderr.txt"),
            "target_repo_root": str(run_ctx.target_root),
            "execution_root": str(run_ctx.execution_root),
            "artifact_root": str(run_ctx.artifact_root),
            "repo_sha_before": repo_sha_before,
            "repo_sha_after": repo_sha_after,
        }) + "\n", encoding="utf-8")
        if result.exit_code != 0:
            raise WorkerExecutionError(
                f"codex worker failed with exit_code={result.exit_code}; "
                f"cwd={run_ctx.execution_root}; target repo={run_ctx.target_root}"
            )
        report_path = run_ctx.reports_dir / f"{patchlet['patchlet_id']}.json"
        if not report_path.exists():
            raise WorkerExecutionError(f"codex worker did not produce report: {report_path}")
        return WorkerResult(
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            report_path=report_path if report_path.exists() else None,
        )
