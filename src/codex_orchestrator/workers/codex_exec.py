from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from codex_orchestrator.command_runner import CommandRunner
from codex_orchestrator.errors import WorkerExecutionError, WorkerPreconditionError
from codex_orchestrator.git_guard import repo_head
from codex_orchestrator.target_repo import TargetRepoContext

from .base import Worker, WorkerResult


class CodexExecWorker(Worker):
    def __init__(self, codex_binary: str | None = None) -> None:
        self.codex_binary = codex_binary or os.environ.get("CXOR_CODEX_BINARY", "codex")

    def run_patchlet(self, ctx: TargetRepoContext, patchlet: dict, *, run_dir: Path) -> WorkerResult:
        prompt_path = ctx.root / patchlet["subprompt_path"]
        if not prompt_path.exists():
            raise WorkerPreconditionError(f"Missing patchlet prompt: {prompt_path}")
        if shutil.which(self.codex_binary) is None:
            raise WorkerPreconditionError(f"Codex binary not found: {self.codex_binary}")
        run_dir.mkdir(parents=True, exist_ok=True)
        repo_sha_before = repo_head(ctx.root)
        args = [self.codex_binary, "exec", "--json", str(prompt_path)]
        result = CommandRunner().run(
            args,
            cwd=ctx.root,
            stdout_path=run_dir / "stdout.txt",
            stderr_path=run_dir / "stderr.txt",
        )
        repo_sha_after = repo_head(ctx.root)
        (run_dir / "command.json").write_text(json.dumps({
            **result.to_json(),
            "target_repo_root": str(ctx.root),
            "patchlet_id": patchlet["patchlet_id"],
            "repo_sha_before": repo_sha_before,
            "repo_sha_after": repo_sha_after,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (run_dir / "output.jsonl").write_text(json.dumps({
            "args": args,
            "cwd": str(ctx.root),
            "exit_code": result.exit_code,
            "stdout_path": str(run_dir / "stdout.txt"),
            "stderr_path": str(run_dir / "stderr.txt"),
            "target_repo_root": str(ctx.root),
            "repo_sha_before": repo_sha_before,
            "repo_sha_after": repo_sha_after,
        }) + "\n", encoding="utf-8")
        if result.exit_code != 0:
            raise WorkerExecutionError(
                f"codex worker failed with exit_code={result.exit_code}; "
                f"cwd={ctx.root}; target repo={ctx.root}"
            )
        report_path = ctx.paths.reports_dir / f"{patchlet['patchlet_id']}.json"
        if not report_path.exists():
            raise WorkerExecutionError(f"codex worker did not produce report: {report_path}")
        return WorkerResult(
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            report_path=report_path if report_path.exists() else None,
        )
