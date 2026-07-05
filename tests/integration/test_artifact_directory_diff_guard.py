from __future__ import annotations

from codex_orchestrator.validators.diff_validator import validate_changed_paths


def _patchlet() -> dict:
    return {
        "patchlet_id": "P0001",
        "allowed_product_runtime_file": "service.cfg",
        "allowed_artifact_dirs": [
            ".artifacts/probes/",
            ".codex-orchestrator/reports/",
            ".codex-orchestrator/runs/",
        ],
    }


def test_execution_root_artifact_directory_reported_by_git_is_allowed():
    result = validate_changed_paths([".artifacts"], _patchlet())
    assert result.allowed is True
    assert result.artifact_paths == [".artifacts"]


def test_artifact_directory_granularity_expands_to_allowed_artifact_files():
    result = validate_changed_paths([".artifacts/probes"], _patchlet())
    assert result.allowed is True
    assert result.path_classifications[".artifacts/probes"] == "ARTIFACT_ALLOWED"


def test_product_directory_reported_by_git_is_not_allowed():
    result = validate_changed_paths(["src"], _patchlet())
    assert result.allowed is False
    assert "src" in result.unauthorized_paths


def test_allowed_artifact_roots_do_not_permit_product_runtime_files():
    result = validate_changed_paths(["service.cfg"], _patchlet())
    assert result.allowed is True
    assert result.product_runtime_paths == ["service.cfg"]


def test_worktree_execution_artifact_dirs_are_authorized():
    patchlet = _patchlet() | {"recorded_execution_artifact_roots": [".codex-orchestrator/runs/P0001_attempt1"]}
    result = validate_changed_paths([".codex-orchestrator/runs/P0001_attempt1"], patchlet)
    assert result.allowed is True


def test_artifact_dir_allowance_preserves_one_product_file_rule():
    result = validate_changed_paths([".artifacts", "other.cfg"], _patchlet())
    assert result.allowed is False
    assert "other.cfg" in result.unauthorized_paths


def test_scratch_quarantine_does_not_allow_new_product_directory():
    result = validate_changed_paths(["runtime"], _patchlet())
    assert result.allowed is False
    assert "runtime" in result.unauthorized_paths


def test_scratch_quarantine_does_not_allow_second_product_file():
    result = validate_changed_paths(["service.cfg", "other.cfg"], _patchlet())
    assert result.allowed is False
    assert "other.cfg" in result.unauthorized_paths


def test_patchlet_report_pretty_quarantine_does_not_allow_second_product_file():
    result = validate_changed_paths(["service.cfg", "peer.record"], _patchlet())

    assert result.allowed is False
    assert "peer.record" in result.unauthorized_paths


def test_patchlet_report_pretty_quarantine_does_not_allow_product_directory():
    result = validate_changed_paths(["service.cfg", "runtime"], _patchlet())

    assert result.allowed is False
    assert "runtime" in result.unauthorized_paths


def test_patchlet_report_pretty_quarantine_preserves_one_file_rule():
    result = validate_changed_paths(["service.cfg", "policy.bundle"], _patchlet())

    assert result.allowed is False
    assert "service.cfg" in result.product_runtime_paths
    assert "policy.bundle" in result.unauthorized_paths


def test_patchlet_report_pretty_quarantine_preserves_slice_boundary():
    patchlet = _patchlet() | {
        "slice_change_boundary": {
            "allowed_changes": [
                {"file": "service.cfg", "key": "status", "old_value": "pending", "new_value": "ready"}
            ],
            "forbidden_changes": [
                {"file": "service.cfg", "key": "mode", "old_value": "permissive", "new_value": "strict"}
            ],
        }
    }
    diff_text = """diff --git a/service.cfg b/service.cfg
--- a/service.cfg
+++ b/service.cfg
@@ -1,2 +1,2 @@
-status=pending
+status=ready
-mode=permissive
+mode=strict
"""

    result = validate_changed_paths(["service.cfg"], patchlet, diff_text=diff_text)

    assert result.allowed is False
    assert result.slice_boundary_violations
