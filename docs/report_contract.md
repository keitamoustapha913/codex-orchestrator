# Real-Codex Report Contract

Canonical patchlet reports must keep `probe_artifact_refs` as object entries.
Raw real-Codex reports may contain string paths only as worker output before
report ingestion. String paths are never canonical report truth.

Report declarations do not expand product ownership. Every write-capable
worker runs in a disposable sandbox, and the deterministic allowlist is the
only product boundary. All in-sandbox non-allowlisted outputs are sandbox
debris. Sandbox debris never blocks promotion and a report reference cannot
make debris part of the canonical patch. Containment escape remains blocking.

## Canonical Probe References

Invalid canonical report shape:

```json
{
  "probe_artifact_refs": [
    ".artifacts/probes/P0002/comparison.txt"
  ]
}
```

Valid canonical report shape:

```json
{
  "probe_artifact_refs": [
    {
      "patchlet_id": "P0002",
      "probe_root": ".artifacts/probes/P0002",
      "run_id": "default",
      "files": [
        {
          "path": ".artifacts/probes/P0002/comparison.txt",
          "kind": "comparison",
          "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
          "size_bytes": 123
        }
      ]
    }
  ]
}
```

Nested probe runs use the nested directory as `run_id`:

```json
{
  "patchlet_id": "P0001",
  "probe_root": ".artifacts/probes/P0001/run_001",
  "run_id": "run_001",
  "files": [
    {
      "path": ".artifacts/probes/P0001/run_001/before_state.json",
      "kind": "before_state",
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "size_bytes": 123
    }
  ]
}
```

Canonical V2 reports may include `files` metadata. When present, the validator
checks path, kind, sha256, and size. File paths must remain under
`.artifacts/probes/<patchlet_id>/`.

## Report Ingestion

The report-ingress layer preserves raw worker output at
`.codex-orchestrator/reports/<PATCHLET_ID>.raw.json` and writes the canonical
candidate at `.codex-orchestrator/reports/<PATCHLET_ID>.json`.

Safe string refs are normalized only during ingress. They must exist, resolve
inside the target repository, stay under `.artifacts/probes/`, match the
current patchlet id, and avoid symlink escapes. Unsafe refs, missing files,
product/runtime paths, and paths outside `.artifacts/probes/` fail with
structured evidence instead of being accepted.

Ingress writes:

- `.codex-orchestrator/runs/<ATTEMPT_ID>/gates/report_ingestion_result.json`
- `.codex-orchestrator/runs/<ATTEMPT_ID>/gates/report_validation_errors.json`

Structured validation errors include JSON pointer, schema path, field,
expected type, actual type, invalid value excerpt, normalized signature, repair
hint, and a canonical example. The signature for string refs where objects are
required is `probe_artifact_refs_not_objects`; this class should not appear as
`unknown_repeated_failure`.

## Repair Routing

Report-shape-only failures do not mean the product/runtime change failed.
Deterministic normalization is attempted first. Report-only repair policy may
rewrite only the report JSON shape and must not edit product/runtime files or
probe evidence. Full patchlet repair remains available for true product
failures, worker timeouts, target hygiene failures, or invalid generated
evidence.

Repeated report-shape failures are surfaced to the loop governor with specific
signatures such as `probe_artifact_refs_not_objects`. Safe-failure mode
preserves evidence instead of blindly regenerating patchlets.

## Operator Visibility

Direct `cxor auto --live-progress`, `cxor monitor`, and `cxor status --json`
surface report ingestion outcomes. Compact progress can show:

```text
[cxor +118s] report ingestion P0002 normalized 2 probe artifact path refs.
[cxor +119s] report P0002 valid after canonicalization.
```

Compact progress does not print raw report bodies or prompt bodies. Use
`cxor prompts --repo <repo> --show PR000001 --lines 160` when a prompt body is
explicitly needed.
