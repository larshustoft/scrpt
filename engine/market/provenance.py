"""
Data trust discipline.

Marketing spend must rest only on data we can stand behind. Every figure in
the growth engine carries a source, and each source has a trust level:

    REPORTED  — from a file Amazon gave us (KDP royalty report, Ads report).
                Structured, downloaded, exact. Trustworthy.
    SET       — a value SCRPT itself controls (list price, word count, the
                keywords we chose). Known by definition. Trustworthy.
    ESTIMATE  — an assumption used until real data replaces it (e.g. a 3%
                conversion rate from published benchmarks). FLAGGED.
    SCRAPED   — read off a public web page (BSR, reviews, on-page price).
                Best-effort and often wrong. NEVER drives spend. FLAGGED.

The rule enforced below: a spend decision is only "safe" when its money inputs
are REPORTED or SET. If any critical input is an ESTIMATE or SCRAPED value, the
decision is marked unsafe and must not run automatically.
"""

REPORTED = "reported"
SET = "set"
ESTIMATE = "estimate"
SCRAPED = "scraped"

TRUSTWORTHY = {REPORTED, SET}


def field(value, source: str, note: str = "") -> dict:
    """Wrap a number with its provenance."""
    return {"value": value, "source": source, "trusted": source in TRUSTWORTHY,
            "note": note}


def safe_to_spend(*sources: str) -> bool:
    """True only when every input driving the decision is trustworthy."""
    return all(s in TRUSTWORTHY for s in sources)


def gate(reasons: list[str]) -> dict:
    """A verdict on whether an automatic spend action may proceed."""
    return {"safe": len(reasons) == 0, "blocking": reasons}
