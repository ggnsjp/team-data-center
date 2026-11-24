"""Tests for the live what-if panel's LLM glue: the knob vocabulary, clamping, and the client."""
import json

import pytest

from dcopt.common import llm
from dcopt.common.geo import geocode
from dcopt.heat import whatif
from dcopt.heat.network import Source
from dcopt.heat.v1 import Site

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
                                     "years": 20, "renewable_power": "yes", "unknown_knob": 1},
                         "clarify": ""})
    out = whatif.parse_patch("x", CURRENT, llm_chat=fake_chat(canned))
    changes = out["changes"]
    assert out["clarify"] is None
    assert changes["it_load_mw"] == 50.0      # clamped into the slider's range
    assert changes["cop"] == 2.6              # string number, rounded to the step
    assert changes["kerosene_yen_l"] == 170   # int clamped, still on the step
    assert changes["years"] == 20
    assert changes["renewable_power"] is True
    assert "unknown_knob" not in changes      # only the declared vocabulary passes


def test_parse_patch_returns_the_clarify_question():
    canned = json.dumps({"changes": {}, "clarify": "Kerosene or electricity?"})
    out = whatif.parse_patch("double the price", CURRENT, llm_chat=fake_chat(canned))
    assert out["changes"] == {} and out["clarify"] == "Kerosene or electricity?"


def test_parse_patch_rejects_garbage():
    with pytest.raises(whatif.WhatifError):
        whatif.parse_patch("x", CURRENT, llm_chat=fake_chat("sorry, I cannot do that"))
    with pytest.raises(whatif.WhatifError):
        whatif.parse_patch("x", CURRENT, llm_chat=fake_chat('{"no_changes_key": 1}'))


def test_parse_patch_retries_with_a_bigger_budget():
    calls = []

    def chat(messages, max_tokens=1000, **kw):
        calls.append(max_tokens)
        if max_tokens < 4000:
            raise llm.LLMError("the model spent its whole budget on reasoning")
        return json.dumps({"changes": {"years": 20}, "clarify": ""})

    out = whatif.parse_patch("x", CURRENT, llm_chat=chat)
    assert calls == [2000, 4000] and out["changes"]["years"] == 20


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


def test_explain_prompt_takes_non_knob_keys():
    p = whatif.explain_prompt("new DC?", {"new data center: 20 MW at (43.1, 141.3)": "built (assumption)"},
                              {}, {"connected sites": 15}, "en")
    assert "new data center: 20 MW" in p and "built (assumption)" in p


def test_parse_patch_carries_a_new_data_center():
    canned = json.dumps({"changes": {}, "new_data_center": {"mw": 20, "place": "手稲区"}, "clarify": ""})
    out = whatif.parse_patch("teine 20MW", CURRENT, llm_chat=fake_chat(canned))
    assert out["new_dc"] == {"mw": 20.0, "place": "手稲区"} and out["changes"] == {}


def test_parse_patch_drops_an_incomplete_new_data_center():
    canned = json.dumps({"changes": {}, "new_data_center": {"place": "somewhere"}, "clarify": "MW?"})
    out = whatif.parse_patch("a new DC", CURRENT, llm_chat=fake_chat(canned))
    assert out["new_dc"] is None and out["clarify"] == "MW?"


def test_geocode_parses_nominatim():
    def fake(url):
        assert "bounded=1" in url and "nominatim" in url

        class R:
            def read(self):
                return json.dumps([{"lat": "43.1201", "lon": "141.3100",
                                    "display_name": "Somewhere, Ishikari, Japan"}]).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R()

    lat, lon, label = geocode("新港", transport=fake)
    assert (lat, lon) == (43.1201, 141.3100) and "Ishikari" in label


def test_geocode_raises_when_nothing_matches():
    def fake(url):
        class R:
            def read(self):
                return b"[]"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R()

    with pytest.raises(LookupError):
        geocode("nowhere", transport=fake)


def test_new_dc_summary_compares_with_and_without():
    from synthetic import instance as synth
    srcs = [Source("dc0", "DC 0", "DC 0", 0.0, 0.0, {"low": 0.3, "high": 0.6}, "operating", ("", ""), "test")]
    users = [Site("gh", "gh", "gh", "greenhouse", 0.0, 0.0, 2500.0, "test"),
             Site("fish", "fish", "fish", "aquaculture", 0.0, 0.0, 1800.0, "test"),
             Site("hosp", "hosp", "hosp", "hospital", 0.0, 0.0, 1500.0, "test")]

    def build(s, u):
        return synth([(0, 0), (3100, -350)][:len(s)],
                     [("gh", "greenhouse", (600, 400), 2500.0),
                      ("fish", "aquaculture", (500, -700), 1800.0),
                      ("hosp", "hospital", (3000, -400), 1500.0)],
                     it=[{"low": 0.3, "high": 0.6}] + [{"low": 0.5, "high": 0.5}] * (len(s) - 1))

    out = whatif.new_dc_summary(srcs, users, 0.5, 43.0, 141.0, time_limit=5.0, build=build)
    # the assumed DC sits next to the hospital: without it the trunk is too long to pay off
    assert out["after"]["connected sites"] > out["before"]["connected sites"]
    assert out["after"]["expected net (M yen/yr)"] > out["before"]["expected net (M yen/yr)"]
    assert "0.5 MW" in out["new_dc"] and "43.0000" in out["new_dc"]
