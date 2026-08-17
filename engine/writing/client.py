"""
Claude client for the writing engine.
Model is configurable per install (settings key: writing_model).
"""

import asyncio
import json
import re
from typing import Optional

from anthropic import AsyncAnthropic

from ..config import ANTHROPIC_API_KEY
from ..database import get_setting

DEFAULT_MODEL = "claude-sonnet-5"

_client: Optional[AsyncAnthropic] = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def writing_model() -> str:
    return get_setting("writing_model", DEFAULT_MODEL) or DEFAULT_MODEL


async def complete(
    system: str,
    user: str,
    max_tokens: int = 8000,
    retries: int = 3,
    web_search: int = 0,
) -> str:
    """One-shot completion with retry on transient errors.

    web_search > 0 enables the server-side web search tool with that many
    searches allowed — used by research stages so market claims are checked
    against the live web, not just training knowledge. Falls back to a plain
    completion if the API rejects the tool (older models / no access).
    """
    last_err = None
    kwargs = {}
    if web_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search",
                            "max_uses": web_search}]
    for attempt in range(retries):
        try:
            resp = await client().messages.create(
                model=writing_model(),
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                **kwargs,
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            if text.strip():
                return text
            # empty text usually means the budget went to internal reasoning
            # before any output — double the budget and try again
            last_err = RuntimeError(
                f"empty response (stop_reason={getattr(resp, 'stop_reason', '?')}, "
                f"max_tokens={max_tokens})")
            max_tokens = min(max_tokens * 2, 32000)
            continue
        except Exception as e:  # transient API errors: back off and retry
            last_err = e
            msg = str(e).lower()
            if kwargs.get("tools") and ("tool" in msg or "web_search" in msg) \
                    and "rate" not in msg:
                kwargs.pop("tools", None)  # tool unsupported — retry without
                continue
            await asyncio.sleep(2 ** attempt * 2)
    raise RuntimeError(f"Claude request failed after {retries} attempts: {last_err}")


async def complete_chat(
    system: str,
    messages: list[dict],
    max_tokens: int = 1200,
    retries: int = 2,
) -> str:
    """Multi-turn completion (assistant conversations)."""
    last_err = None
    for attempt in range(retries):
        try:
            resp = await client().messages.create(
                model=writing_model(),
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return "".join(b.text for b in resp.content if b.type == "text")
        except Exception as e:
            last_err = e
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"Claude chat failed: {last_err}")


def extract_json(text: str):
    """Pull the first JSON object/array out of a response, tolerating fences,
    prose, and truncation (salvages complete items from a cut-off array)."""
    fence = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", text, re.DOTALL)
    candidates = [fence.group(1)] if fence else []
    # widest brace/bracket span
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            return json.loads(cand, strict=False)
        except ValueError:
            continue
    # salvage a truncated response: from the first bracket, cut back to the
    # last complete object and close the array/object
    start = min((i for i in (text.find("["), text.find("{")) if i != -1), default=-1)
    if start != -1:
        frag = text[start:]
        for cut in range(len(frag), max(len(frag) - 20000, 0), -1):
            piece = frag[:cut].rstrip().rstrip(",")
            if not piece.endswith("}"):
                continue
            for closer in ("]", "}", "]}", "}]"):
                try:
                    return json.loads(piece + closer if piece[0] in "[{" else piece,
                                      strict=False)
                except ValueError:
                    continue
        # last resort: progressively truncate at object boundaries
        ends = [m.end() for m in re.finditer(r"\}", frag)]
        for e in reversed(ends):
            piece = frag[:e].rstrip().rstrip(",")
            try:
                return json.loads(piece + ("]" if frag[0] == "[" else ""),
                                  strict=False)
            except ValueError:
                continue
    raise ValueError(f"No parseable JSON in response: {text[:300]}")
