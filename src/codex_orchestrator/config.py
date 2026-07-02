from __future__ import annotations

from pathlib import Path

DEFAULT_TARGET_CONFIG = """[repo]
root = "."
name = "target-repo"

[artifacts]
workflow_dir = ".codex-orchestrator"
probe_dir = ".artifacts/probes"

[worker]
mode = "mock"
codex_binary = "codex"
default_model = "default"

[execution]
non_interactive = true
auto_repair = true
auto_replan = true
auto_rediscover = true
until = "DONE"
max_patchlet_attempts = 3
max_repair_cycles = 0

[git]
require_clean_start = false
use_worktrees = false
rollback_unauthorized_diffs = true
allow_self_target = false
allow_non_git = false

[commands]
test = ""
lint = ""
typecheck = ""
"""


def write_default_target_config(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_TARGET_CONFIG, encoding="utf-8")
