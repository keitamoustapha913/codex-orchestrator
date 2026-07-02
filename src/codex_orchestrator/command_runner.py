from __future__ import annotations

import os
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
    timeout_seconds: int | None = None

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
    ) -> CommandResult:
        started = time.time()
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        timed_out = False
        exit_code = 0
        stdout = ""
        stderr = ""
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
            )
            if proc.stdin is not None:
                if input_text:
                    proc.stdin.write(input_text)
                proc.stdin.close()

            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []
            selector = selectors.DefaultSelector()
            if proc.stdout is not None:
                selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
            if proc.stderr is not None:
                selector.register(proc.stderr, selectors.EVENT_READ, "stderr")

            while selector.get_map():
                if timeout_seconds is not None and time.time() - started >= timeout_seconds and not timed_out:
                    timed_out = True
                    proc.kill()
                for key, _ in selector.select(timeout=0.1):
                    line = key.fileobj.readline()
                    if line == "":
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    if key.data == "stdout":
                        stdout_chunks.append(line)
                        if stdout_line_callback is not None:
                            stdout_line_callback(line, time.time() - started)
                    else:
                        stderr_chunks.append(line)
                if proc.poll() is not None and not selector.get_map():
                    break

            proc.wait()
            exit_code = 124 if timed_out else proc.returncode
            stdout = "".join(stdout_chunks)
            stderr = "".join(stderr_chunks)
            if timed_out:
                stderr = (
                    f"{stderr}\n" if stderr else ""
                ) + f"command timed out after {timeout_seconds} seconds"
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
            timeout_seconds=timeout_seconds,
        )
        if check and exit_code != 0:
            raise subprocess.CalledProcessError(exit_code, args, output=stdout, stderr=stderr)
        return result


def command_available(name: str) -> bool:
    return shutil.which(name) is not None
