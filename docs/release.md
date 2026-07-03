# Release checklist

Use this checklist before tagging a release candidate.

Normal deterministic command:

```bash
cxor auto --repo <repo> --master <prompt> --until DONE
```

mock mode is deterministic and CI-safe:

```bash
uv run --no-sync pytest -q
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
```

The default suite and default smoke check do not run real Codex. real Codex is
opt-in only.

Version and packaging checks:

```bash
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
```

Integration safety checks:

```bash
cxor validate-integration-artifacts --repo <repo>
```

The integration ref keeps the target clean between patchlets. Accepted patchlet
changes advance `refs/cxor/runs/<run_id>/integration`; target product/runtime
files are not dirtied between accepted patchlets.

apply-results is explicit finalization:

```bash
cxor apply-results --repo <repo> --mode patch
cxor apply-results --repo <repo> --mode branch
cxor apply-results --repo <repo> --mode working-tree
```

Patch mode writes a final diff without mutating product files. Branch mode
creates a result branch without checkout. Working-tree mode requires a clean
target and mutates only after explicit operator request.

Operator-run real-Codex evidence flow:

```bash
cxor real-codex-smoke-runbook --dry-run
cxor validate-real-codex-smoke-runbook --run-dir <bundle>
cxor list-real-codex-smoke-runbooks
cxor export-real-codex-smoke-runbook --run-dir <bundle>
```

`cxor export-real-codex-smoke-runbook --run-dir <bundle>` packages one
validated bundle into `.operator-runs/exports/<bundle>.zip` and writes a
sidecar `.manifest.json` containing relative file paths, sizes, and sha256
hashes. Invalid bundles are refused unless `--force` is provided. The export
command is read-only for the source bundle, does not run Codex, and does not
run pytest.

Live real-Codex release evidence is operator-gated:

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor real-codex-smoke-runbook --run-real-codex --live-progress

uv run --no-sync cxor list-real-codex-smoke-runbooks --latest --json
uv run --no-sync cxor validate-real-codex-smoke-runbook --run-dir <latest_bundle>
uv run --no-sync cxor export-real-codex-smoke-runbook --run-dir <latest_bundle>
```

`safe_failure` is evidence capture, not DONE. DONE means the orchestrator
validators accepted the run.
