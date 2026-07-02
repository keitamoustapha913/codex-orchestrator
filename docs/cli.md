# CLI

Primary MVP command:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock
```

Stage commands implemented:

```bash
cxor init
cxor status
cxor validate-state
cxor census
cxor normalize
cxor classify-evidence
cxor build-inventory
cxor extract-invariants
cxor compile-patchlets
cxor run-next
cxor run-all
cxor validate-report
cxor verify-group
cxor verify-all-groups
cxor verify-global
cxor classify-failures
cxor plan-repair
cxor apply-repair
cxor rediscover
cxor rebuild-inventory
cxor regenerate-patchlets
cxor auto
```

Repair loop:
`failure -> classification -> repair plan -> apply repair -> regenerate patchlets -> verify`

No blind retry. Use:

```bash
cxor apply-repair --repo /path/to/target-repo
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest
```

These repair replay commands are idempotent when the corresponding durable artifacts already exist:

```bash
cxor apply-repair --repo /path/to/target-repo
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode mock
```

If the workflow is already `DONE`, `cxor apply-repair` and `cxor regenerate-patchlets` become terminal no-op commands. They exit successfully, report the no-op, and leave state, patchlet index, final verification, and product/runtime files unchanged.

Durable probe artifacts and `probe_artifact_refs` are required for successful patchlet reports.

Transaction group and global verification commands:

```bash
cxor verify-group --repo /path/to/target-repo TG001
cxor verify-all-groups --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo
```

Advanced repair and rediscovery commands:

```bash
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rediscover --repo /path/to/target-repo --scope full
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
```

Optional worktree execution with validated merge:

```bash
cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
```

Worktree mode is optional, not default. It requires a clean target repo apart from volatile workflow artifacts and isolates unauthorized diffs before any target product/runtime merge.

CI-friendly commands that exist:

```bash
cxor doctor --repo /path/to/target-repo
cxor validate-state --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode ci_only
```
