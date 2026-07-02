from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitSnapshot:
    head: str | None
    status: dict[str, str]


def repo_head(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip() or None


def snapshot_status(repo_root: Path) -> GitSnapshot:
    status: dict[str, str] = {}
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return GitSnapshot(head=None, status={})
    for line in result.stdout.splitlines():
        if not line:
            continue
        code = line[:2]
        path = line[3:]
        # For renamed files, keep the destination path for guard purposes.
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        status[path] = code
    return GitSnapshot(head=repo_head(repo_root), status=status)


def changed_between(before: GitSnapshot, after: GitSnapshot) -> list[str]:
    changed: list[str] = []
    all_paths = set(before.status) | set(after.status)
    for path in sorted(all_paths):
        if before.status.get(path) != after.status.get(path):
            changed.append(path)
    return changed


def git_diff(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return result.stdout
