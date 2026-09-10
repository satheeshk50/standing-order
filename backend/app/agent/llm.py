"""Thin wrapper over LLM APIs (Google Gemini and Anthropic Claude).

1. ``LLM_MODE`` can be ``mock``, which swaps in a deterministic rule-based
   stand-in. The whole product — workflow, wake gate, tools, timeline, final
   report — runs end to end with no API key. That keeps the demo reproducible
   and lets a reviewer clone and run without credentials.

2. When live, Google Gemini (e.g. ``gemini-3.5-flash`` and
   ``gemini-3.5-flash-lite``), Groq (e.g. ``openai/gpt-oss-120b``) and
   Anthropic models are all supported, for both structured JSON and tool
   execution. The provider is chosen by model name, never by which key
   happens to be set.

3. ``FALLBACK_MODEL`` is a second provider tried once when the primary call
   fails. Two tiers of degradation therefore sit under every call: another
   vendor first, then the deterministic policy. A per-project quota or a
   single-vendor outage no longer silently turns the demo into the mock.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_anthropic_client = None


def is_live() -> bool:
    return settings.llm_live


def mode() -> str:
    return "live" if is_live() else "mock"


def _normalize_schema(s: Any) -> Any:
    """Normalize JSON schema types to uppercase for Gemini compatibility."""
    if not isinstance(s, dict):
        return s
    out = {}
    for k, v in s.items():
        if k == "additionalProperties":
            continue
        if k == "type" and isinstance(v, str):
            out[k] = v.upper()
        elif isinstance(v, dict):
            out[k] = _normalize_schema(v)
        elif isinstance(v, list):
            out[k] = [_normalize_schema(x) for x in v]
        else:
            out[k] = v
    return out


def _is_gemini(model: str) -> bool:
    """Route on the model name alone.

    Routing on *key presence* meant a template still holding a Claude model
    name was POSTed to Google's endpoint, which 404s on the model path and
    then degrades silently into the deterministic policy. The model name is
    the only honest signal for which provider owns a request.
    """
    return model.startswith("gemini-")


def _gemini_url(model: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
    )


def _gemini_headers() -> dict[str, str]:
    """Auth goes in a header, never the query string.

    httpx puts the full URL in every error it raises, and those messages are
    persisted to the activity timeline and rendered in the UI — a key in the
    query string leaks into the database and onto the screen.
    """
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; cannot call a Gemini model.")
    return {"x-goog-api-key": settings.gemini_api_key}


# --------------------------------------------------------------------------
# Groq - OpenAI-compatible chat completions. Serves as the fallback tier.
# --------------------------------------------------------------------------

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

#: Model families Groq serves. The configured fallback model always routes
#: here whatever its prefix, so changing FALLBACK_MODEL needs no code edit.
_GROQ_PREFIXES = (
    "llama",
    "mixtral",
    "gemma",
    "qwen",
    "deepseek",
    "moonshotai/",
    "openai/gpt-oss",
    "groq/",
)


def _is_groq(model: str) -> bool:
    return model.startswith(_GROQ_PREFIXES) or model == settings.fallback_model


def _groq_headers() -> dict[str, str]:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set; cannot call a Groq model.")
    return {"Authorization": f"Bearer {settings.groq_api_key}"}


def _groq_max_tokens(requested: int) -> int:
    """Clamp the output budget to the per-minute token ceiling.

    Groq bills ``max_tokens`` against the tokens-per-minute allowance as
    *reserved* capacity, not as tokens actually produced. Asking for the
    agent's full 8000 therefore reserves an entire minute's budget on the
    free tier and the next call in the same turn is rejected. A supervisor
    turn emits a few tool calls and a short summary, so a much smaller
    ceiling costs nothing in practice.
    """
    return min(requested, settings.groq_max_tokens)


async def _groq_post(client: httpx.AsyncClient, body: dict) -> dict:
    """POST to Groq, retrying once when the per-minute allowance is hit.

    Groq reports exactly how long the caller must wait, so a 429 is a pause
    rather than a failure. Without this a burst of events — which is the
    normal shape of an order timeline — drops turns onto the deterministic
    policy purely for pacing reasons.
    """
    for attempt in (1, 2):
        resp = await client.post(GROQ_URL, json=body, headers=_groq_headers())
        if resp.status_code != 429 or attempt == 2:
            resp.raise_for_status()
            return resp.json()

        delay = _retry_after_seconds(resp)
        log.warning(
            "groq rate limited; waiting %.1fs for the allowance to reset", delay
        )
        await asyncio.sleep(delay)

    raise RuntimeError("unreachable")


def _retry_after_seconds(resp: httpx.Response, default: float = 5.0) -> float:
    """Seconds to wait, from whichever header Groq populated."""
    raw = resp.headers.get("retry-after") or resp.headers.get(
        "x-ratelimit-reset-tokens"
    )
    if not raw:
        return default
    try:
        return min(float(raw), 30.0)
    except ValueError:
        pass
    # Durations arrive as e.g. "615ms", "7.66s", "2m30s".
    match = re.match(
        r"^(?:(?P<m>[\d.]+)m)?(?:(?P<s>[\d.]+)s)?(?:(?P<ms>[\d.]+)ms)?$", raw.strip()
    )
    if not match or not any(match.groupdict().values()):
        return default
    total = 0.0
    if match.group("m"):
        total += float(match.group("m")) * 60
    if match.group("s"):
        total += float(match.group("s"))
    if match.group("ms"):
        total += float(match.group("ms")) / 1000
    return min(max(total, 0.5), 30.0)


def _flatten_system(system: list[dict] | str) -> str:
    """Anthropic system blocks -> one string.

    Cache breakpoints are an Anthropic concept and have no meaning here, so
    the blocks are simply concatenated.
    """
    if isinstance(system, str):
        return system
    return "\n\n".join(
        b.get("text", "") for b in system if isinstance(b, dict) and "text" in b
    )


def _can_fallback(model: str) -> bool:
    """True when a fallback is configured and we are not already using it."""
    return bool(settings.groq_api_key) and model != settings.fallback_model


def _groq_tools(tools: list[dict]) -> list[dict]:
    """Anthropic-shaped tool definitions -> OpenAI function specs."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        }
        for t in tools
    ]


async def _complete_json_groq(
    *, model: str, system: str, user: str, schema: dict[str, Any], max_tokens: int
) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                # json_object mode guarantees valid JSON but not the shape,
                # so the schema is restated in the prompt.
                "content": (
                    f"{system}\n\nRespond with a single JSON object conforming "
                    f"to this JSON schema:\n{json.dumps(schema)}"
                ),
            },
            {"role": "user", "content": user},
        ],
        "max_tokens": _groq_max_tokens(max_tokens),
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        data = await _groq_post(client, body)
    choices = data.get("choices", [])
    if not choices:
        raise ValueError(f"Groq returned no choices: {data}")
    return json.loads(choices[0]["message"]["content"])


async def _run_groq_tool_loop(
    *,
    model: str,
    system: list[dict] | str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 8000,
    max_iterations: int = 6,
    execute_tool,
) -> tuple[str, list[dict]]:
    """Drives the multi-step tool calling loop against Groq."""
    convo: list[dict[str, Any]] = [
        {"role": "system", "content": _flatten_system(system)}
    ]
    for msg in messages:
        content = msg["content"]
        if not isinstance(content, str):
            content = "\n".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        convo.append({"role": msg["role"], "content": content})

    groq_tools = _groq_tools(tools)
    executed: list[dict] = []
    final_text = ""

    async with httpx.AsyncClient(timeout=60.0) as client:
        for _ in range(max_iterations):
            body = {
                "model": model,
                "messages": convo,
                "tools": groq_tools,
                "tool_choice": "auto",
                "max_tokens": _groq_max_tokens(max_tokens),
            }
            choices = (await _groq_post(client, body)).get("choices", [])
            if not choices:
                break

            message = choices[0].get("message", {})
            if message.get("content"):
                final_text = message["content"]

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                break

            convo.append(message)
            for call in tool_calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                call_id = call.get("id") or f"groq-{name}"
                try:
                    output = await execute_tool(name, args, call_id)
                    is_error = False
                except Exception as exc:
                    log.exception("tool %s failed", name)
                    output, is_error = f"Tool failed: {exc}", True

                executed.append(
                    {"id": call_id, "name": name, "input": args, "error": is_error}
                )
                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": str(output),
                    }
                )

    return final_text, executed


async def complete_json(
    *,
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """One structured-output call, with a cross-provider retry.

    A structured completion has no side effects, so a failed call is always
    safe to retry on the fallback provider.
    """
    try:
        return await _complete_json_once(
            model=model,
            system=system,
            user=user,
            schema=schema,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        if not _can_fallback(model):
            raise
        log.warning(
            "model %s failed (%s: %s); retrying on fallback %s",
            model,
            type(exc).__name__,
            exc,
            settings.fallback_model,
        )
        return await _complete_json_once(
            model=settings.fallback_model,
            system=system,
            user=user,
            schema=schema,
            max_tokens=max_tokens,
        )


async def _complete_json_once(
    *,
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """One structured-output call. Used by the wake-up classifier and final report."""
    if _is_gemini(model):
        url = _gemini_url(model)
        headers = _gemini_headers()
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": _normalize_schema(schema),
                "max_output_tokens": max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError(f"Gemini returned no candidates: {data}")
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if "text" in p)
            return json.loads(text)

    if _is_groq(model):
        return await _complete_json_groq(
            model=model,
            system=system,
            user=user,
            schema=schema,
            max_tokens=max_tokens,
        )

    # Anthropic Claude
    global _anthropic_client
    if _anthropic_client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                f"Model '{model}' is not a Gemini model and ANTHROPIC_API_KEY "
                "is not set. Point the supervisor template at a gemini-* model."
            )
        from anthropic import AsyncAnthropic

        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await _anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": schema,
            }
        },
    )
    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    return json.loads(text)


async def run_tool_loop(
    *,
    model: str,
    system: list[dict] | str,
    messages: list[dict],
    tools: list[dict],
    effort: str = "medium",
    max_tokens: int = 8000,
    max_iterations: int = 6,
    execute_tool,
):
    """Agentic tool loop, with a cross-provider retry.

    Unlike a structured completion, a tool loop has side effects: every
    business action it executes writes an activity row and is visible to an
    operator. Retrying after a tool has already run would duplicate those
    rows under a different tool-call id, defeating the idempotency key. So
    the fallback is only taken when the primary failed *before* executing
    anything; a mid-loop failure propagates to the deterministic policy.
    """
    executed_count = 0

    async def counting_execute(name, payload, call_id):
        nonlocal executed_count
        executed_count += 1
        return await execute_tool(name, payload, call_id)

    try:
        return await _run_tool_loop_once(
            model=model,
            system=system,
            messages=messages,
            tools=tools,
            effort=effort,
            max_tokens=max_tokens,
            max_iterations=max_iterations,
            execute_tool=counting_execute,
        )
    except Exception as exc:
        if executed_count or not _can_fallback(model):
            raise
        log.warning(
            "model %s failed before any tool ran (%s: %s); retrying on fallback %s",
            model,
            type(exc).__name__,
            exc,
            settings.fallback_model,
        )
        return await _run_tool_loop_once(
            model=settings.fallback_model,
            system=system,
            messages=messages,
            tools=tools,
            effort=effort,
            max_tokens=max_tokens,
            max_iterations=max_iterations,
            execute_tool=counting_execute,
        )


async def _run_tool_loop_once(
    *,
    model: str,
    system: list[dict] | str,
    messages: list[dict],
    tools: list[dict],
    effort: str = "medium",
    max_tokens: int = 8000,
    max_iterations: int = 6,
    execute_tool,
):
    """Manual agentic loop for tool calls."""
    if _is_gemini(model):
        return await _run_gemini_tool_loop(
            model=model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            max_iterations=max_iterations,
            execute_tool=execute_tool,
        )

    if _is_groq(model):
        return await _run_groq_tool_loop(
            model=model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            max_iterations=max_iterations,
            execute_tool=execute_tool,
        )

    # Anthropic Claude
    global _anthropic_client
    if _anthropic_client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                f"Model '{model}' is not a Gemini model and ANTHROPIC_API_KEY "
                "is not set. Point the supervisor template at a gemini-* model."
            )
        from anthropic import AsyncAnthropic

        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    executed: list[dict] = []
    convo = list(messages)

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "tools": tools,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort},
    }
    if model.startswith(("claude-opus-5", "claude-fable-5")):
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"

    final_text = ""
    for _ in range(max_iterations):
        create = (
            _anthropic_client.beta.messages.create
            if "betas" in kwargs
            else _anthropic_client.messages.create
        )
        response = await create(messages=convo, **kwargs)

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            final_text = (
                "The model declined this turn "
                f"({getattr(details, 'category', 'unknown')}). No action taken."
            )
            break

        text_parts = [
            b.text for b in response.content if getattr(b, "type", "") == "text"
        ]
        if text_parts:
            final_text = "\n".join(text_parts)

        tool_uses = [b for b in response.content if getattr(b, "type", "") == "tool_use"]
        if not tool_uses:
            break

        convo.append({"role": "assistant", "content": response.content})

        results = []
        for block in tool_uses:
            payload = dict(block.input) if isinstance(block.input, dict) else {}
            try:
                output = await execute_tool(block.name, payload, block.id)
                is_error = False
            except Exception as exc:
                log.exception("tool %s failed", block.name)
                output, is_error = f"Tool failed: {exc}", True
            executed.append(
                {"id": block.id, "name": block.name, "input": payload, "error": is_error}
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output),
                    "is_error": is_error,
                }
            )

        convo.append({"role": "user", "content": results})

    return final_text, executed


async def _run_gemini_tool_loop(
    *,
    model: str,
    system: list[dict] | str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 8000,
    max_iterations: int = 6,
    execute_tool,
) -> tuple[str, list[dict]]:
    """Drives the multi-step tool calling loop against Google Gemini."""
    url = _gemini_url(model)
    headers = _gemini_headers()

    # Extract plain system string
    system_text = ""
    if isinstance(system, list):
        system_text = "\n\n".join(
            b.get("text", "") for b in system if isinstance(b, dict) and "text" in b
        )
    elif isinstance(system, str):
        system_text = system

    # Convert tools to Gemini format
    gemini_tools = [
        {
            "function_declarations": [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": _normalize_schema(t.get("input_schema", {})),
                }
                for t in tools
            ]
        }
    ]

    # Convert messages to Gemini contents format
    contents: list[dict[str, Any]] = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        content_val = msg["content"]
        if isinstance(content_val, str):
            contents.append({"role": role, "parts": [{"text": content_val}]})
        elif isinstance(content_val, list):
            contents.append({"role": role, "parts": content_val})

    executed: list[dict] = []
    final_text = ""

    async with httpx.AsyncClient(timeout=60.0) as client:
        for step in range(max_iterations):
            body = {
                "system_instruction": {"parts": [{"text": system_text}]},
                "contents": contents,
                "tools": gemini_tools,
                "generationConfig": {
                    "max_output_tokens": max_tokens,
                },
            }
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates", [])
            if not candidates:
                break

            candidate_content = candidates[0].get("content", {})
            parts = candidate_content.get("parts", [])
            contents.append({"role": "model", "parts": parts})

            text_parts = [p.get("text", "") for p in parts if "text" in p]
            if text_parts:
                final_text = "\n".join(text_parts)

            function_calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not function_calls:
                break

            tool_responses = []
            for i, fc in enumerate(function_calls):
                tool_name = fc["name"]
                args = fc.get("args", {})
                call_id = f"gemini-step{step}-call{i}"
                try:
                    output = await execute_tool(tool_name, args, call_id)
                    is_error = False
                except Exception as exc:
                    log.exception("tool %s failed", tool_name)
                    output, is_error = f"Tool failed: {exc}", True

                executed.append(
                    {
                        "id": call_id,
                        "name": tool_name,
                        "input": args,
                        "error": is_error,
                    }
                )
                tool_responses.append(
                    {
                        "functionResponse": {
                            "name": tool_name,
                            "response": {"result": output, "error": is_error},
                        }
                    }
                )

            contents.append({"role": "user", "parts": tool_responses})

            # Terminate turn if outcome was recorded
            if any(fc["name"] == "record_turn_outcome" for fc in function_calls):
                break

    return final_text, executed

