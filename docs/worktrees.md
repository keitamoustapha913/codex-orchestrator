# Worktrees

Worktree mode is optional. It is not the default.

Command:

```bash
cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
```

Safety contract:

- worktree execution requires a clean target repo apart from volatile workflow artifacts;
- reports, run records, and durable probe artifacts are written to the target repo artifact root;
- target product/runtime files are not mutated before diff validation and report validation pass;
- validated merge applies only the allowed product/runtime diff;
- unauthorized worktree diffs are isolated as failure evidence;
- no source is copied into the target repo;
- no blind retry is allowed.

This is a validated merge flow, not a default execution mode.
