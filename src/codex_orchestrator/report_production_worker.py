"""Entry point for the constrained one-shot report-production worker."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from .report_production import produce_report


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) != 2:
        return 2
    inputs = Path(args[0])
    output_dir = Path(args[1])
    produce_report(
        json.loads((inputs / "task_completion_handoff.json").read_text(encoding="utf-8")),
        json.loads((inputs / "report_production_context.json").read_text(encoding="utf-8")),
        json.loads((inputs / "worker_evidence_inventory.json").read_text(encoding="utf-8")),
        json.loads((inputs / "worker_evidence_preservation_result.json").read_text(encoding="utf-8")),
        output_dir=output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
