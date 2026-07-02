# Transaction Groups

Transaction groups prove that one-file patchlets can still satisfy larger invariant-level workflows.

Commands:

```bash
cxor verify-group --repo /path/to/target-repo TG001
cxor verify-all-groups --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo
```

`DONE` is blocked until required transaction groups pass.
## Transaction Output Matrix

Before a transaction group is accepted, the verifier writes:

- `.codex-orchestrator/transaction_groups/<group>/patchlet_output_matrix.json`
- `.codex-orchestrator/transaction_groups/<group>/gates/group_gate_result.json`

`patchlet_output_matrix.json` cross-checks each patchlet report, durable probe
artifacts, allowed diff result, and wrapper gate acceptance. Contradictions in
that matrix block the group verdict.

`verify-group` writes the matrix first and then writes
`gates/group_gate_result.json` as the machine verdict for the transaction
group.
