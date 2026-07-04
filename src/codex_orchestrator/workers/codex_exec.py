from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from codex_orchestrator.codex_execution_policy import (
    ExecutionPolicyError,
    resolve_patchlet_timeout_seconds,
    resolve_progress_interval_seconds,
    soft_deadline_seconds,
)
from codex_orchestrator.codex_model_profile import resolve_codex_model_profile
from codex_orchestrator.command_runner import CommandRunner
from codex_orchestrator.errors import WorkerExecutionError, WorkerPreconditionError
from codex_orchestrator.git_guard import repo_head
from codex_orchestrator.live_progress import (
    LiveProgressPolicyError,
    LiveProgressReporter,
    compact_codex_signal,
    resolve_live_progress_policy,
)
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.prompt_index import upsert_prompt_index_entry
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.worker_capsule import (
    final_report_contract_text,
    report_schema_contract_text,
    runtime_side_effect_contract_text,
)

from .base import Worker, WorkerResult, ensure_run_context


class CodexExecWorker(Worker):
    def __init__(self, codex_binary: str | None = None) -> None:
        self.codex_binary = codex_binary or os.environ.get("CXOR_CODEX_BINARY", "codex")
        self.model_profile = resolve_codex_model_profile("patchlet", os.environ)
        self.codex_model = self.model_profile.model
        self.codex_reasoning = self.model_profile.reasoning
        try:
            self.timeout_seconds = resolve_patchlet_timeout_seconds(os.environ)
            self.progress_interval_seconds = resolve_progress_interval_seconds(os.environ)
            self.live_progress_policy = resolve_live_progress_policy(os.environ)
        except (ExecutionPolicyError, LiveProgressPolicyError) as exc:
            raise WorkerPreconditionError(str(exc)) from exc
        self.soft_deadline_seconds = soft_deadline_seconds(self.timeout_seconds)

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
        report_contract_path = run_dir / "worker_memory" / "REPORT_SCHEMA_CONTRACT.md"
        final_report_contract_path = run_dir / "worker_memory" / "FINAL_REPORT_CONTRACT.md"
        runtime_contract_path = run_dir / "worker_memory" / "RUNTIME_SIDE_EFFECT_CONTRACT.md"
        live_memory_md_path = run_dir / "worker_memory" / "LIVE_MEMORY.md"
        write_these_files_path = run_dir / "worker_memory" / "WRITE_THESE_FILES.md"
        worker_stage_dir = run_dir / "worker_stage"
        worker_memory_dir = run_dir / "worker_memory"
        worker_hooks_dir = run_dir / "worker_hooks"
        gates_dir = run_dir / "gates"
        diagnostics_dir = run_dir / "diagnostics"
        preflight_stage_path = run_dir / "worker_stage" / "00_preflight.md"
        final_report_stage_path = run_dir / "worker_stage" / "05_final_report.md"
        forbidden_target_worker_stage = run_ctx.target_root / "worker_stage"
        attempt_prompt_path = run_dir / "codex_task_prompt.md"
        progress_path = run_dir / "progress.jsonl"
        attempt_prompt_text = (
            "Before doing any task work, read:\n"
            f"- {task_contract_path}\n"
            f"- {report_contract_path}\n"
            f"- {final_report_contract_path}\n"
            f"- {runtime_contract_path}\n"
            f"- {live_memory_md_path}\n"
            f"- {write_these_files_path}\n\n"
            "Use explicit Worker Capsule paths from the environment:\n"
            f"- CXOR_WORKER_STAGE_DIR={worker_stage_dir}\n"
            f"- CXOR_WORKER_MEMORY_DIR={worker_memory_dir}\n"
            f"- CXOR_WORKER_HOOKS_DIR={worker_hooks_dir}\n"
            f"- CXOR_GATES_DIR={gates_dir}\n"
            f"- CXOR_DIAGNOSTICS_DIR={diagnostics_dir}\n"
            f"- CXOR_PREFLIGHT_PATH={preflight_stage_path}\n"
            f"- CXOR_FINAL_REPORT_PATH={final_report_stage_path}\n\n"
            "Then write the preflight only to:\n"
            f"- $CXOR_PREFLIGHT_PATH ({preflight_stage_path})\n\n"
            "Before final response, write the final report only to:\n"
            f"- $CXOR_FINAL_REPORT_PATH ({final_report_stage_path})\n\n"
            f"Do not create target-root worker_stage/ at {forbidden_target_worker_stage}/. "
            "All Worker Capsule stage files must stay under $CXOR_WORKER_STAGE_DIR.\n\n"
            f"You have a hard timeout of {self.timeout_seconds} seconds. "
            f"Aim to finish by {self.soft_deadline_seconds} seconds. "
            "If you cannot complete, write $CXOR_FINAL_REPORT_PATH with an explicit "
            "BLOCKED or FAILED status and preserve what you learned. "
            "Do not keep investigating indefinitely. Do not use blind retry.\n\n"
            "Do not write gate results. The orchestrator writes gates.\n\n"
            "When running probes, avoid creating language-runtime caches or build byproducts under target root.\n"
            "Do not load target-root product/runtime files in a way that mutates target-root state.\n"
            "The target hygiene gate will detect and report runtime byproduct leaks.\n\n"
            "Use those files as the attempt-local contract. Then continue with the patchlet instructions below.\n\n"
            + prompt_path.read_text(encoding="utf-8")
        )
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
        allowed_file = patchlet.get("allowed_product_runtime_file", "")
        live_progress = LiveProgressReporter(self.live_progress_policy, attempt_id=run_dir.name)
        attempt_prompt_text = (
            attempt_prompt_text
            + "\n\n## Concrete execution-root edit contract\n\n"
            + f"Allowed product/runtime edit path: $CXOR_EXECUTION_ROOT/{allowed_file} ({run_ctx.execution_root / allowed_file})\n"
            + f"Forbidden product/runtime edit path: $CXOR_TARGET_ROOT/{allowed_file} ({run_ctx.target_root / allowed_file})\n"
            + "Product/runtime files under target root are read-only to the worker. "
            + "Target-root artifact directories remain writable only under .codex-orchestrator/ and .artifacts/probes/.\n\n"
            + "## Embedded report schema contract\n\n"
            + report_schema_contract_text(
                patchlet_id=patchlet_id,
                report_path=f".codex-orchestrator/reports/{patchlet_id}.json",
            )
            + "\n\n## Embedded final report contract\n\n"
            + final_report_contract_text(
                patchlet_id=patchlet_id,
                attempt_id=run_dir.name,
                final_report_path=str(final_report_stage_path),
                report_path=f".codex-orchestrator/reports/{patchlet_id}.json",
                probe_root=f".artifacts/probes/{patchlet_id}",
            )
            + "\n\n## Embedded runtime side-effect contract\n\n"
            + runtime_side_effect_contract_text()
        )
        attempt_prompt_path.write_text(attempt_prompt_text, encoding="utf-8")
        upsert_prompt_index_entry(ctx.root, {
            "kind": "repair_worker_prompt" if patchlet.get("is_repair_patchlet") else "patchlet_worker_prompt",
            "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
            "patchlet_id": patchlet_id,
            "attempt_id": run_dir.name,
            "repair_plan_id": patchlet.get("repair_plan_id"),
            "failure_ids": patchlet.get("source_failure_ids", []),
            "title": f"{allowed_file} — {patchlet_id}",
            "summary": f"Worker prompt for patchlet {patchlet_id}.",
            "path": attempt_prompt_path,
            "subprompt_path": patchlet.get("subprompt_path"),
            "model": self.codex_model,
            "reasoning": self.codex_reasoning,
            "contracts": [
                "TASK_CONTRACT.md",
                "REPORT_SCHEMA_CONTRACT.md",
                "FINAL_REPORT_CONTRACT.md",
                "RUNTIME_SIDE_EFFECT_CONTRACT.md",
            ],
            "artifact_paths": [str(attempt_prompt_path)],
        })

        def write_progress_event(payload: dict) -> None:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            with progress_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")

        def record_progress(raw_line: str, elapsed_seconds: float) -> None:
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                return
            if not isinstance(event, dict):
                return
            signal = event.get("type") or event.get("event") or event.get("kind")
            if not isinstance(signal, str) or not signal:
                return
            payload = {
                "schema_version": "1.0",
                "kind": "codex_progress",
                "patchlet_id": patchlet_id,
                "attempt_id": run_dir.name,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "signal": signal,
                "source": "stdout_jsonl",
            }
            summary = event.get("summary")
            if isinstance(summary, str) and summary:
                payload["summary"] = summary[:200]
            write_progress_event(payload)
            compact_signal = compact_codex_signal(event)
            if compact_signal:
                live_progress.emit(compact_signal, elapsed_seconds)

        write_progress_event({
            "schema_version": "1.0",
            "kind": "codex_progress",
            "patchlet_id": patchlet_id,
            "attempt_id": run_dir.name,
            "elapsed_seconds": 0,
            "signal": "process.started",
            "source": "runner",
        })
        live_progress.emit("process.started", 0, force=True)
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
                "CXOR_WORKER_STAGE_DIR": str(worker_stage_dir),
                "CXOR_WORKER_MEMORY_DIR": str(worker_memory_dir),
                "CXOR_WORKER_HOOKS_DIR": str(worker_hooks_dir),
                "CXOR_GATES_DIR": str(gates_dir),
                "CXOR_DIAGNOSTICS_DIR": str(diagnostics_dir),
                "CXOR_PREFLIGHT_PATH": str(preflight_stage_path),
                "CXOR_FINAL_REPORT_PATH": str(final_report_stage_path),
                "CXOR_PATCHLET_ID": patchlet_id,
                "CXOR_ATTEMPT_ID": run_dir.name,
                "CXOR_TIMEOUT_SECONDS": str(self.timeout_seconds),
                "CXOR_SOFT_DEADLINE_SECONDS": str(self.soft_deadline_seconds),
                "CXOR_ALLOWED_PRODUCT_RUNTIME_FILE": patchlet.get("allowed_product_runtime_file", ""),
                "CXOR_REPORT_PATH": str(report_path),
                "CXOR_PROBE_ROOT": str(probe_root),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            stdout_path=run_dir / "stdout.txt",
            stderr_path=run_dir / "stderr.txt",
            stdout_line_callback=record_progress,
        )
        live_progress.emit(f"exited {result.exit_code}", result.duration_seconds, force=True)
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
            "progress_path": str(progress_path),
            "repo_sha_before": repo_sha_before,
            "repo_sha_after": repo_sha_after,
            "timed_out": result.timed_out,
            "timeout_seconds": result.timeout_seconds,
            "soft_deadline_seconds": self.soft_deadline_seconds,
            "selected_model": self.codex_model,
            "selected_reasoning": self.codex_reasoning,
            "env": {
                "PYTHONDONTWRITEBYTECODE": "1",
            },
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
            "progress_path": str(progress_path),
            "repo_sha_before": repo_sha_before,
            "repo_sha_after": repo_sha_after,
            "timed_out": result.timed_out,
            "timeout_seconds": result.timeout_seconds,
            "soft_deadline_seconds": self.soft_deadline_seconds,
            "selected_model": self.codex_model,
            "selected_reasoning": self.codex_reasoning,
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
