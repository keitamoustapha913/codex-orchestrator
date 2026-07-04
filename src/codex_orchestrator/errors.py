from __future__ import annotations


class CxorError(Exception):
    """Base exception for user-facing orchestrator errors."""


class TargetRepoError(CxorError):
    """Raised when target repository resolution or validation fails."""


class StateError(CxorError):
    """Raised when workflow state is missing, invalid, or cannot transition."""


class ValidationError(CxorError):
    """Raised by validators when an artifact violates policy."""


class CommandExecutionError(CxorError):
    """Raised when a required subprocess command fails."""


class StagePreconditionError(CxorError):
    """Raised when a workflow stage is called in the wrong state or without required artifacts."""

    def __init__(self, operation: str, *, current_stage: str, target_repo: str, detail: str) -> None:
        self.operation = operation
        self.current_stage = current_stage
        self.target_repo = target_repo
        self.detail = detail
        super().__init__(
            f"precondition failed for {operation}: {detail}; "
            f"current stage={current_stage}; target repo={target_repo}"
        )


class WorkerPreconditionError(CxorError):
    """Raised when a worker cannot start because a required binary or artifact is missing."""


class WorkerExecutionError(CxorError):
    """Raised when a worker starts but fails to produce a valid execution result."""


class WorkerTimeoutError(WorkerExecutionError):
    """Raised when the orchestrator terminates a worker after its wall-clock budget."""


class WorkerInterruptedError(WorkerExecutionError):
    """Raised when a worker attempt is interrupted and evidence has been preserved."""
