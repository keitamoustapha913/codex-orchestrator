from __future__ import annotations

from codex_orchestrator.codex_model_profile import resolve_codex_model_profile


def test_patchlet_model_profile_defaults_to_gpt_5_4_mini():
    profile = resolve_codex_model_profile("patchlet", {})

    assert profile.model == "gpt-5.4-mini"


def test_orchestrator_model_profile_defaults_to_gpt_5_5():
    profile = resolve_codex_model_profile("orchestrator", {})

    assert profile.model == "gpt-5.5"


def test_group_model_profile_defaults_to_gpt_5_5():
    profile = resolve_codex_model_profile("group", {})

    assert profile.model == "gpt-5.5"


def test_transaction_model_profile_defaults_to_gpt_5_5():
    profile = resolve_codex_model_profile("transaction", {})

    assert profile.model == "gpt-5.5"


def test_global_model_profile_defaults_to_gpt_5_5():
    profile = resolve_codex_model_profile("global", {})

    assert profile.model == "gpt-5.5"


def test_global_codex_model_env_overrides_both_profiles_when_specific_env_absent():
    env = {"CODEX_MODEL": "global-model"}

    assert resolve_codex_model_profile("patchlet", env).model == "global-model"
    assert resolve_codex_model_profile("orchestrator", env).model == "global-model"


def test_patchlet_specific_model_env_overrides_global_env():
    env = {"CODEX_MODEL": "global-model", "CODEX_PATCHLET_MODEL": "patchlet-model"}

    assert resolve_codex_model_profile("patchlet", env).model == "patchlet-model"


def test_orchestrator_specific_model_env_overrides_global_env():
    env = {"CODEX_MODEL": "global-model", "CODEX_ORCHESTRATOR_MODEL": "orchestrator-model"}

    assert resolve_codex_model_profile("orchestrator", env).model == "orchestrator-model"


def test_reasoning_defaults_to_medium_for_all_profiles():
    for kind in ["patchlet", "orchestrator", "master_prompt", "group", "transaction", "global", "repair"]:
        assert resolve_codex_model_profile(kind, {}).reasoning == "medium"
