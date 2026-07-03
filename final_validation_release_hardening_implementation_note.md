Preflight Findings

- Baseline deterministic suite passed before implementation.
- Current repository started clean at the new release-hardening HEAD.
- `codex` is installed locally, but live real-Codex execution is not approved by policy for this prompt.

Current Test Baseline

- Full suite: 673 passed, 2 skipped.
- Python: 3.10.20.
- uv workflow is available.

Current Git Status

- Clean at preflight start.

Current Operator Runbook Capabilities

- Dry-run and explicit runbook commands exist.
- Runbook bundles include raw stdout/stderr, selected policy, result, diagnosis paths, and validation result.

Current Bundle Validation Capabilities

- `cxor validate-real-codex-smoke-runbook --run-dir <bundle>` validates one bundle without running Codex or pytest.

Current Bundle Listing Capabilities

- `cxor list-real-codex-smoke-runbooks` summarizes local bundles and handles malformed bundles.

Current Integration Artifact Validation Capabilities

- `cxor validate-integration-artifacts --repo <repo>` validates integration state, accepted changes, checkpoints, apply-results artifacts, and final diff requirements.

Current Integration Ref Behavior

- Accepted patchlets advance a hidden `refs/cxor/runs/<run_id>/integration` ref.
- Target product/runtime files remain clean between patchlets.

Current apply-results Behavior

- Patch mode writes final diff without mutating product files.
- Branch mode creates a result branch without checkout.
- Working-tree mode requires a clean target and then applies the final diff.

Current Mock Autonomous Matrix Coverage

- Existing deterministic tests cover mock auto DONE, repair replay, rediscovery, integration ref updates, and apply-results modes.
- This increment adds a tiny DONE fixture tying auto, final verification, integration validation, and apply-results together.

Current CI/Release Commands

- Deterministic release checks remain command-based and do not run real Codex.

Current Packaging/Install Behavior

- Version commands work through module and installed entry points.
- Existing tests cover CLI execution from outside the repository with `--repo`.

Live Real-Codex Run Policy

- Live real-Codex smoke is not run unless explicitly approved.
- This increment records the exact operator command sequence instead.

Implementation Phase Order

- Add export command and tests.
- Add deterministic tiny DONE fixture.
- Update release docs and implementation status.
- Run default smoke skip and full deterministic verification.

Risks and Stop Conditions

- Stop if export mutates source bundles, invokes Codex or pytest, archives unsafe paths, or permits invalid bundles without `--force`.
