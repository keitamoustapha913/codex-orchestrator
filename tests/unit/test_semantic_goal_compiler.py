from __future__ import annotations

from pathlib import Path

from codex_orchestrator.semantic_goals import compile_semantic_goal_spec


def _expected(prompt: str):
    spec = compile_semantic_goal_spec(
        master_prompt_text=prompt,
        master_prompt_path=Path("master_prompt.md"),
        master_prompt_sha256="b" * 64,
        workflow_id=None,
        run_id=None,
    )
    return spec, spec["criteria"][0]["expected_value"] if spec["criteria"] else None


def test_compiles_make_app_return_me():
    assert _expected("Make app return me and prove it.")[1] == "me"


def test_compiles_make_app_return_ok():
    assert _expected("Make app return ok and prove it.")[1] == "ok"


def test_compiles_make_app_py_return_value():
    assert _expected("Make app.py return yes and prove it.")[1] == "yes"


def test_compiles_make_app_main_return_value():
    assert _expected("Make app.main() return no and prove it.")[1] == "no"


def test_compiles_quoted_string_value():
    assert _expected('Make app return "hello world" and prove it.')[1] == "hello world"


def test_compiler_is_case_insensitive():
    assert _expected("MAKE APP RETURN ME AND PROVE IT.")[1] == "ME"


def test_compiler_trims_final_period():
    assert _expected("Make app return me and prove it.")[1] == "me"


def test_compiler_rejects_ambiguous_prompt():
    spec, value = _expected("Make the project better.")
    assert value is None
    assert spec["semantic_mode"] == "unsupported"


def test_compiler_rejects_code_like_value():
    assert _expected("Make app return foo() and prove it.")[0]["semantic_mode"] == "unsupported"


def test_compiler_rejects_environment_secret_expression():
    assert _expected('Make app return os.environ["SECRET"] and prove it.')[0]["semantic_mode"] == "unsupported"


def test_compiler_outputs_unsupported_when_no_parser_matches():
    spec, _ = _expected("Fix the bug.")
    assert spec["semantic_mode"] == "unsupported"
    assert spec["unsupported_reasons"]


def test_compiler_includes_master_prompt_hash():
    spec, _ = _expected("Make app return me and prove it.")
    assert spec["source_master_prompt_sha256"] == "b" * 64


def test_compiler_includes_matched_text():
    spec, _ = _expected("Make app return me and prove it.")
    assert spec["criteria"][0]["source"]["matched_text"] == "Make app return me and prove it."
