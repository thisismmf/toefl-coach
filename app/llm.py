"""Provider abstraction: Ollama, any OpenAI-compatible endpoint, Anthropic.

Every pipeline stage asks for a small, strict JSON object. Small local models
drift, so `chat_json` retries with a repair prompt before giving up.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import PROVIDERS

TIMEOUT = httpx.Timeout(600.0, connect=15.0)


class LLMError(RuntimeError):
    pass


class ConnectionProblem(LLMError):
    """The model could not be reached or refused us: auth, network, missing model.

    Raised separately from ordinary failures so the UI can tell the difference
    between "this model is unavailable, pick another" and "the model replied
    but the output was unusable".
    """

    def __init__(self, message: str, *, kind: str = "unreachable",
                 hint: str = "") -> None:
        super().__init__(message)
        self.kind = kind      # unreachable | auth | missing_model | no_key
        self.hint = hint


def _strip_cloud(model: str) -> str:
    """ollama.com serves `gpt-oss:120b`; the local daemon lists it as `-cloud`."""
    return model[:-6] if model.endswith("-cloud") else model


def _ollama_headers(api_key: str | None) -> dict:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


async def list_models(provider: str, base_url: str | None = None,
                      api_key: str | None = None) -> list[str]:
    cfg = PROVIDERS.get(provider, {})
    base = (base_url or cfg.get("base_url") or "").rstrip("/")
    key = api_key or cfg.get("api_key")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
            if provider in ("ollama", "ollama_cloud"):
                r = await c.get(f"{base}/api/tags",
                                headers=_ollama_headers(key))
                r.raise_for_status()
                return sorted(m["name"] for m in r.json().get("models", []))
            if provider == "openai":
                h = {"Authorization": f"Bearer {key}"} if key else {}
                r = await c.get(f"{base}/models", headers=h)
                r.raise_for_status()
                return sorted(m["id"] for m in r.json().get("data", []))
            if provider == "anthropic":
                if not key:
                    return []
                r = await c.get(f"{base}/v1/models",
                                headers={"x-api-key": key,
                                         "anthropic-version": "2023-06-01"})
                r.raise_for_status()
                return sorted(m["id"] for m in r.json().get("data", []))
    except Exception:
        return []
    return []


async def chat(messages: list[dict], *, provider: str, model: str,
               temperature: float = 0.2, num_ctx: int = 8192,
               json_mode: bool = False, base_url: str | None = None,
               api_key: str | None = None, max_tokens: int = 4096) -> str:
    """Single completion. Returns raw assistant text."""
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        raise LLMError(f"Unknown provider '{provider}'")
    base = (base_url or cfg["base_url"]).rstrip("/")
    key = api_key or cfg.get("api_key")

    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        if provider in ("ollama", "ollama_cloud"):
            cloud = provider == "ollama_cloud"
            if cloud and not key:
                raise ConnectionProblem(
                    "No Ollama Cloud API key is set.", kind="no_key",
                    hint="Add OLLAMA_API_KEY to .env, or paste a key in the sidebar.")
            payload: dict[str, Any] = {
                "model": _strip_cloud(model) if cloud else model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_ctx": num_ctx},
            }
            if json_mode:
                payload["format"] = "json"
            try:
                r = await c.post(f"{base}/api/chat", json=payload,
                                 headers=_ollama_headers(key))
            except httpx.RequestError as e:
                raise ConnectionProblem(
                    f"Could not reach {'ollama.com' if cloud else base}: {e}",
                    kind="unreachable",
                    hint="Ollama is not running." if not cloud
                         else "Check your internet connection.") from e
            if r.status_code in (401, 403):
                raise ConnectionProblem(
                    f"Ollama rejected the API key ({r.status_code}).", kind="auth",
                    hint="Check OLLAMA_API_KEY in .env, or paste a valid key.")
            if r.status_code == 404:
                raise ConnectionProblem(
                    f"Model '{model}' was not found.", kind="missing_model",
                    hint=f"Run `ollama pull {model}`." if not cloud
                         else "Pick a model from the Ollama Cloud list.")
            if r.status_code in (402, 429):
                paid = r.status_code == 402
                raise ConnectionProblem(
                    f"'{model}' is not included in your Ollama plan."
                    if paid else f"Rate limit reached on '{model}'.",
                    kind="needs_plan" if paid else "rate_limited",
                    hint="Choose another cloud model, or upgrade at "
                         "ollama.com/upgrade." if paid
                         else "Wait a moment, or choose another model.")
            if r.status_code >= 400:
                body = r.text[:400]
                # The local daemon cannot serve *-cloud models by itself.
                if not cloud and model.endswith("-cloud"):
                    raise ConnectionProblem(
                        f"The local Ollama daemon cannot serve '{model}'.",
                        kind="missing_model",
                        hint="Switch the provider to Ollama Cloud for this model.")
                raise ConnectionProblem(f"Ollama {r.status_code}: {body}",
                                        kind="unreachable")
            return r.json().get("message", {}).get("content", "")

        if provider == "openai":
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            h = {"Content-Type": "application/json"}
            if key:
                h["Authorization"] = f"Bearer {key}"
            try:
                r = await c.post(f"{base}/chat/completions", json=payload, headers=h)
            except httpx.RequestError as e:
                raise ConnectionProblem(f"Could not reach {base}: {e}",
                                        kind="unreachable") from e
            if r.status_code in (401, 403):
                raise ConnectionProblem("The API key was rejected.", kind="auth",
                                        hint="Check the key in the sidebar or .env.")
            if r.status_code == 404:
                raise ConnectionProblem(f"Model '{model}' was not found.",
                                        kind="missing_model")
            if r.status_code >= 400:
                raise ConnectionProblem(
                    f"OpenAI-compatible {r.status_code}: {r.text[:400]}",
                    kind="unreachable")
            return r.json()["choices"][0]["message"]["content"]

        if provider == "anthropic":
            if not key:
                raise ConnectionProblem("No Anthropic API key is set.", kind="no_key",
                                        hint="Add ANTHROPIC_API_KEY to .env.")
            system = "\n".join(m["content"] for m in messages if m["role"] == "system")
            turns = [m for m in messages if m["role"] != "system"]
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": turns,
            }
            if system:
                payload["system"] = system
            try:
                r = await c.post(f"{base}/v1/messages", json=payload,
                                 headers={"x-api-key": key,
                                          "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
            except httpx.RequestError as e:
                raise ConnectionProblem(f"Could not reach {base}: {e}",
                                        kind="unreachable") from e
            if r.status_code in (401, 403):
                raise ConnectionProblem("The API key was rejected.", kind="auth")
            if r.status_code == 404:
                raise ConnectionProblem(f"Model '{model}' was not found.",
                                        kind="missing_model")
            if r.status_code >= 400:
                raise ConnectionProblem(f"Anthropic {r.status_code}: {r.text[:400]}",
                                        kind="unreachable")
            blocks = r.json().get("content", [])
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    raise LLMError(f"Unsupported provider '{provider}'")


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def extract_json(text: str) -> Any:
    """Pull the first valid JSON value out of a possibly chatty response."""
    if not text:
        raise ValueError("empty response")
    text = _THINK.sub("", text).strip()

    m = _FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Brace/bracket matching scan.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    raise ValueError(f"no JSON found in: {text[:300]}")


async def chat_json(messages: list[dict], *, retries: int = 2, **kw) -> Any:
    """Completion that must yield JSON. Retries with an explicit repair turn."""
    kw.setdefault("json_mode", True)
    last_text, last_err = "", None
    for attempt in range(retries + 1):
        try:
            msgs = messages if attempt == 0 else messages + [
                {"role": "assistant", "content": last_text[:1500]},
                {"role": "user", "content":
                 "That was not valid JSON. Reply with ONLY the JSON value, "
                 "no prose, no markdown fences, no explanation."},
            ]
            last_text = await chat(msgs, **kw)
            return extract_json(last_text)
        except ConnectionProblem:
            raise  # retrying will not help; surface it to the UI immediately
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise LLMError(f"Could not obtain JSON after {retries + 1} tries: {last_err}")


async def probe(provider: str, model: str, base_url: str | None = None,
                api_key: str | None = None) -> dict:
    """One tiny request, used by the UI to check a model before a long run."""
    try:
        txt = await chat(
            [{"role": "user", "content": "Reply with the single word: ok"}],
            provider=provider, model=model, temperature=0,
            base_url=base_url, api_key=api_key, max_tokens=16)
        return {"ok": True, "reply": (txt or "").strip()[:60]}
    except ConnectionProblem as e:
        return {"ok": False, "kind": e.kind, "error": str(e), "hint": e.hint}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "kind": "unreachable", "error": f"{type(e).__name__}: {e}",
                "hint": ""}
