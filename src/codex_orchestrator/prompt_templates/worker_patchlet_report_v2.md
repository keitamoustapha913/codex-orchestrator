# WorkerPatchletReportV2 report contract

Contract fingerprint: `6a53c97f66455f215540798f3b117c4cb15d024ffbc00b7108dd19c1694a68f5`

Emit these fields only as evidence; the orchestrator owns acceptance:
- `schema_version` (string): WorkerPatchletReportV2 version.
- `kind` (string): Canonical worker report kind.
- `patchlet_id` (string): Orchestrator-assigned patchlet identity.
- `status` (string): Worker lifecycle status; not proof.
- `changed_product_runtime_file` (['string', 'null']): Reported product file; boundary gates remain authoritative.
- `changed_artifact_files` (array): Reported evidence artifacts.
- `probe_commands` (array): Worker-described probes; independent proof remains authoritative.
- `deterministic_run_counts` (object): Declared run counts; not independent proof.
- `root_cause_classification` (object): Structured worker diagnosis.
- `before_after_state` (array): Worker state observations.
- `row_ledger` (array): Worker evidence ledger.
- `trace_ledger` (array): Worker trace ledger.
- `cleanup_proof` (string): Worker cleanup observation; hygiene gates remain authoritative.
- `probe_artifact_refs` (array): References to evidence under approved probe roots.
- `semantic_goal_results` (array): Worker semantic observations pending independent proof.
- `blocking_boundary_reason` (string): Worker description of the current blocking boundary.
- `failed_probe_evidence` (string): Worker description of failed probe evidence.

Semantic shorthand entries use exactly these fields: `goal_item_id`, `result`.

Report path fields are bounded logical references, never absolute filesystem paths.
Use `.artifacts/probes/<patchlet-id>/...` for `changed_artifact_files`, `probe_root`, and file `path` values. Never copy `$CXOR_WORKER_EVIDENCE_DIR`, `/tmp/...`, `~`, `..`, or sandbox paths into the report.

Unknown fields are preserved as non-authoritative warnings.
