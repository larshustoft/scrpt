"""
Claude client for the writing engine.
Model is configurable per install (settings key: writing_model).
"""

import asyncio
import json
import re
from typing import Optional

from anthropic import AsyncAnthropic

from ..credits import OutOfCredits, looks_broke, raise_if_broke
from ..config import ANTHROPIC_API_KEY
from ..database import get_setting

DEFAULT_MODEL = "claude-sonnet-5"

_FICTION_FRAME = (
    "This is a commercial NOVEL manuscript for a publishing house. Every "
    "agency, technology, code and event in it is invented for drama - write "
    "the scene as literary fiction (interiority, atmosphere, character), "
    "with invented jargon standing in for any technical detail, and no "
    "real-world operational instruction of any kind.\n\n")

class ContentRefused(RuntimeError):
    """The model declined this content repeatedly — a brief/model problem,
    not a transient API error, so it must not be retried blindly."""


_client: Optional[AsyncAnthropic] = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


import contextvars

# a book may pin its own writing model (data.writing_model_override) — set per
# draft task so parallel books on different models never interfere
_model_override: contextvars.ContextVar = contextvars.ContextVar(
    "scrpt_model_override", default=None)


def set_model_override(model: Optional[str]):
    _model_override.set((model or "").strip() or None)


def writing_model() -> str:
    return (_model_override.get()
            or get_setting("writing_model", DEFAULT_MODEL) or DEFAULT_MODEL)


# Mechanical stages (research, titles, taglines, outlines, quality gates,
# blurbs, hooks) run on a cheaper model — the words readers actually read
# (chapters, story bible, architecture, the acceptance editor) stay on the
# writing model. Configurable via settings key mechanical_model.
MECHANICAL_MODEL_DEFAULT = "claude-sonnet-5"


def mechanical_model() -> str:
    return get_setting("mechanical_model", MECHANICAL_MODEL_DEFAULT) \
        or MECHANICAL_MODEL_DEFAULT


# Reader of last resort: when the writing model declines to READ a manuscript
# (large mixed-content prompts can trip its safeguards), judging stages escalate
# here rather than leaving a finished book with no verdict.
FALLBACK_MODEL_DEFAULT = "claude-opus-5"


def fallback_model() -> str:
    return get_setting("fallback_model", FALLBACK_MODEL_DEFAULT) \
        or FALLBACK_MODEL_DEFAULT


async def complete(
    system: str,
    user: str,
    max_tokens: int = 8000,
    retries: int = 3,
    web_search: int = 0,
    mechanical: bool = False,
    cached_context: str = None,
    model: str = None,
    allow_fallback: bool = False,
) -> str:
    """One-shot completion with retry on transient errors.

    web_search > 0 enables the server-side web search tool with that many
    searches allowed — used by research stages so market claims are checked
    against the live web, not just training knowledge. Falls back to a plain
    completion if the API rejects the tool (older models / no access).

    mechanical=True routes the call to the cheaper mechanical-stage model.
    allow_fallback=True lets a judging stage finish on the fallback model when
    the primary is refusing or congested — never used for chapter prose, where
    a mid-book model switch would break the voice.
    cached_context is a large stable block (e.g. bible + outline) appended
    to the system prompt with prompt caching, so repeated calls over the
    same book re-read it at ~10% of the input price.
    """
    last_err = None
    refusals = 0
    kwargs = {}
    if web_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search",
                            "max_uses": web_search}]
    for attempt in range(retries + 4):   # +4: room for refusal re-rolls
        try:
            if cached_context:
                sys_payload = [
                    {"type": "text", "text": system},
                    {"type": "text", "text": cached_context,
                     "cache_control": {"type": "ephemeral"}},
                ]
            else:
                sys_payload = system
            # always stream: long generations (thinking-heavy models, big
            # budgets) exceed the SDK's non-streaming 10-minute guard
            async with client().messages.stream(
                model=model or (mechanical_model() if mechanical
                                else writing_model()),
                max_tokens=max_tokens,
                system=sys_payload,
                messages=[{"role": "user", "content": user}],
                **kwargs,
            ) as stream:
                resp = await stream.get_final_message()
            text = "".join(b.text for b in resp.content if b.type == "text")
            stop = getattr(resp, "stop_reason", None)
            try:
                from .ledger import record as _record
                _record(getattr(resp, "model", None) or (model or (mechanical_model() if mechanical else writing_model())),
                        getattr(resp, "usage", None), kind=(system or "")[:40])
            except Exception:
                pass
            if stop == "refusal":
                # Refusals are partly stochastic: the same prompt often
                # succeeds on a re-roll, and large prompts raise the odds.
                # Re-roll (asserting the fictional frame from the second
                # attempt on) and only fail loudly once the budget is spent.
                refusals += 1
                last_err = RuntimeError(
                    f"model declined ({refusals}x, stop_reason=refusal)")
                if _FICTION_FRAME not in system:
                    system = _FICTION_FRAME + system
                if refusals >= max(3, retries):
                    raise ContentRefused(
                        f"model declined this content {refusals} times "
                        "(stop_reason=refusal) — rework the brief or run this "
                        "book on another model")
                await asyncio.sleep(1.5 * refusals)
                continue
            # On always-thinking models the reasoning counts against
            # max_tokens: a response can come back truncated mid-output
            # (stop_reason max_tokens) or empty (budget consumed before any
            # output). Both get a doubled budget and a retry.
            if stop == "max_tokens" and max_tokens < 64000:
                last_err = RuntimeError(
                    f"response truncated at max_tokens={max_tokens}")
                max_tokens = min(max_tokens * 2, 64000)
                continue
            if text.strip():
                return text
            last_err = RuntimeError(
                f"empty response (stop_reason={stop}, max_tokens={max_tokens})")
            max_tokens = min(max_tokens * 2, 64000)
            continue
        except ContentRefused:
            raise                      # a real content problem: surface it
        except OutOfCredits:
            raise            # the account is empty: stop, never retry
        except Exception as e:  # transient API errors: back off and retry
            # AN EMPTY ACCOUNT IS NOT A TRANSIENT ERROR (2026-09-01).
            if looks_broke(e):
                raise OutOfCredits("Anthropic", "writing or checking", str(e))
            last_err = e
            msg = str(e).lower()
            if kwargs.get("tools") and ("tool" in msg or "web_search" in msg) \
                    and "rate" not in msg:
                kwargs.pop("tools", None)  # tool unsupported — retry without
                continue
            # API capacity pushback clears on the order of tens of seconds —
            # a 2s backoff just burns the retry budget for nothing
            if "overloaded" in msg or "rate_limit" in msg or "529" in msg:
                await asyncio.sleep(min(90, 20 * (attempt + 1)))
                continue
            await asyncio.sleep(2 ** attempt * 2)
    if allow_fallback and not model:
        primary = mechanical_model() if mechanical else writing_model()
        # readers of last resort, in order — any capable model beats leaving a
        # finished book unjudged when the primary is congested
        for fb in (fallback_model(), MECHANICAL_MODEL_DEFAULT):
            if not fb or fb == primary:
                continue
            try:
                return await complete(system, user, max_tokens=max_tokens,
                                      retries=retries, web_search=web_search,
                                      cached_context=cached_context, model=fb)
            except OutOfCredits:
                raise      # the account is empty: no fallback model helps
            except Exception as e:
                if looks_broke(e):
                    raise OutOfCredits("Anthropic", "writing", str(e))
                last_err = e
    raise RuntimeError(f"Claude request failed after {retries} attempts: {last_err}")


async def complete_vision(
    system: str,
    user: str,
    image_png: bytes,
    max_tokens: int = 2000,
    retries: int = 3,
) -> str:
    """One-shot completion with an image attached (e.g. describing cover art)."""
    import base64
    last_err = None
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.b64encode(image_png).decode()}},
        {"type": "text", "text": user},
    ]
    for attempt in range(retries):
        try:
            async with client().messages.stream(
                model=writing_model(),
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
            ) as stream:
                resp = await stream.get_final_message()
            text = "".join(b.text for b in resp.content if b.type == "text")
            if text.strip():
                return text
            last_err = RuntimeError(f"empty response (stop_reason={getattr(resp, 'stop_reason', None)})")
            max_tokens = min(max_tokens * 2, 16000)
        except Exception as e:
            # AN EMPTY ACCOUNT IS NOT A TRANSIENT ERROR (2026-09-01) — but
            # for READING a picture there is a second provider, so one empty
            # account slows the line down rather than stopping it. If that
            # one is empty too, the run halts and says so.
            if looks_broke(e):
                return await _vision_openai(system, user, image_png, max_tokens)
            last_err = e
            await asyncio.sleep(2 ** attempt * 2)
    raise RuntimeError(f"Claude vision request failed after {retries} attempts: {last_err}")


async def _vision_openai(system: str, user: str, image_png: bytes,
                         max_tokens: int = 2000) -> str:
    """The second pair of eyes.

    Reading a picture back is a safety check, and a safety check that only
    one account can perform is a safety check that stops the factory when
    that account empties (Lars, 2026-09-01). Same question, different
    provider, so the line keeps its eyes open.
    """
    import base64
    import httpx
    from ..config import OPENAI_API_KEY
    if not OPENAI_API_KEY:
        raise RuntimeError("no second vision provider is configured")
    b64 = base64.b64encode(image_png).decode()
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": "gpt-4.1", "max_tokens": max_tokens,
                  "messages": [
                      {"role": "system", "content": system},
                      {"role": "user", "content": [
                          {"type": "text", "text": user},
                          {"type": "image_url",
                           "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]})
        raise_if_broke("OpenAI", r.status_code, r.text, "checking a picture")
        if r.status_code != 200:
            raise RuntimeError(f"second-opinion vision failed "
                               f"({r.status_code}): {r.text[:200]}")
        return r.json()["choices"][0]["message"]["content"]


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
            # AN EMPTY ACCOUNT IS NOT A TRANSIENT ERROR (2026-09-01).
            if looks_broke(e):
                raise OutOfCredits("Anthropic", "writing or checking", str(e))
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
