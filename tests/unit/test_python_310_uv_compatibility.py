from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_python_version_file_pins_310() -> None:
    python_version = REPO_ROOT / ".python-version"

    assert python_version.exists()
    assert python_version.read_text(encoding="utf-8") == "3.10\n"


def test_pyproject_declares_python_310_compatibility() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.10"' in pyproject
    assert 'requires-python = ">=3.11"' not in pyproject


def test_source_avoids_known_python_311_only_stdlib_features() -> None:
    forbidden_patterns = [
        "import tomllib",
        "from tomllib import",
        "typing.Self",
        "from typing import Self",
        "ExceptionGroup",
    ]

    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        content = path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            assert pattern not in content, f"{path} contains forbidden Python 3.11-only pattern: {pattern}"
