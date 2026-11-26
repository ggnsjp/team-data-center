"""A minimal OpenAI-compatible chat client for the app's live what-if panel.

Stdlib only, transport injectable for tests. The endpoint, model and key come from the
environment at call time — CARBONFORGE_BASE_URL (default: the carbonforge endpoint),
LLM_MODEL (default: carbonforge-flash) and CF_API_KEY. The key is never logged and never
appears in error messages; the model only ever explains numbers the deterministic model
computed, it does not compute them.

A second service is optional: OrcaRouter, an OpenAI-compatible gateway. It is used when
LLM_PROVIDER=orcarouter, or when ORCAROUTER_API_KEY is set and CF_API_KEY is not; its endpoint
can be overridden with ORCAROUTER_BASE_URL and its model with LLM_MODEL.
"""
import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE = "https://endpoint.carbonforge.ai/v1"
DEFAULT_MODEL = "carbonforge-flash"
TIMEOUT_S = 180
# service: (endpoint, model, variable holding the key, variable that overrides the endpoint)
PROVIDERS = {
    "carbonforge": (DEFAULT_BASE, DEFAULT_MODEL, "CF_API_KEY", "CARBONFORGE_BASE_URL"),
    "orcarouter": ("https://api.orcarouter.ai/v1", "orcarouter/fusion-flash", "ORCAROUTER_API_KEY",
                   "ORCAROUTER_BASE_URL"),
}


class LLMError(RuntimeError):
    """A chat call failed; the message is safe to show in the UI (no key, no URL)."""


def provider() -> str:
    """The service in use: LLM_PROVIDER when it names one; otherwise OrcaRouter when only its key is
    set; otherwise the default."""
    name = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if name in PROVIDERS:
        return name
    if os.environ.get("ORCAROUTER_API_KEY") and not os.environ.get("CF_API_KEY"):
        return "orcarouter"
    return "carbonforge"


def settings() -> dict:
    """{provider, base_url, model, key_env, has_key} for the UI to decide whether the panel is available."""
    name = provider()
    base, model, key_env, base_env = PROVIDERS[name]
    return {"provider": name, "base_url": os.environ.get(base_env) or base,
            "model": os.environ.get("LLM_MODEL") or model,
            "key_env": key_env, "has_key": bool(os.environ.get(key_env))}


def _http(url: str, payload: bytes, headers: dict) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
        return res.status, res.read()


def chat(messages: list[dict], *, max_tokens: int = 1600, json_mode: bool = False,
         transport=None) -> str:
    """One chat completion; returns the assistant message's text content ('' when none)."""
    cfg = settings()
    body = {"model": cfg["model"], "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.2}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    payload = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer " + (os.environ.get(cfg["key_env"]) or "")}
    send = transport or _http
    if transport is None and not cfg["has_key"]:
        raise LLMError(f"{cfg['key_env']} is not set")
    try:
        status, raw = send(cfg["base_url"].rstrip("/") + "/chat/completions", payload, headers)
    except urllib.error.HTTPError as e:
        raise LLMError(f"the chat endpoint returned HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f"could not reach the chat endpoint ({type(e).__name__})") from None
    if status != 200:
        raise LLMError(f"the chat endpoint returned HTTP {status}")
    try:
        data = json.loads(raw.decode("utf-8"))
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        if not content and choice.get("finish_reason") == "length":
            raise LLMError("the model spent its whole budget on reasoning")
        return content
    except (KeyError, IndexError, ValueError, TypeError):
        raise LLMError("the chat endpoint returned an unexpected shape") from None
