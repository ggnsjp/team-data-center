"""One question to the language model cannot hold the page for many minutes (review issue #45):
a request has a time limit over the whole answer, and the steps of a question share a budget."""
import json
import urllib.request

import pytest

from dcopt.common import llm
from dcopt.heat import whatif

ENV = ("ORCAROUTER_API_KEY", "ORCAROUTER_BASE_URL", "LLM_MODELS", "LLM_MODEL", "CF_API_KEY",
       "CARBONFORGE_BASE_URL", "LLM_TIMEOUT_S", "LLM_API_KEY", "LLM_BASE_URL")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    c = Clock()
    monkeypatch.setattr(llm.time, "monotonic", c.monotonic)
    return c


def answer(text: str = "ok") -> bytes:
    return json.dumps({"choices": [{"message": {"content": text}}]}).encode()


def test_the_time_limit_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("LLM_TIMEOUT_S", raising=False)
    assert llm.timeout_s() == llm.DEFAULT_TIMEOUT_S == 60
    monkeypatch.setenv("LLM_TIMEOUT_S", "20")
    assert llm.timeout_s() == 20
    for unusable in ("", "soon", "0", "-5", "inf", "nan"):
        monkeypatch.setenv("LLM_TIMEOUT_S", unusable)
        assert llm.timeout_s() == llm.DEFAULT_TIMEOUT_S


def test_a_budget_is_twice_the_time_limit_and_ends(clock, monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_S", "10")
    assert not llm.out_of_time()                         # no budget, no deadline
    with llm.time_budget():
        clock.now += 19.9
        assert not llm.out_of_time()
        clock.now += 0.2
        assert llm.out_of_time()
    assert not llm.out_of_time()


def test_an_inner_budget_cannot_extend_the_outer_one(clock):
    with llm.time_budget(5):
        with llm.time_budget(500):
            clock.now += 6
            assert llm.out_of_time()
        assert llm.out_of_time()


def test_no_request_is_sent_once_the_budget_has_run_out(clock, monkeypatch):
    monkeypatch.setenv("CF_API_KEY", "a-key")
    sent = []

    def send(url, payload, headers):
        sent.append(url)
        return 200, answer()

    with llm.time_budget(30):
        assert llm.chat([{"role": "user", "content": "hi"}], transport=send) == "ok"
        clock.now += 31
        with pytest.raises(llm.LLMError, match="too long"):
            llm.chat([{"role": "user", "content": "hi"}], transport=send)
    assert len(sent) == 1


def test_the_direct_call_after_the_router_is_skipped_when_time_is_up(clock, monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "a-router-key")
    monkeypatch.setenv("CF_API_KEY", "a-key")
    sent = []

    def slow_router(url, payload, headers):
        sent.append(url)
        clock.now += 200                                  # the router hangs, then fails
        return 503, b""

    with llm.time_budget(120), pytest.raises(llm.LLMError, match="too long"):
        llm.chat([{"role": "user", "content": "hi"}], transport=slow_router)
    assert len(sent) == 1 and "orcarouter" in sent[0]

    sent.clear()                                          # with time left, the direct call still happens

    def failing_router_then_direct(url, payload, headers):
        sent.append(url)
        return (503, b"") if "orcarouter" in url else (200, answer("direct"))

    with llm.time_budget(120):
        assert llm.chat([{"role": "user", "content": "hi"}], transport=failing_router_then_direct) == "direct"
    assert len(sent) == 2


def test_the_second_try_of_a_question_is_skipped_when_time_is_up(clock):
    tries = []

    def chat(messages, max_tokens=0, **kw):
        tries.append(max_tokens)
        clock.now += 500                                  # the first try hangs for longer than the budget
        raise llm.LLMError("could not reach the chat endpoint (TimeoutError)")

    with pytest.raises(llm.LLMError):
        whatif.parse_patch("x", {}, llm_chat=chat)
    assert tries == [2000]


class Trickle:
    """A response that sends one small piece per read; every read moves the clock on."""

    status = 200

    def __init__(self, clock, pieces, seconds_per_read):
        self.clock, self.pieces, self.seconds = clock, list(pieces), seconds_per_read
        self.headers = {"Content-Type": "application/json"}

    def read1(self, n=-1):
        self.clock.now += self.seconds
        return self.pieces.pop(0) if self.pieces else b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_trickling_answer_is_cut_off_after_the_time_limit(clock, monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_S", "10")
    opened = []

    def urlopen(req, timeout):
        opened.append(timeout)
        return Trickle(clock, [b"x"] * 100, seconds_per_read=3)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(TimeoutError):
        llm._http("https://example.invalid/v1/chat/completions", b"{}", {})
    assert opened == [10]
    assert clock.now == pytest.approx(1012)               # four reads of 3 s: stopped just past the 10 s limit


def test_a_normal_answer_is_read_whole_and_the_budget_shortens_the_limit(clock, monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_S", "60")
    opened = []

    def urlopen(req, timeout):
        opened.append(timeout)
        return Trickle(clock, [b'{"a":', b" 1}"], seconds_per_read=0.5)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with llm.time_budget(25):
        status, body, headers = llm._http("https://example.invalid/v1/chat/completions", b"{}", {})
        assert (status, body) == (200, b'{"a": 1}') and opened == [25]
        assert headers["Content-Type"] == "application/json"
        clock.now += 30
        with pytest.raises(TimeoutError):
            llm._http("https://example.invalid/v1/chat/completions", b"{}", {})
    assert opened == [25]                                 # the second request was never opened
