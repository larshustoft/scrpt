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
    temperature: float = 1.0,
    retries: int = 3,
) -> str:
    """One-shot completion with retry on transient errors."""
    last_err = None
    for attempt in range(retries):
        try:
            resp = await client().messages.create(
                model=writing_model(),
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(b.text for b in resp.content if b.type == "text")
        except Exception as e:  # transient API errors: back off and retry
            last_err = e
            await asyncio.sleep(2 ** attempt * 2)
    raise RuntimeError(f"Claude request failed after {retries} attempts: {last_err}")


def extract_json(text: str):
    """Pull the first JSON object/array out of a response, tolerating fences and prose."""
    fence = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", text, re.DOTALL)
    candidates = [fence.group(1)] if fence else []
    # fallback: widest brace/bracket span
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except ValueError:
            continue
    raise ValueError(f"No parseable JSON in response: {text[:300]}")
