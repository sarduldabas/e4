"""Thin wrapper around the Azure OpenAI / Microsoft Foundry chat API.

One method, `complete_json(system, user)`, returns a parsed JSON object. Agents depend on the `LlmClient`
protocol only, so tests can pass a fake and a different provider can be added without touching the agents.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Protocol

from .config import LlmSettings


class LlmError(Exception):
    """The model call failed or answered something that is not usable. The message is safe to show to developers."""


class LlmClient(Protocol):
    """`tier` picks the deployment (small / standard / strong / vision); `images` are data URLs for vision calls."""

    model: str

    def complete_json(self, system: str, user: str, *, tier: str | None = None, images: list[str] | None = None) -> dict: ...

    def web_search(self, query: str, *, instructions: str = "", tier: str | None = None) -> dict: ...


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):  # some models wrap JSON in a code fence even when told not to
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise LlmError(f"model answer is not valid JSON ({e.msg})") from e
    if not isinstance(data, dict):
        raise LlmError("model answer is not a JSON object")
    return data


class AzureOpenAIClient:
    """Chat completions against a Foundry / Azure OpenAI deployment.

    Two ways to reach it, chosen by settings:
      * v1 API (default): base URL `<endpoint>/openai/v1/`, no api-version needed. Works with current models.
      * classic API: set AZURE_OPENAI_API_VERSION, uses the AzureOpenAI client.
    Sign-in: API key, or Entra ID (no key, or AZURE_USE_ENTRA_ID=true): see entra.py. An identity on the machine (`az login`) is used
    first, otherwise a browser tab opens once and the account is remembered for the next starts.
    """

    def __init__(self, settings: LlmSettings):
        if not settings.configured:
            raise LlmError("LLM is not configured (endpoint, deployment and key or Entra ID are required)")
        self._s = settings
        self.model = settings.deployment
        self._client = None
        self._lock = threading.Lock()
        self._tls = threading.local()

    @property
    def last_usage(self) -> dict:
        """Token usage of the last call made by the calling thread."""
        return getattr(self._tls, "usage", {})

    def _build(self):
        from openai import AzureOpenAI, OpenAI  # imported late so rules-only setups start without the SDK

        s = self._s
        credential = s.api_key
        if s.use_entra_id and not s.api_key:
            from azure.identity import get_bearer_token_provider

            from .entra import build_credential

            # Sign in once, here: _build runs under the lock, so parallel agent calls wait for one sign-in (and one browser tab)
            # instead of each opening its own. A failure leaves no client behind, so the next call retries.
            credential = get_bearer_token_provider(build_credential(s), s.scope)
        if s.api_version:
            kw = {"azure_ad_token_provider": credential} if callable(credential) else {"api_key": credential}
            return AzureOpenAI(azure_endpoint=s.endpoint, api_version=s.api_version, timeout=s.timeout_seconds, max_retries=2, **kw)
        return OpenAI(base_url=f"{s.endpoint}/openai/v1/", api_key=credential, timeout=s.timeout_seconds, max_retries=2)

    def complete_json(self, system: str, user: str, *, tier: str | None = None, images: list[str] | None = None) -> dict:
        content: object = user
        if images:
            content = [{"type": "text", "text": user}] + [{"type": "image_url", "image_url": {"url": u}} for u in images]
        try:
            with self._lock:
                if self._client is None:
                    self._client = self._build()
            res = self._client.chat.completions.create(
                model=self._s.deployment_for("vision" if images else tier),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
                response_format={"type": "json_object"},
            )
        except LlmError:
            raise
        except Exception as e:  # SDK errors: auth, timeout, quota, unknown deployment, network ...
            raise LlmError(_describe(e)) from e
        usage = getattr(res, "usage", None)
        self._tls.usage = {"prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0, "completion_tokens": getattr(usage, "completion_tokens", 0) or 0}
        choice = res.choices[0] if res.choices else None
        content = choice.message.content if choice and choice.message else None
        if not content:
            raise LlmError("model returned an empty answer")
        return _parse_json(content)

    def web_search(self, query: str, *, instructions: str = "", tier: str | None = "standard") -> dict:
        """Search the public web with the Foundry web search tool (Responses API); no extra key or Bing resource is needed.

        Returns {"text": the model's answer, "sources": [{"url", "title"}], "queries": [...]}. The answer is a model-written summary of
        what it found; the sources are the pages it cites. Callers should treat the text as a summary, not as a quotation.
        """
        try:
            with self._lock:
                if self._client is None:
                    self._client = self._build()
            kw = {"instructions": instructions} if instructions else {}
            res = self._client.responses.create(model=self._s.deployment_for(tier), input=query, tools=[{"type": self._s.web_search_tool}], **kw)
        except LlmError:
            raise
        except Exception as e:  # noqa: BLE001
            raise LlmError(_describe(e)) from e
        usage = getattr(res, "usage", None)
        self._tls.usage = {"prompt_tokens": getattr(usage, "input_tokens", 0) or 0, "completion_tokens": getattr(usage, "output_tokens", 0) or 0}
        text = getattr(res, "output_text", "") or ""
        sources, queries, seen = [], [], set()
        for item in getattr(res, "output", None) or []:
            kind = getattr(item, "type", "")
            if kind == "web_search_call":
                action = getattr(item, "action", None)
                q = getattr(action, "query", None) if action is not None else None
                if q:
                    queries.append(q)
            for part in getattr(item, "content", None) or []:
                for ann in getattr(part, "annotations", None) or []:
                    if getattr(ann, "type", "") == "url_citation" and getattr(ann, "url", None) and ann.url not in seen:
                        seen.add(ann.url)
                        sources.append({"url": ann.url, "title": getattr(ann, "title", "") or ""})
        if not text.strip():
            raise LlmError("web search returned no text")
        return {"text": text.strip(), "sources": sources, "queries": queries}

    def ping(self) -> dict:
        """Tiny call used by GET /health/llm to check the connection and credentials."""
        started = time.perf_counter()
        data = self.complete_json("Reply with a JSON object.", 'Return {"ok": true}.')
        return {"ok": bool(data), "latency_ms": round((time.perf_counter() - started) * 1000)}


def _describe(e: Exception) -> str:
    """Short, key-free description of an SDK error."""
    name = e.__class__.__name__
    status = getattr(e, "status_code", None)
    detail = ""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            detail = str(err.get("message") or err.get("code") or "")
    detail = (detail or str(e)).replace("\n", " ")[:240]
    return f"{name}{f' {status}' if status else ''}: {detail}"
