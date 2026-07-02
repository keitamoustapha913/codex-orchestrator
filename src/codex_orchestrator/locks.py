from __future__ import annotations

import json
import os
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import version
from .errors import CxorError


@contextmanager
def workflow_lock(lock_path: Path, *, target_repo_root: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": " ".join(sys.argv),
        "orchestrator_version": version.__version__,
        "target_repo_root": str(target_repo_root),
    }
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise CxorError(f"Workflow lock already exists: {lock_path}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
