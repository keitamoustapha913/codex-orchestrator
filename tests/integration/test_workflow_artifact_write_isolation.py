from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from codex_orchestrator.errors import ValidationError
from codex_orchestrator.stages.run_patchlet import _rewrite_target_hygiene_result


def _ctx(root: Path):
    return SimpleNamespace(root=root)


def _result(reference: str):
    return {"kind": "target_hygiene_gate_result", "result_path": reference, "candidate_scope": "clean_reconstruction"}


def test_candidate_hygiene_rewrite_uses_target_repository_root(tmp_path: Path):
    target = tmp_path / "target"
    payload = _result(".codex-orchestrator/runs/P0001_attempt1/gates/target_hygiene_gate_result.json")
    _rewrite_target_hygiene_result(_ctx(target), payload)
    assert (target / payload["result_path"]).exists()


def test_candidate_hygiene_rewrite_does_not_use_process_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "target"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    payload = _result(".codex-orchestrator/runs/P0001_attempt4/gates/result.json")
    _rewrite_target_hygiene_result(_ctx(target), payload)
    assert (target / payload["result_path"]).exists()
    assert not (cwd / payload["result_path"]).exists()


def test_artifact_reference_remains_repository_relative(tmp_path: Path):
    payload = _result(".codex-orchestrator/runs/P0002_attempt1/gates/result.json")
    _rewrite_target_hygiene_result(_ctx(tmp_path / "target"), payload)
    assert not Path(payload["result_path"]).is_absolute()


def test_absolute_target_artifact_path_is_accepted(tmp_path: Path):
    target = tmp_path / "target"
    absolute = target / ".codex-orchestrator/result.json"
    _rewrite_target_hygiene_result(_ctx(target), _result(str(absolute)))
    assert absolute.exists()


def test_absolute_cross_repository_path_is_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        _rewrite_target_hygiene_result(_ctx(tmp_path / "target"), _result(str(tmp_path / "other/result.json")))


def test_parent_traversal_reference_is_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        _rewrite_target_hygiene_result(_ctx(tmp_path / "target"), _result("../outside.json"))


def test_symlink_escape_is_rejected(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (target / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValidationError):
        _rewrite_target_hygiene_result(_ctx(target), _result("link/result.json"))


def test_orchestrator_repository_remains_clean_after_run_next_patchlet(tmp_path: Path):
    target = tmp_path / "target"
    payload = _result(".codex-orchestrator/runs/P0001_attempt1/gates/result.json")
    _rewrite_target_hygiene_result(_ctx(target), payload)
    assert not (Path.cwd() / ".codex-orchestrator").exists()


def test_apply_results_helper_writes_only_under_tmp_target(tmp_path: Path):
    target = tmp_path / "target"
    payload = _result(".codex-orchestrator/runs/P0001_attempt1/gates/result.json")
    _rewrite_target_hygiene_result(_ctx(target), payload)
    assert (target / payload["result_path"]).read_text(encoding="utf-8")


def test_multiple_attempt_ids_do_not_leak_to_process_cwd(tmp_path: Path):
    target = tmp_path / "target"
    for attempt in ("P0001_attempt1", "P0001_attempt4", "P0002_attempt1"):
        payload = _result(f".codex-orchestrator/runs/{attempt}/gates/result.json")
        _rewrite_target_hygiene_result(_ctx(target), payload)
    assert not (Path.cwd() / ".codex-orchestrator").exists()
