from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

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

    def to_json(self) -> dict:
        return asdict(self)


class CommandRunner:
    def run(
        self,
        args: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int | None = None,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        check: bool = False,
    ) -> CommandResult:
        started = time.time()
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        try:
            proc = subprocess.run(
                args,
                cwd=str(cwd),
                env=proc_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
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
        )
        if check and exit_code != 0:
            raise subprocess.CalledProcessError(exit_code, args, output=stdout, stderr=stderr)
        return result


def command_available(name: str) -> bool:
    return shutil.which(name) is not None
