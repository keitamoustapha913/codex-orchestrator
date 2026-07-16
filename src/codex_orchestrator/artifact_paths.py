from __future__ import annotations

from pathlib import Path

from codex_orchestrator.errors import ValidationError


def resolve_artifact_write_path(
    *, owning_root: Path, artifact_reference: str | Path, file_required: bool = True
) -> Path:
    """Resolve a portable artifact reference to a contained filesystem path."""
    root = Path(owning_root)
    if not root.is_absolute():
        raise ValidationError(f"artifact owning root must be absolute: {root}")
    root = root.resolve(strict=False)

    reference = Path(artifact_reference)
    candidate = reference if reference.is_absolute() else root / reference
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValidationError(
            f"artifact path escapes owning root: {artifact_reference}"
        ) from exc
    if file_required and resolved == root:
        raise ValidationError("artifact path must identify a file beneath the owning root")
    return resolved
