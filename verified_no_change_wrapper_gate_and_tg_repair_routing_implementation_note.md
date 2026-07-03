# Verified-No-Change Wrapper Gate and TG Repair Routing Implementation Note

## Preflight Findings

Baseline was `758 passed, 2 skipped` before this increment. The repo contains uncommitted changes from the prior report-contract hardening increment; they are preserved and not reverted.

## Latest Live Run Evidence

Latest bundle: `.operator-runs/real-codex-smoke/2026-07-03T15-05-27-real-codex-smoke`. The bundle validates and exports.

## Observed Final Report Markdown

The final report contained `Marker: \`FINAL_STATUS: PASS\`` instead of a standalone `FINAL_STATUS: PASS` line.

## Observed Wrapper Gate Result

`wrapper_gate_result.json` recorded `accepted=false`, `final_status_gate=missing`, and reason `missing worker_stage/05_final_report.md FINAL_STATUS marker`.

## Observed Transaction Group Result

`TG001` failed because `P0001` had `wrapper_gate_not_accepted`.

## Observed Failure Record Shape

The failure record used `source_id=TG001` but did not include `source_type`, `source_transaction_group_id`, or `source_patchlet_ids`.

## Observed Repair Plan Shape

The repair plan referenced `source_failure_ids=["F0001"]`.

## Observed Regeneration Failure

`regenerate-patchlets` read `F0001.source_id=TG001` and tried to find a patchlet manifest named `TG001`, producing `missing source patchlet manifest for TG001`.

## Current Marker Contract

The wrapper gate currently requires a line that starts with `FINAL_STATUS:`. The existing prompt did not make the standalone column-one line sufficiently explicit.

## Current Wrapper Gate Parser Behavior

The parser returns only a stripped value for a line that starts exactly with `FINAL_STATUS:`. It does not distinguish missing, non-canonical, or invalid marker values.

## Current Transaction Group Failure Semantics

Transaction group failures are legitimate and use transaction group ids such as `TG001`, but the failure record does not preserve source type or member patchlet ids.

## Current Regenerate-Patchlets Source Resolution

Regeneration assumes every failure `source_id` is a patchlet id.

## Current Diagnosis Precedence

Structured wrapper-gate and routing evidence does not outrank broad network/API text. Stage precondition errors fall through to generic output classification.

## Chosen Contract Decision

A successful worker final report must contain a canonical final-status marker as a standalone line.

Accepted canonical lines:

```text
FINAL_STATUS: PASS
FINAL_STATUS: BLOCKED
FINAL_STATUS: FAILED
```

Non-canonical examples rejected with precise evidence:

```text
Marker: `FINAL_STATUS: PASS`
`FINAL_STATUS: PASS`
The marker is FINAL_STATUS: PASS
FINAL_STATUS PASS
```

`FINAL_STATUS: OK` and `FINAL_STATUS: SUCCESS` are invalid values.

The wrapper gate remains strict. Non-canonical text does not pass as success. Prompts and Worker Capsule artifacts must make the exact required line unambiguous. Transaction group failures keep transaction group identity and member patchlet ids. Regeneration resolves source failures by source type and never treats `TG001` as a patchlet id.

## Implementation Phase Order

1. Add final report contract artifact and prompt references.
2. Add precise wrapper gate marker classification.
3. Add diagnosis categories for wrapper gate, transaction-group routing, and stage preconditions.
4. Add transaction-group failure source modeling.
5. Add regenerate-patchlets source resolution for transaction groups.
6. Add full-chain fake-Codex reproduction and canonical happy path.
7. Update docs and run final verification.

## Risks and Stop Conditions

Do not accept non-canonical markers as success. Do not hide wrapper gate failure. Do not treat `TG001` as a patchlet id. Do not let network/API classification mask structured gate or routing evidence. Do not run real Codex in default tests.
