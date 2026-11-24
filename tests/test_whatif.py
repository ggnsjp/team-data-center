"""Tests for the live what-if panel's LLM glue: the knob vocabulary, clamping, and the client."""
import json

import pytest

from dcopt.common import llm
from dcopt.heat import whatif

CURRENT = {"it_load_mw": 10.0, "recovery": 0.6, "cop": 4.0, "kerosene_yen_l": 115,
           "power_yen_kwh": 25, "pipe_cost": 10, "years": 30, "rate": 3.0,
           "renewable_power": True, "assumed_sites": True, "k_pipes": 3}


def ok_transport(content: str):
    def send(url, payload, headers):
        body = json.loads(payload)
        assert body["model"] == "carbonforge-flash" and body["messages"]
        assert "Authorization" in headers
        return 200, json.dumps({"choices": [{"message": {"content": content}}]}).encode()
    return send


def fake_chat(content: str):
    def chat(messages, **kw):
        return content
    return chat


def test_chat_posts_and_returns_content():
    out = llm.chat([{"role": "user", "content": "hi"}], transport=ok_transport('{"a": 1}'))
    assert out == '{"a": 1}'


def test_chat_json_mode_sets_response_format():
    seen = {}

    def send(url, payload, headers):
        seen.update(json.loads(payload))
        return 200, json.dumps({"choices": [{"message": {"content": "x"}}]}).encode()

    llm.chat([{"role": "user", "content": "hi"}], json_mode=True, transport=send)
    assert seen["response_format"] == {"type": "json_object"}


def test_chat_errors_never_leak_the_key(monkeypatch):
    monkeypatch.setenv("CF_API_KEY", "sekrit-key-123")

    def bad(url, payload, headers):
        assert "sekrit-key-123" in headers["Authorization"]   # the key goes to the endpoint
        return 401, b'{"error": "bad key"}'

    with pytest.raises(llm.LLMError) as e:
        llm.chat([{"role": "user", "content": "hi"}], transport=bad)
    assert "401" in str(e.value) and "sekrit" not in str(e.value)

    def boom(url, payload, headers):
        import urllib.error
        raise urllib.error.URLError("no route")

    with pytest.raises(llm.LLMError):
        llm.chat([{"role": "user", "content": "hi"}], transport=boom)


def test_chat_without_a_key_fails_fast(monkeypatch):
    monkeypatch.delenv("CF_API_KEY", raising=False)
    with pytest.raises(llm.LLMError):
        llm.chat([{"role": "user", "content": "hi"}])   # the real path: no key, no call


def test_parse_patch_clamps_into_slider_ranges():
    canned = json.dumps({"changes": {"it_load_mw": 999, "cop": "2.55", "kerosene_yen_l": 300,
                                     "years": 20, "renewable_power": "yes", "unknown_knob": 1}})
    out = whatif.parse_patch("x", CURRENT, llm_chat=fake_chat(canned))
    assert out["it_load_mw"] == 50.0          # clamped into the slider's range
    assert out["cop"] == 2.6                  # string number, rounded to the step
    assert out["kerosene_yen_l"] == 170       # int clamped, still on the step
    assert out["years"] == 20
    assert out["renewable_power"] is True
    assert "unknown_knob" not in out          # only the declared vocabulary passes


def test_parse_patch_rejects_garbage():
    with pytest.raises(whatif.WhatifError):
        whatif.parse_patch("x", CURRENT, llm_chat=fake_chat("sorry, I cannot do that"))
    with pytest.raises(whatif.WhatifError):
        whatif.parse_patch("x", CURRENT, llm_chat=fake_chat('{"no_changes_key": 1}'))


def test_parse_prompt_lists_knobs_with_currents():
    p = whatif.parse_prompt(CURRENT, "電気料金を2倍にして")
    assert "power_yen_kwh" in p and "now 25" in p and "電気料金を2倍にして" in p
    assert "k_pipes" in p and "renewable_power" in p


def test_explain_prompt_carries_only_model_numbers():
    p = whatif.explain_prompt("なぜ？", {"kerosene_yen_l": 156}, CURRENT,
                              {"つながる需要家（件）": 13, "導管（km）": 7.8,
                               "期待純便益（百万円/年）": 93.8}, "ja")
    assert "93.8" in p and "changes" in p and "results" in p
    assert "156" in p and "115" in p          # old -> new for the changed knob
