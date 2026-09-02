"""One signal for "the money ran out", which nothing is allowed to swallow.

Every provider says it differently — OpenAI returns 429 insufficient_quota,
Anthropic returns 400 "credit balance is too low", Runway refuses a job —
and every one of those used to be caught by a broad `except Exception` and
turned into something that looked like ordinary failure: a picture that
"could not be drawn", a check that "could not be read". The line then did
the worst possible thing and retried, or redrew, or moved on quietly.

On 2026-09-01 an empty vision account was read as 146 bad pictures and the
line redrew all of them, twice, for nothing.

So: an empty account raises OutOfCredits, retry loops do not retry it,
gathers re-raise it, and the run stops immediately. Money can only be spent
while there is money to spend.
"""
from __future__ import annotations


class OutOfCredits(RuntimeError):
    """A provider has no credit left. Stop everything; do not retry."""

    def __init__(self, provider: str, where: str = "", detail: str = ""):
        self.provider = provider
        links = {
            "anthropic": "https://console.anthropic.com/settings/billing",
            "openai": "https://platform.openai.com/settings/organization/billing",
            "runway": "https://app.runwayml.com/settings/billing",
            "elevenlabs": "https://elevenlabs.io/app/subscription",
        }
        self.link = links.get(provider.lower(), "")
        super().__init__(
            f"{provider} has run out of credits"
            + (f" while {where}" if where else "")
            + " — the run has been stopped so that nothing more is spent."
            + (f" Top up: {self.link}" if self.link else "")
            + (f" ({detail[:120]})" if detail else ""))


# What each provider's refusal actually looks like on the wire.
_SIGNS = (
    "credit balance is too low",
    "insufficient_quota",
    "credit_balance_exhausted",
    "no credits remaining",
    "insufficient credits",
    "quota exceeded",
    "billing_hard_limit_reached",
)


def looks_broke(text) -> bool:
    """Is this error a provider saying the account is empty?"""
    t = str(text or "").lower()
    return any(s in t for s in _SIGNS)


def raise_if_broke(provider: str, status, text, where: str = ""):
    """Turn a provider's refusal into the one signal that stops the run."""
    try:
        code = int(status)
    except Exception:
        code = 0
    if code in (400, 402, 429) and looks_broke(text):
        raise OutOfCredits(provider, where, str(text))
