"""A minimal OpenAI-compatible chat client for the app's live what-if panel.

Stdlib only, transport injectable for tests. Everything comes from the environment at call time.

Direct mode (default): any OpenAI-compatible service, set by LLM_API_KEY, LLM_BASE_URL and
LLM_MODEL; all three are needed. The settings of the service used during the hackathon still work:
CF_API_KEY, with CARBONFORGE_BASE_URL and LLM_MODEL defaulting to that service's endpoint and model
(EVENT_BASE, EVENT_MODEL). LLM_API_KEY wins when both keys are set.

Router mode, an optional add-on (docs/optional-addons.md), when ORCAROUTER_API_KEY is set:
ORCAROUTER_BASE_URL (default https://api.orcarouter.ai/v1) and LLM_MODELS, a comma-separated
ordered chain of the router's model ids (at most 5). The request carries extra_body =
{"models": chain, "route": "fallback"}; the router fails over to the next entry only on an upstream
5xx / 429 / network error, and the X-Orca-Fallback-Model response header names the model that
answered after a failover. If the router itself cannot be reached or answers 5xx / 429, and a
direct service is set, the client calls it instead. Other errors (401, 403, a guardrail's 400) are
final: retrying elsewhere would only hide them.

Time: one request is cut off after LLM_TIMEOUT_S seconds (default 60), counted over the whole
request and not per read. The steps of one question (the retry with a larger budget, the direct
call after the router) share a budget of twice that (time_budget): once it has run out, the next
request is not sent.

Keys are never logged and never appear in error messages. The model only ever explains numbers
the deterministic model computed; it does not compute them.
"""
import contextvars
import json
import os
import time
import urllib.error
import urllib.request
from contextlib import contextmanager

EVENT_BASE = "https://endpoint.carbonforge.ai/v1"   # the service used during the hackathon (CF_API_KEY)
EVENT_MODEL = "carbonforge-flash"
DEFAULT_ROUTER_BASE = "https://api.orcarouter.ai/v1"
MAX_CHAIN = 5                      # OrcaRouter truncates longer fallback chains
DEFAULT_TIMEOUT_S = 60.0           # one request; LLM_TIMEOUT_S overrides
RETRYABLE = {429, 500, 502, 503, 504}
_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar("llm_deadline", default=None)


class LLMError(RuntimeError):
    """A chat call failed; the message is safe to show in the UI (no key, no URL)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def direct() -> dict:
    """The direct service: key, base URL, model, and which of the generic settings are missing.
    LLM_API_KEY needs LLM_BASE_URL and LLM_MODEL; CF_API_KEY alone uses the event's service."""
    if os.environ.get("LLM_API_KEY") or not os.environ.get("CF_API_KEY"):
        cfg = {"key": os.environ.get("LLM_API_KEY") or "", "base_url": os.environ.get("LLM_BASE_URL") or "",
               "model": os.environ.get("LLM_MODEL") or ""}
        cfg["missing"] = [name for name, value in (("LLM_API_KEY", cfg["key"]), ("LLM_BASE_URL", cfg["base_url"]),
                                                   ("LLM_MODEL", cfg["model"])) if not value]
        return cfg
    return {"key": os.environ.get("CF_API_KEY") or "", "base_url": os.environ.get("CARBONFORGE_BASE_URL") or EVENT_BASE,
            "model": os.environ.get("LLM_MODEL") or EVENT_MODEL, "missing": []}


def chain() -> list[str]:
    """The router's ordered model chain from LLM_MODELS (falls back to the direct model, if any)."""
    models = [m.strip() for m in (os.environ.get("LLM_MODELS") or "").split(",") if m.strip()]
    fallback = [direct()["model"]] if direct()["model"] else []
    return (models or fallback)[:MAX_CHAIN]


def settings() -> dict:
    """What the UI needs to decide whether the panel is available, and how it will be served."""
    router = bool(os.environ.get("ORCAROUTER_API_KEY"))
    d = direct()
    return {"base_url": d["base_url"], "model": d["model"], "direct": not d["missing"], "missing": d["missing"],
            "has_key": (router and bool(chain())) or not d["missing"],
            "router": router,
            "router_base_url": os.environ.get("ORCAROUTER_BASE_URL") or DEFAULT_ROUTER_BASE,
            "models": chain() if router else []}


def timeout_s() -> float:
    """Seconds one request may take: LLM_TIMEOUT_S when it is a positive number, else the default."""
    try:
        value = float(os.environ.get("LLM_TIMEOUT_S") or "")
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return value if 0 < value < float("inf") else DEFAULT_TIMEOUT_S


@contextmanager
def time_budget(seconds: float | None = None):
    """Requests made inside share one deadline, `seconds` from now (default: twice timeout_s()).

    Each request is cut off at the deadline, and a request that would start after it is not sent.
    An outer budget stays in force: a nested one can only shorten it.
    """
    end = time.monotonic() + (2 * timeout_s() if seconds is None else seconds)
    outer = _deadline.get()
    token = _deadline.set(end if outer is None else min(end, outer))
    try:
        yield
    finally:
        _deadline.reset(token)


def out_of_time() -> bool:
    """True inside a time_budget whose deadline has passed."""
    end = _deadline.get()
    return end is not None and time.monotonic() >= end


def _http(url: str, payload: bytes, headers: dict) -> tuple[int, bytes, dict]:
    limit, end = timeout_s(), _deadline.get()
    if end is not None:
        limit = min(limit, end - time.monotonic())
    if limit <= 0:
        raise TimeoutError("the time budget has run out")
    stop = time.monotonic() + limit
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=limit) as res:
        chunks = []
        while True:                        # the socket timeout covers one read; this covers the whole answer
            chunk = res.read1(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if time.monotonic() > stop:
                raise TimeoutError("the answer took too long")
        return res.status, b"".join(chunks), dict(res.headers.items())


def _post(send, url: str, body: dict, key: str, label: str) -> tuple[bytes, dict]:
    """POST one chat request; returns (raw body, lower-cased response headers) or raises LLMError.

    A transport may return (status, body) or (status, body, headers).
    """
    payload = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    try:
        out = send(url, payload, headers)
    except urllib.error.HTTPError as e:
        raise LLMError(f"{label} returned HTTP {e.code}", e.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f"could not reach {label} ({type(e).__name__})") from None
    status, raw = out[0], out[1]
    resp_headers = out[2] if len(out) > 2 else {}
    if status != 200:
        raise LLMError(f"{label} returned HTTP {status}", status)
    return raw, {str(k).lower(): v for k, v in (resp_headers or {}).items()}


def _content(raw: bytes, label: str) -> str:
    try:
        data = json.loads(raw.decode("utf-8"))
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        raise LLMError(f"{label} returned an unexpected shape") from None
    if not content and choice.get("finish_reason") == "length":
        raise LLMError("the model spent its whole budget on reasoning")
    return content


def chat_ex(messages: list[dict], *, max_tokens: int = 1600, json_mode: bool = False,
            transport=None) -> dict:
    """One chat completion -> {"text", "model" (who answered), "via" ("orcarouter" | "direct")}."""
    cfg = settings()
    send = transport or _http
    if transport is None and not cfg["has_key"]:
        raise LLMError("no language model is set: LLM_API_KEY, LLM_BASE_URL and LLM_MODEL (or a router)")
    if out_of_time():
        raise LLMError("the request took too long")
    base = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.2}
    if json_mode:
        base["response_format"] = {"type": "json_object"}

    if cfg["router"] and cfg["models"]:
        models = cfg["models"]
        body = dict(base, model=models[0], extra_body={"models": models, "route": "fallback"})
        url = cfg["router_base_url"].rstrip("/") + "/chat/completions"
        try:
            raw, headers = _post(send, url, body, os.environ.get("ORCAROUTER_API_KEY") or "", "OrcaRouter")
        except LLMError as e:
            retryable = e.status is None or e.status in RETRYABLE
            if not retryable or not cfg["direct"]:
                raise
            if out_of_time():              # no time left for the direct call
                raise LLMError("the request took too long") from None
        else:
            served = headers.get("x-orca-fallback-model") or models[0]
            return {"text": _content(raw, "OrcaRouter"), "model": served, "via": "orcarouter"}

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    raw, _ = _post(send, url, dict(base, model=cfg["model"]), direct()["key"], "the chat endpoint")
    return {"text": _content(raw, "the chat endpoint"), "model": cfg["model"], "via": "direct"}


def chat(messages: list[dict], *, max_tokens: int = 1600, json_mode: bool = False,
         transport=None) -> str:
    """One chat completion; returns the assistant message's text content ('' when none)."""
    return chat_ex(messages, max_tokens=max_tokens, json_mode=json_mode, transport=transport)["text"]
