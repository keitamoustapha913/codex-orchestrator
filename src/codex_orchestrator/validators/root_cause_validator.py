from __future__ import annotations

from .report_validator import validate_patchlet_report


def validate_root_cause_contract(report: dict, patchlet: dict | None = None) -> None:
    validate_patchlet_report(report, patchlet)
