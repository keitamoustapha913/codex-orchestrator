# Autonomous Loop

Local baseline: `uv + Python 3.10`.

Primary autonomous command:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
```

The autonomous loop is probe-gated and evidence-bound:

`normalize -> census -> classify-evidence -> build-inventory -> extract-invariants -> compile-patchlets -> run patchlets -> transaction groups -> verify-global -> DONE`

If failures occur, the loop routes through:

`failure -> classification -> repair plan -> apply repair -> regenerate patchlets -> verify`

For advanced cases it can also route through:

`PARTIAL_REDISCOVERY_REQUIRED`
`FULL_REDISCOVERY_REQUIRED`
`INVENTORY_REBUILD_REQUIRED`

No blind retry is allowed.

`ci_only` mode is read-only and intended for CI-safe resume and verification flows:

```bash
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode ci_only
```

`--use-worktree` is optional, not default. When enabled for patchlet-executing worker modes, the target repo must be clean apart from volatile workflow artifacts before worktree execution starts.
