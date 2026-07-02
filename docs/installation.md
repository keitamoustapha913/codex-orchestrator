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
