from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


os.environ.setdefault("CXOR_PLANNING_MODEL_STUB", "1")


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-real-codex",
        action="store_true",
        default=False,
        help="Run opt-in smoke tests that invoke the installed codex binary.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_codex: opt-in smoke tests that invoke the installed codex binary",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-real-codex"):
        return
    skip_real_codex = pytest.mark.skip(reason="requires --run-real-codex")
    for item in items:
        if "real_codex" in item.keywords:
            item.add_marker(skip_real_codex)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    run(["git", "init"], repo)
    run(["git", "config", "user.email", "test@example.com"], repo)
    run(["git", "config", "user.name", "Test User"], repo)
    (repo / "app.py").write_text("def main():\n    return 'ok'\n", encoding="utf-8")
    (repo / "master_prompt.md").write_text("Make app return ok and prove it.\n", encoding="utf-8")
    run(["git", "add", "app.py", "master_prompt.md"], repo)
    run(["git", "commit", "-m", "initial"], repo)
    return repo


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
