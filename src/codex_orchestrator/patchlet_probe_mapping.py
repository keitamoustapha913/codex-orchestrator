from __future__ import annotations

from typing import Any


MISSING_PATCHLET_PROBE_MAPPING = "MISSING_PATCHLET_PROBE_MAPPING"


class PatchletProbeMappingError(ValueError):
    """A patchlet cannot be compiled without a deterministic probe mapping."""

    def __init__(self, *, patchlet: dict[str, Any], supplied: Any, candidates: list[str], reason: str) -> None:
        self.details = {
            "failure_signature": MISSING_PATCHLET_PROBE_MAPPING,
            "patchlet_id": patchlet.get("patchlet_id"),
            "goal_item_ids": list(patchlet.get("goal_item_ids") or []),
            "proof_obligation_ids": list(patchlet.get("proof_obligation_ids") or []),
            "supplied_probe_ids": supplied,
            "derived_probe_candidates": list(candidates),
            "reason": reason,
        }
        super().__init__(f"{MISSING_PATCHLET_PROBE_MAPPING}: {reason} for {patchlet.get('patchlet_id')}")


def _valid_probe_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and item.strip()})


def _boundary_probe_candidates(patchlet: dict[str, Any]) -> list[list[str]]:
    boundaries: list[list[str]] = []
    current = patchlet.get("current_slice_boundary")
    if isinstance(current, dict) and "probe_ids" in current:
        boundaries.append(_valid_probe_ids(current.get("probe_ids")))
    change_boundary = patchlet.get("slice_change_boundary")
    if isinstance(change_boundary, dict):
        current = change_boundary.get("current_boundary")
        if isinstance(current, dict) and "probe_ids" in current:
            boundaries.append(_valid_probe_ids(current.get("probe_ids")))
        elif "probe_ids" in change_boundary:
            boundaries.append(_valid_probe_ids(change_boundary.get("probe_ids")))
    return boundaries


def _probe_ids_by_obligation(probe_plan: dict[str, Any] | None) -> dict[str, list[str]]:
    result: dict[str, set[str]] = {}
    for probe in (probe_plan or {}).get("probes", []):
        probe_id = probe.get("probe_id")
        if not isinstance(probe_id, str) or not probe_id.strip():
            continue
        for obligation_id in probe.get("obligation_ids", []):
            result.setdefault(str(obligation_id), set()).add(probe_id)
    return {key: sorted(value) for key, value in result.items()}


def resolve_patchlet_probe_ids(
    patchlet: dict[str, Any],
    *,
    probe_plan: dict[str, Any] | None = None,
) -> list[str]:
    """Return only explicitly or unambiguously mapped probe IDs."""
    if "probe_ids" in patchlet:
        supplied = patchlet.get("probe_ids")
        probe_ids = _valid_probe_ids(supplied)
        if not probe_ids:
            raise PatchletProbeMappingError(
                patchlet=patchlet,
                supplied=supplied,
                candidates=[],
                reason="probe_ids was explicitly supplied as empty or invalid",
            )
        if not isinstance(supplied, list) or len(probe_ids) != len(supplied):
            raise PatchletProbeMappingError(
                patchlet=patchlet,
                supplied=supplied,
                candidates=probe_ids,
                reason="probe_ids contains invalid or duplicate values",
            )
        return probe_ids

    boundary_candidates = _boundary_probe_candidates(patchlet)
    non_empty = [candidate for candidate in boundary_candidates if candidate]
    if non_empty:
        candidates = sorted({probe_id for row in non_empty for probe_id in row})
        if len(non_empty) == len(boundary_candidates) and all(row == candidates for row in non_empty):
            return candidates
        raise PatchletProbeMappingError(
            patchlet=patchlet,
            supplied=None,
            candidates=candidates,
            reason="explicit boundary probe mappings are empty or contradictory",
        )

    by_obligation = _probe_ids_by_obligation(probe_plan)
    derived: set[str] = set()
    for obligation_id in patchlet.get("proof_obligation_ids") or []:
        mapped = by_obligation.get(str(obligation_id), [])
        if len(mapped) != 1:
            raise PatchletProbeMappingError(
                patchlet=patchlet,
                supplied=None,
                candidates=sorted(derived | set(mapped)),
                reason=f"proof obligation {obligation_id} resolves to {len(mapped)} probes",
            )
        derived.add(mapped[0])
    if not derived:
        raise PatchletProbeMappingError(
            patchlet=patchlet,
            supplied=None,
            candidates=[],
            reason="no explicit goal/obligation/probe mapping resolved",
        )
    return sorted(derived)
