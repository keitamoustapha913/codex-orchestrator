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
cxor verify-global
cxor classify-failures
cxor plan-repair
cxor apply-repair
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
