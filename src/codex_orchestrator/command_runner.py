from __future__ import annotations

import os
import signal
import selectors
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

from .atomic_io import atomic_write_text


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    cwd: str
    exit_code: int
    started_at: float
    ended_at: float
    duration_seconds: float
    stdout_path: str | None
    stderr_path: str | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    interrupted: bool = False
    timeout_seconds: int | None = None
    termination_signal: str | None = None

    def to_json(self) -> dict:
        return asdict(self)


class CommandRunner:
    def run(
        self,
        args: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        input_text: str | None = None,
        timeout_seconds: int | None = None,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        check: bool = False,
        stdout_line_callback: Callable[[str, float], None] | None = None,
        liveness_callback: Callable[[dict], None] | None = None,
        progress_interval_seconds: int | None = None,
        no_progress_stall_seconds: int | None = None,
        patchlet_id: str | None = None,
        attempt_id: str | None = None,
    ) -> CommandResult:
        started = time.time()
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        timed_out = False
        interrupted = False
        exit_code = 0
        stdout = ""
        stderr = ""
        termination_signal: str | None = None
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        last_progress_at = started
        last_event_type = "process.started"
        last_liveness_at = started
        warned_budget = False
        interval = progress_interval_seconds if progress_interval_seconds and progress_interval_seconds > 0 else None
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(cwd),
                env=proc_env,
                text=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                start_new_session=True,
            )
            if proc.stdin is not None:
                if input_text:
                    proc.stdin.write(input_text)
                proc.stdin.close()

            selector = selectors.DefaultSelector()
            if proc.stdout is not None:
                selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
            if proc.stderr is not None:
                selector.register(proc.stderr, selectors.EVENT_READ, "stderr")

            while selector.get_map():
                now = time.time()
                if interval and now - last_liveness_at >= interval:
                    _emit_liveness(
                        liveness_callback,
                        started=started,
                        now=now,
                        patchlet_id=patchlet_id,
                        attempt_id=attempt_id,
                        last_event_type=last_event_type,
                        last_progress_at=last_progress_at,
                        timeout_seconds=timeout_seconds,
                        event_type="codex_liveness",
                        no_progress_stall_seconds=no_progress_stall_seconds,
                    )
                    last_liveness_at = now
                if (
                    timeout_seconds is not None
                    and not warned_budget
                    and timeout_seconds > 60
                    and timeout_seconds - (now - started) <= 60
                ):
                    _emit_liveness(
                        liveness_callback,
                        started=started,
                        now=now,
                        patchlet_id=patchlet_id,
                        attempt_id=attempt_id,
                        last_event_type=last_event_type,
                        last_progress_at=last_progress_at,
                        timeout_seconds=timeout_seconds,
                        event_type="patchlet_budget_warning",
                        no_progress_stall_seconds=no_progress_stall_seconds,
                    )
                    warned_budget = True
                if timeout_seconds is not None and now - started >= timeout_seconds and not timed_out:
                    timed_out = True
                    termination_signal = _terminate_process_group(proc, signal.SIGTERM)
                    _emit_liveness(
                        liveness_callback,
                        started=started,
                        now=now,
                        patchlet_id=patchlet_id,
                        attempt_id=attempt_id,
                        last_event_type=last_event_type,
                        last_progress_at=last_progress_at,
                        timeout_seconds=timeout_seconds,
                        event_type="patchlet_timed_out",
                        no_progress_stall_seconds=no_progress_stall_seconds,
                    )
                for key, _ in selector.select(timeout=0.1):
                    line = key.fileobj.readline()
                    if line == "":
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    if key.data == "stdout":
                        stdout_chunks.append(line)
                        parsed_event = _event_type_from_stdout_line(line)
                        if parsed_event:
                            last_event_type = parsed_event
                            last_progress_at = time.time()
                        if stdout_line_callback is not None:
                            stdout_line_callback(line, time.time() - started)
                    else:
                        stderr_chunks.append(line)
                if proc.poll() is not None and not selector.get_map():
                    break

            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                termination_signal = _terminate_process_group(proc, signal.SIGKILL)
                proc.wait(timeout=2)
            exit_code = 124 if timed_out else proc.returncode
            stdout = "".join(stdout_chunks)
            stderr = "".join(stderr_chunks)
            if timed_out:
                stderr = (
                    f"{stderr}\n" if stderr else ""
                ) + f"command timed out after {timeout_seconds} seconds"
            elif exit_code in {130, -signal.SIGINT} or "KeyboardInterrupt" in stderr:
                interrupted = True
                if exit_code == -signal.SIGINT:
                    exit_code = 130
                termination_signal = signal.SIGINT.name
        except KeyboardInterrupt:
            interrupted = True
            exit_code = 130
            try:
                if "proc" in locals():
                    termination_signal = _terminate_process_group(proc, signal.SIGTERM)
            finally:
                stdout = "".join(stdout_chunks)
                stderr = "".join(stderr_chunks)
                stderr = (f"{stderr}\n" if stderr else "") + "command interrupted by user"
        except FileNotFoundError as exc:
            exit_code = 127
            stdout = ""
            stderr = str(exc)
        ended = time.time()

        if stdout_path is not None:
            atomic_write_text(stdout_path, stdout)
        if stderr_path is not None:
            atomic_write_text(stderr_path, stderr)

        result = CommandResult(
            args=args,
            cwd=str(cwd),
            exit_code=exit_code,
            started_at=started,
            ended_at=ended,
            duration_seconds=ended - started,
            stdout_path=str(stdout_path) if stdout_path else None,
            stderr_path=str(stderr_path) if stderr_path else None,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            interrupted=interrupted,
            timeout_seconds=timeout_seconds,
            termination_signal=termination_signal,
        )
        if check and exit_code != 0:
            raise subprocess.CalledProcessError(exit_code, args, output=stdout, stderr=stderr)
        return result


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def _terminate_process_group(proc: subprocess.Popen, sig: signal.Signals) -> str:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        return sig.name
    except Exception:
        try:
            proc.send_signal(sig)
        except Exception:
            pass
    return sig.name


def _event_type_from_stdout_line(line: str) -> str | None:
    import json

    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    event_type = payload.get("type") or payload.get("event") or payload.get("kind")
    return event_type if isinstance(event_type, str) and event_type else None


def _emit_liveness(
    callback: Callable[[dict], None] | None,
    *,
    started: float,
    now: float,
    patchlet_id: str | None,
    attempt_id: str | None,
    last_event_type: str,
    last_progress_at: float,
    timeout_seconds: int | None,
    event_type: str,
    no_progress_stall_seconds: int | None,
) -> None:
    if callback is None:
        return
    no_progress_for = max(0.0, now - last_progress_at)
    payload = {
        "schema_version": "1.0",
        "kind": "codex_liveness",
        "event_type": event_type,
        "signal": event_type,
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "elapsed_seconds": round(now - started, 3),
        "last_event_type": last_event_type,
        "no_progress_for_seconds": round(no_progress_for, 3),
        "timeout_seconds": timeout_seconds,
        "remaining_seconds": round(max(0.0, timeout_seconds - (now - started)), 3)
        if timeout_seconds is not None
        else None,
        "stall_status": "likely_stalled"
        if no_progress_stall_seconds is not None and no_progress_for >= no_progress_stall_seconds
        else "active",
    }
    callback(payload)
