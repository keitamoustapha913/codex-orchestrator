from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import TargetRepoError
from .paths import WorkflowPaths, build_paths


@dataclass(frozen=True)
class TargetRepoContext:
    root: Path
    workflow_dir: Path
    probe_dir: Path
    config_path: Path
    state_path: Path
    run_manifest_path: Path
    git_root: Path | None
    is_git_repo: bool
    allow_non_git: bool
    allow_self_target: bool
    paths: WorkflowPaths


def _git_root(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    out = result.stdout.strip()
    return Path(out).resolve() if out else None


def _looks_like_orchestrator_source(root: Path) -> bool:
    pyproject = root / "pyproject.toml"
    has_package = (root / "src" / "codex_orchestrator").is_dir()
    if not pyproject.exists() or not has_package:
        return False
    try:
        content = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False
    return 'name = "codex-orchestrator"' in content or "name = 'codex-orchestrator'" in content


def resolve_target_repo(
    repo: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
    allow_non_git: bool = False,
    allow_self_target: bool = False,
    repo_exact: bool = False,
) -> TargetRepoContext:
    start = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()

    if repo is not None:
        requested = Path(repo).expanduser().resolve()
        if not requested.exists():
            raise TargetRepoError(f"Target repository path does not exist: {requested}")
        if not requested.is_dir():
            raise TargetRepoError(f"Target repository path is not a directory: {requested}")
        git_root = _git_root(requested)
        if git_root is None:
            if not allow_non_git:
                raise TargetRepoError(
                    f"Path is not a Git repository: {requested}. Pass --allow-non-git to override."
                )
            root = requested
            is_git_repo = False
        else:
            root = requested if repo_exact else git_root
            is_git_repo = True
    else:
        git_root = _git_root(start)
        if git_root is None:
            if not allow_non_git:
                raise TargetRepoError(
                    "No target repository found. Run inside a Git repository or pass --repo /path/to/repo."
                )
            root = start
            is_git_repo = False
        else:
            root = git_root
            is_git_repo = True

    if _looks_like_orchestrator_source(root) and not allow_self_target:
        raise TargetRepoError(
            f"Target repo appears to be the orchestrator source repo: {root}. "
            "Pass --allow-self-target only if dogfooding is intentional."
        )

    paths = build_paths(root)
    return TargetRepoContext(
        root=root,
        workflow_dir=paths.workflow_dir,
        probe_dir=paths.probe_dir,
        config_path=paths.config,
        state_path=paths.state,
        run_manifest_path=paths.run_manifest,
        git_root=root if is_git_repo else None,
        is_git_repo=is_git_repo,
        allow_non_git=allow_non_git,
        allow_self_target=allow_self_target,
        paths=paths,
    )
