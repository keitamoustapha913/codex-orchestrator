"""Entry point for the one-shot report reorganization subprocess."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .report_reorganization import reorganize_report


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) != 5:
        return 2
    raw_path, output_dir, source_hash, patchlet_id, attempt_id = args
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    reorganize_report(raw, source_report_sha256=source_hash, patchlet_id=patchlet_id,
        attempt_id=attempt_id, source_report_version=str(raw.get("schema_version", "")),
        output_dir=Path(output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
