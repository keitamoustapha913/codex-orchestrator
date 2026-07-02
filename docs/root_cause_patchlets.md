# Root-Cause Patchlets

Patchlets are generated with the contractual gate:

`ROOT-CAUSE PROBE-ONLY INVESTIGATION`

Successful reports must carry durable probe artifacts and `probe_artifact_refs`.

Expected durable probe artifacts live under:

```text
.artifacts/probes/<PATCHLET_ID>/
.artifacts/probes/<PATCHLET_ID>/run_001/row_ledger.jsonl
.artifacts/probes/<PATCHLET_ID>/run_001/trace_ledger.jsonl
.artifacts/probes/<PATCHLET_ID>/run_001/before_state.json
.artifacts/probes/<PATCHLET_ID>/run_001/after_state.json
.artifacts/probes/<PATCHLET_ID>/run_001/cleanup_proof.json
```

No blind retry is allowed.
