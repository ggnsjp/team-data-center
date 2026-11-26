"""The chat client's optional second service (OrcaRouter) and how a service is chosen."""
import json

import pytest

from dcopt.common import llm


@pytest.fixture(autouse=True)
def no_settings(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "CF_API_KEY", "ORCAROUTER_API_KEY", "CARBONFORGE_BASE_URL",
                 "ORCAROUTER_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_the_default_service_is_unchanged():
    s = llm.settings()
    assert (s["provider"], s["base_url"], s["model"], s["key_env"], s["has_key"]) == (
        "carbonforge", llm.DEFAULT_BASE, llm.DEFAULT_MODEL, "CF_API_KEY", False)


def test_orcarouter_is_used_when_only_its_key_is_set(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "orca-key")
    s = llm.settings()
    assert (s["provider"], s["base_url"], s["model"], s["has_key"]) == (
        "orcarouter", "https://api.orcarouter.ai/v1", "orcarouter/fusion-flash", True)
    seen = {}

    def send(url, payload, headers):
        seen.update(url=url, model=json.loads(payload)["model"], auth=headers["Authorization"])
        return 200, json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

    assert llm.chat([{"role": "user", "content": "hi"}], transport=send) == "ok"
    assert seen == {"url": "https://api.orcarouter.ai/v1/chat/completions", "model": "orcarouter/fusion-flash",
                    "auth": "Bearer orca-key"}


def test_with_both_keys_the_default_stays_unless_asked(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "orca-key")
    monkeypatch.setenv("CF_API_KEY", "cf-key")
    assert llm.settings()["provider"] == "carbonforge"
    monkeypatch.setenv("LLM_PROVIDER", "OrcaRouter")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("ORCAROUTER_BASE_URL", "https://example.invalid/v1")
    s = llm.settings()
    assert (s["provider"], s["model"], s["key_env"], s["base_url"]) == (
        "orcarouter", "openai/gpt-4o-mini", "ORCAROUTER_API_KEY", "https://example.invalid/v1")


def test_a_missing_key_names_the_right_variable_and_makes_no_call(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "orcarouter")
    with pytest.raises(llm.LLMError, match="ORCAROUTER_API_KEY"):
        llm.chat([{"role": "user", "content": "hi"}])
    monkeypatch.setenv("LLM_PROVIDER", "no-such-service")                       # an unknown name falls back
    assert llm.settings()["provider"] == "carbonforge"
