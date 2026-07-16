# D8/D9 dependency and boundary evidence

## Dependency ownership

- `jsonschema` was already declared in `pyproject.toml` as a runtime dependency.
- No `uv.lock` existed at audit time; it is now generated and records the resolved dependency.
- Production code imports `jsonschema` only in the existing project-owned `validators/schema_validator.py` abstraction. D8/D9 modules do not import it directly.
- Tests consume the existing validator; they do not create a second schema-validation stack.
- Selected boundary: Outcome B. `jsonschema` is required by production schema validation, so the runtime declaration is constrained to `jsonschema>=4,<5`, locked with `uv lock`, and synchronized with `uv sync --dev`.
- Verification used `uv`, not global pip.

## D8/D9 implementation status

Implemented:

- typed `WorkerPatchletReportV2` boundary catalogue;
- immutable raw-report copy, SHA-256, byte size, and envelope metadata;
- strict UTF-8/object/size/depth/field/array and duplicate-key checks;
- unsafe-reference and excluded-debris rejection;
- one-shot subprocess launcher with disposable scratch inputs;
- three-file output allowlist and output-boundary enforcement;
- candidate, trace, and worker-result artifacts;
- source-hash and raw-field accounting checks;
- orchestrator-owned integrity metadata and unknown-field warnings;
- no report-only repair routing in the ingestion path.

Partial:

- generated contract renderers and drift tests now cover schema fields, required fields, prompts, examples, documentation, aliases, and fingerprints; the committed artifacts are checked against the renderers rather than generated automatically at package build time;
- the documented legacy adapter remains deliberately narrow and preserves the source extension.

Not implemented:

- a production LLM-backed reorganization prompt worker; the auxiliary worker is currently a bounded mechanical subprocess;
- the full five-patchlet P0005 workflow through independent proof, coverage, and durable promotion; exact P0005 ingestion identity is covered 5/5.

## Validation evidence

- Contract generation/drift, exact P0005, D8/D9 isolation, integrity, semantic-authority, repair-routing, promotion, and operator-visibility tests: `180 passed`.
- Complete deterministic suite: `2095 passed, 2 skipped` in `297.72s`.
- RC6M patch-only promotion and target-root isolation probe subset: `140 passed`.
- Workspace orchestrator root: absent.
- `git diff --check`: passed.
- No commit was created.
- Contract fingerprint: `b42361708e55cd934eb4445e35a927adddfd790a88b35789ab3dd06fcb5f4bc0`.
- `acceptance_criteria_result` ownership: current prompt drift plus stale example content. It is removed from the generated V2 prompt/example; V1 string compatibility remains, and V2 object values remain unrecognized warnings.
- Repository-wide `ruff check .` is not green because 46 findings span unrelated existing modules/tests; targeted D8/D9 Ruff checks pass.

The executable helper probe matrix completed 5/5 for safe unknown-field warning,
V2 no-reorganization classification, exact P0005 identity, source-hash mismatch,
contract-fingerprint mismatch, dropped/invented/changed value/type rejection,
output-boundary rejection, recursive-worker rejection, auxiliary timeout without
product/integration writes, and non-authority checks. These are boundary-level
probes, not five complete end-to-end promotion workflows.

The requested supervised JavaScript five-file canary was not run: the
repository provides an opt-in generic real-Codex smoke fixture, but no
five-file JavaScript canary target or runbook entry that exercises the new raw
report extension. Python qualification and multilingual validation were not
run.
