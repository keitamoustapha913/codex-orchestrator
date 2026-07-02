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
        self.codex_model = os.environ.get("CODEX_MODEL", "gpt-5.4-mini")
        self.codex_reasoning = os.environ.get("CODEX_REASONING", "medium")
        self.timeout_seconds = int(os.environ.get("CODEX_TIMEOUT_SECONDS", "120"))

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
        task_contract_path = run_dir / "worker_memory" / "TASK_CONTRACT.md"
        live_memory_md_path = run_dir / "worker_memory" / "LIVE_MEMORY.md"
        write_these_files_path = run_dir / "worker_memory" / "WRITE_THESE_FILES.md"
        preflight_stage_path = run_dir / "worker_stage" / "00_preflight.md"
        final_report_stage_path = run_dir / "worker_stage" / "05_final_report.md"
        attempt_prompt_path = run_dir / "codex_task_prompt.md"
        attempt_prompt_text = (
            "Before doing any task work, read:\n"
            f"- {task_contract_path}\n"
            f"- {live_memory_md_path}\n"
            f"- {write_these_files_path}\n\n"
            "Then write:\n"
            f"- {preflight_stage_path}\n\n"
            "Before final response, write:\n"
            f"- {final_report_stage_path}\n\n"
            "Do not write gate results. The orchestrator writes gates.\n\n"
            "Use those files as the attempt-local contract. Then continue with the patchlet instructions below.\n\n"
            + prompt_path.read_text(encoding="utf-8")
        )
        attempt_prompt_path.write_text(attempt_prompt_text, encoding="utf-8")
        repo_sha_before = repo_head(run_ctx.execution_root)
        final_message_path = run_dir / "codex_last_message.md"
        args = [
            self.codex_binary,
            "exec",
            "--cd",
            str(run_ctx.execution_root),
            "--model",
            self.codex_model,
            "--json",
            "--sandbox",
            "workspace-write",
            "-c",
            "approval_policy=never",
            "-c",
            "features.hooks=true",
            "-c",
            f"model_reasoning_effort={self.codex_reasoning}",
        ]
        if os.environ.get("CODEX_BYPASS_HOOK_TRUST") == "1":
            args.append("--dangerously-bypass-hook-trust")
        args.extend([
            "--output-last-message",
            str(final_message_path),
            "-",
        ])
        patchlet_id = patchlet["patchlet_id"]
        report_path = run_ctx.reports_dir / f"{patchlet_id}.json"
        probe_root = run_ctx.probe_dir / patchlet_id
        result = CommandRunner().run(
            args,
            cwd=run_ctx.execution_root,
            input_text=attempt_prompt_text,
            timeout_seconds=self.timeout_seconds,
            env={
                "CXOR_TARGET_ROOT": str(run_ctx.target_root),
                "CXOR_TARGET_REPO_ROOT": str(run_ctx.target_root),
                "CXOR_EXECUTION_ROOT": str(run_ctx.execution_root),
                "CXOR_ARTIFACT_ROOT": str(run_ctx.artifact_root),
                "CXOR_WORKFLOW_DIR": str(run_ctx.workflow_dir),
                "CXOR_PROBE_DIR": str(run_ctx.probe_dir),
                "CXOR_REPORTS_DIR": str(run_ctx.reports_dir),
                "CXOR_RUNS_DIR": str(run_ctx.runs_dir),
                "CXOR_RUN_DIR": str(run_dir),
                "CXOR_PATCHLET_ID": patchlet_id,
                "CXOR_ATTEMPT_ID": run_dir.name,
                "CXOR_ALLOWED_PRODUCT_RUNTIME_FILE": patchlet.get("allowed_product_runtime_file", ""),
                "CXOR_REPORT_PATH": str(report_path),
                "CXOR_PROBE_ROOT": str(probe_root),
            },
            stdout_path=run_dir / "stdout.txt",
            stderr_path=run_dir / "stderr.txt",
        )
        repo_sha_after = repo_head(run_ctx.execution_root)
        (run_dir / "command.json").write_text(json.dumps({
            **result.to_json(),
            "target_repo_root": str(run_ctx.target_root),
            "target_root": str(run_ctx.target_root),
            "execution_root": str(run_ctx.execution_root),
            "artifact_root": str(run_ctx.artifact_root),
            "workflow_dir": str(run_ctx.workflow_dir),
            "probe_dir": str(run_ctx.probe_dir),
            "reports_dir": str(run_ctx.reports_dir),
            "runs_dir": str(run_ctx.runs_dir),
            "run_dir": str(run_dir),
            "prompt_path": str(attempt_prompt_path),
            "final_message_path": str(final_message_path),
            "patchlet_id": patchlet_id,
            "attempt_id": run_dir.name,
            "report_path": str(report_path),
            "probe_root": str(probe_root),
            "repo_sha_before": repo_sha_before,
            "repo_sha_after": repo_sha_after,
            "timed_out": result.timed_out,
            "timeout_seconds": result.timeout_seconds,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (run_dir / "output.jsonl").write_text(json.dumps({
            "args": args,
            "cwd": str(run_ctx.execution_root),
            "exit_code": result.exit_code,
            "stdout_path": str(run_dir / "stdout.txt"),
            "stderr_path": str(run_dir / "stderr.txt"),
            "target_repo_root": str(run_ctx.target_root),
            "target_root": str(run_ctx.target_root),
            "execution_root": str(run_ctx.execution_root),
            "artifact_root": str(run_ctx.artifact_root),
            "workflow_dir": str(run_ctx.workflow_dir),
            "probe_dir": str(run_ctx.probe_dir),
            "reports_dir": str(run_ctx.reports_dir),
            "runs_dir": str(run_ctx.runs_dir),
            "run_dir": str(run_dir),
            "prompt_path": str(attempt_prompt_path),
            "final_message_path": str(final_message_path),
            "patchlet_id": patchlet_id,
            "attempt_id": run_dir.name,
            "report_path": str(report_path),
            "probe_root": str(probe_root),
            "repo_sha_before": repo_sha_before,
            "repo_sha_after": repo_sha_after,
            "timed_out": result.timed_out,
            "timeout_seconds": result.timeout_seconds,
        }) + "\n", encoding="utf-8")
        if result.exit_code != 0:
            timeout_note = f" timed out after {result.timeout_seconds}s;" if result.timed_out else ""
            raise WorkerExecutionError(
                f"codex worker failed with exit_code={result.exit_code};{timeout_note} "
                f"cwd={run_ctx.execution_root}; target repo={run_ctx.target_root}"
            )
        if not report_path.exists():
            raise WorkerExecutionError(f"codex worker did not produce report: {report_path}")
        return WorkerResult(
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            report_path=report_path if report_path.exists() else None,
        )
