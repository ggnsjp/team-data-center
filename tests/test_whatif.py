"""Tests for the live what-if panel's LLM glue: the knob vocabulary, clamping, and the client."""
import io
import json
import re
from decimal import Decimal

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


def test_parse_patch_allows_random_with_or_without_mw():
    out = whatif.parse_patch("random DC", CURRENT,
                             llm_chat=fake_chat(json.dumps({"changes": {},
                                                            "new_data_center": {"mw": None,
                                                                                "place": "random"},
                                                            "clarify": ""})))
    assert out["new_dc"] == {"mw": None, "place": "random"} and out["clarify"] is None
    out = whatif.parse_patch("random DC", CURRENT,
                             llm_chat=fake_chat(json.dumps({"changes": {},
                                                            "new_data_center": {"mw": 30,
                                                                                "place": "ランダム"},
                                                            "clarify": ""})))
    assert out["new_dc"] == {"mw": 30.0, "place": "ランダム"}


def test_sample_random_dc_stays_in_the_study_area():
    for _ in range(50):
        d = whatif.sample_random_dc()
        assert 2.0 <= d["mw"] <= 50.0
        assert 43.10 <= d["lat"] <= 43.35 and 141.15 <= d["lon"] <= 141.70


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


# ------------------------------------------------------------------- OrcaRouter mode + guardrail
ORCA_ENV = ("ORCAROUTER_API_KEY", "ORCAROUTER_BASE_URL", "LLM_MODELS", "LLM_MODEL", "CF_API_KEY",
            "CARBONFORGE_BASE_URL")


@pytest.fixture
def orca(monkeypatch):
    for k in ORCA_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ORCAROUTER_API_KEY", "orca-sekrit")
    monkeypatch.setenv("LLM_MODELS", "byok/carbonforge-flash, openai/gpt-4o-mini")
    return monkeypatch


def reply(content="ok", headers=None):
    return 200, json.dumps({"choices": [{"message": {"content": content}}]}).encode(), headers or {}


def test_no_orcarouter_env_keeps_the_direct_call(monkeypatch):
    for k in ORCA_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CF_API_KEY", "cf")
    seen = []

    def send(url, payload, headers):
        seen.append((url, json.loads(payload)))
        return reply()

    out = llm.chat_ex([{"role": "user", "content": "hi"}], transport=send)
    assert out == {"text": "ok", "model": "carbonforge-flash", "via": "direct"}
    assert seen[0][0] == "https://endpoint.carbonforge.ai/v1/chat/completions"
    assert "extra_body" not in seen[0][1]


def test_orcarouter_sends_the_fallback_chain(orca):
    seen = {}

    def send(url, payload, headers):
        seen.update(url=url, body=json.loads(payload), headers=headers)
        return reply()

    out = llm.chat_ex([{"role": "user", "content": "hi"}], transport=send)
    assert seen["url"] == "https://api.orcarouter.ai/v1/chat/completions"
    assert seen["body"]["model"] == "byok/carbonforge-flash"
    assert seen["body"]["extra_body"] == {"models": ["byok/carbonforge-flash", "openai/gpt-4o-mini"],
                                          "route": "fallback"}
    assert seen["headers"]["Authorization"] == "Bearer orca-sekrit"
    assert out == {"text": "ok", "model": "byok/carbonforge-flash", "via": "orcarouter"}


def test_orcarouter_chain_is_capped_at_five(orca):
    orca.setenv("LLM_MODELS", "a,b,c,d,e,f,g")
    assert llm.chain() == ["a", "b", "c", "d", "e"]


def test_orcarouter_reports_the_fallback_model(orca):
    out = llm.chat_ex([{"role": "user", "content": "hi"}],
                      transport=lambda u, p, h: reply("x", {"X-Orca-Fallback-Level": "1",
                                                           "X-Orca-Fallback-Model": "openai/gpt-4o-mini"}))
    assert out["model"] == "openai/gpt-4o-mini" and out["via"] == "orcarouter"


@pytest.mark.parametrize("failure", [502, 429, "network"])
def test_orcarouter_down_falls_back_to_carbonforge(orca, failure):
    orca.setenv("CF_API_KEY", "cf-sekrit")
    calls = []

    def send(url, payload, headers):
        calls.append((url, headers["Authorization"], json.loads(payload)))
        if "orcarouter" in url:
            if failure == "network":
                import urllib.error
                raise urllib.error.URLError("no route")
            return failure, b"{}", {}
        return reply("direct answer")

    out = llm.chat_ex([{"role": "user", "content": "hi"}], transport=send)
    assert out == {"text": "direct answer", "model": "carbonforge-flash", "via": "direct"}
    assert [c[0].split("/")[2] for c in calls] == ["api.orcarouter.ai", "endpoint.carbonforge.ai"]
    assert calls[1][1] == "Bearer cf-sekrit" and "extra_body" not in calls[1][2]


@pytest.mark.parametrize("status", [401, 403, 400])
def test_orcarouter_auth_or_guardrail_errors_do_not_fail_over(orca, status):
    orca.setenv("CF_API_KEY", "cf-sekrit")
    calls = []

    def send(url, payload, headers):
        calls.append(url)
        return status, b'{"error": "nope"}', {}

    with pytest.raises(llm.LLMError) as e:
        llm.chat_ex([{"role": "user", "content": "hi"}], transport=send)
    assert len(calls) == 1 and str(status) in str(e.value)
    assert "sekrit" not in str(e.value)


def test_orcarouter_down_without_a_carbonforge_key_raises(orca):
    with pytest.raises(llm.LLMError) as e:
        llm.chat_ex([{"role": "user", "content": "hi"}], transport=lambda u, p, h: (503, b"{}", {}))
    assert "503" in str(e.value) and "orca-sekrit" not in str(e.value)


def test_settings_reports_router_mode(orca):
    s = llm.settings()
    assert s["has_key"] and s["router"] and s["models"][0] == "byok/carbonforge-flash"


def test_question_is_capped():
    long = "x" * (whatif.MAX_QUESTION_CHARS + 100)
    assert "x" * (whatif.MAX_QUESTION_CHARS + 1) not in whatif.parse_prompt(CURRENT, long)
    assert "x" * (whatif.MAX_QUESTION_CHARS + 1) not in whatif.explain_prompt(long, {}, {}, {}, "en")


RESULTS = {"connected sites": 13, "pipes (km)": 7.8, "expected net (M yen/yr)": 93.8, "CO2 cut (t/yr)": 1600}


def test_number_check_passes_an_answer_using_only_given_numbers():
    answer = ("With kerosene at 156 yen/L instead of 115, 13 sites connect over 7.8 km of pipe; "
              "the expected net is 93.80 M yen per year and CO2 falls by 1,600 t.")
    assert whatif.unsupported_numbers(answer, "why?", {"kerosene_yen_l": 156}, {"kerosene_yen_l": 115},
                                      RESULTS, "en") == []


def test_number_check_flags_invented_or_converted_numbers():
    answer = "13 sites connect; that is about 94 M yen, roughly 20% better."
    assert whatif.unsupported_numbers(answer, "why?", {}, {}, RESULTS, "en") == ["20", "94"]


def test_number_check_reads_full_width_digits_and_question_numbers():
    answer = "電気料金を２倍にすると、つながる需要家は１３件です。"
    assert whatif.unsupported_numbers(answer, "電気料金を2倍にして", {}, {}, RESULTS, "ja") == []


def test_numbers_only_summary_lists_changes_and_results():
    s = whatif.numbers_only_summary({"kerosene_yen_l": 156}, {"kerosene_yen_l": 115}, RESULTS, "en")
    assert "kerosene price (yen/L): 115 → 156" in s and "- pipes (km): 7.8" in s


# ---- numbers written in kanji (review issue #45) ----

JA_RESULTS = {"つながる需要家（件）": 13, "導管（km）": 7.8, "期待純便益（百万円/年）": 93.8}


def test_number_check_reads_numbers_written_in_kanji():
    answer = "純便益は三億円増え、導管は十二キロです"                  # neither figure was computed
    assert whatif.unsupported_numbers(answer, "割引率を下げたら？", {}, {}, RESULTS, "ja") == ["12", "3"]


def test_number_check_matches_kanji_and_digits_between_question_and_answer():
    kanji_answer = "電気料金を二倍にすると、つながる需要家は13件です。"
    digit_answer = "電気料金を2倍にすると、つながる需要家は13件です。"
    assert whatif.unsupported_numbers(kanji_answer, "電気料金を2倍にして", {}, {}, RESULTS, "ja") == []
    assert whatif.unsupported_numbers(digit_answer, "電気料金を二倍にして", {}, {}, RESULTS, "ja") == []


def test_number_check_leaves_words_that_contain_kanji_numerals_alone():
    answer = "二酸化炭素は一方で十分に減り、千歳方面の一部でも一年を通じて同じです。"
    assert whatif.unsupported_numbers(answer, "なぜ？", {}, {}, RESULTS, "ja") == []


def test_number_check_takes_a_unit_label_as_a_unit():
    answer = "期待純便益は年93.8百万円で、単位は百万円です。"
    assert whatif.unsupported_numbers(answer, "なぜ？", {}, {}, JA_RESULTS, "ja") == []
    # 百万円 in a result key does not make 100 a permitted figure
    assert whatif.unsupported_numbers("つながる需要家は100件です。", "なぜ？", {}, {}, JA_RESULTS, "ja") == ["100"]
    assert whatif.unsupported_numbers("全体の三分の一にあたります。", "なぜ？", {}, {}, JA_RESULTS, "ja") == ["1", "3"]


def test_kanji_numbers_are_read_by_value():
    assert whatif.kanji_numbers("千二百三十四件、二〇二五年、三百万円、十日、二十か所") == {
        Decimal(n) for n in (1234, 2025, 300, 10, 20)}
    assert whatif.kanji_numbers("一億円と一割") == {Decimal(1)}
    assert whatif.kanji_numbers("一番、一度、一人、一つ、一年") == set()       # words, not counts
    assert whatif.kanji_numbers("93.8百万円、3千万円") == set()                # after digits a kanji run is a unit
    assert whatif.numbers_in("13件と十二キロ") == {Decimal(13), Decimal(12)}


def test_explain_prompt_asks_for_digits():
    assert "算用数字" in whatif.explain_prompt("なぜ？", {}, {}, {}, "ja")
    assert "in digits" in whatif.explain_prompt("why?", {}, {}, {}, "en")


# ---- a typed point for a new data center (review issue #45) ----

def test_the_coordinate_example_is_latitude_first_and_inside_the_study_area():
    lat, lon = whatif.parse_latlon(whatif.COORDINATE_EXAMPLE)
    assert whatif.point_problem(lat, lon) is None


def test_a_typed_point_is_checked_before_it_is_solved():
    assert whatif.parse_latlon(" 43.2 ,141.3 ") == (43.2, 141.3)
    assert whatif.parse_latlon("手稲区") is None and whatif.parse_latlon("43.2") is None
    assert whatif.point_problem(43.2, 141.3) is None
    assert whatif.point_problem(141.3, 43.2) == "swapped"          # longitude first
    assert whatif.point_problem(35.68, 139.76) == "outside"        # Tokyo
    assert whatif.point_problem(-43.2, 141.3) == "outside"


def test_random_points_are_inside_the_study_area():
    for _ in range(100):
        drawn = whatif.sample_random_dc()
        assert whatif.point_problem(drawn["lat"], drawn["lon"]) is None


def test_the_study_area_is_the_box_the_place_lookup_searches():
    seen = []

    def fake(url):
        seen.append(url)
        return io.BytesIO(json.dumps([{"lat": "43.2", "lon": "141.3", "display_name": "x"}]).encode())

    geocode("新港", transport=fake)
    west, north, east, south = (float(x) for x in re.search(r"viewbox=([0-9.,]+)", seen[0])[1].split(","))
    assert whatif.STUDY_AREA == {"lat": (south, north), "lon": (west, east)}
