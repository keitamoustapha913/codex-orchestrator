# Installation

Local baseline: `uv + Python 3.10`.

```bash
cd codex-orchestrator
uv venv --python 3.10
. .venv/bin/activate
uv pip install -e ".[dev]"
uv run pytest -q
```

After installation:

```bash
uv run cxor --version
uv run codex-orchestrator --version
uv run python -m codex_orchestrator --version
```

Typical mock workflow:

```bash
uv run --no-sync cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock
```

Optional worktree-safe execution:

```bash
uv run --no-sync cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
```
