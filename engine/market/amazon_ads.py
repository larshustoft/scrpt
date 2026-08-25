"""
Amazon Ads API client — campaigns SCRPT can create and steer directly.

Authorisation is OAuth through Login with Amazon: the publisher approves SCRPT
once on Amazon's own consent screen and Amazon returns a refresh token. SCRPT
never sees a password, and never touches a payment method — Amazon bills the
card on the Ads account, and the campaign's daily budget is the hard ceiling.

Settings used (engine settings table):
    ads_client_id, ads_client_secret   from the Login with Amazon security profile
    ads_refresh_token                  written by the OAuth exchange below
    ads_profile_id                     the KDP author advertising profile
    ads_region                         na | eu | fe   (default na)
"""

import gzip
import io
import json
import urllib.parse
from datetime import date, timedelta
from typing import Optional

import httpx

from ..database import get_connection, get_setting, set_setting

TOKEN_URL = "https://api.amazon.com/auth/o2/token"
AUTH_URL = "https://www.amazon.com/ap/oa"
HOSTS = {
    "na": "https://advertising-api.amazon.com",
    "eu": "https://advertising-api-eu.amazon.com",
    "fe": "https://advertising-api-fe.amazon.com",
}
SCOPES = "advertising::campaign_management"


def _cfg(key: str, default: str = "") -> str:
    return (get_setting(key, default) or default).strip()


def host() -> str:
    return HOSTS.get(_cfg("ads_region", "na") or "na", HOSTS["na"])


def configured() -> dict:
    return {
        "client_id": bool(_cfg("ads_client_id")),
        "client_secret": bool(_cfg("ads_client_secret")),
        "refresh_token": bool(_cfg("ads_refresh_token")),
        "profile_id": _cfg("ads_profile_id") or None,
        "region": _cfg("ads_region", "na") or "na",
    }


def authorize_url(redirect_uri: str) -> str:
    """The consent screen the publisher approves. No credentials pass through
    SCRPT — Amazon returns a one-time code to the redirect."""
    client_id = _cfg("ads_client_id")
    if not client_id:
        raise ValueError("Set ads_client_id in Settings first")
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "scope": SCOPES,
        "response_type": "code", "redirect_uri": redirect_uri})


async def exchange_code(code: str, redirect_uri: str) -> dict:
    """Trade the one-time code for a long-lived refresh token."""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(TOKEN_URL, data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect_uri,
            "client_id": _cfg("ads_client_id"),
            "client_secret": _cfg("ads_client_secret")})
    if r.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({r.status_code}): {r.text[:200]}")
    tok = r.json()
    set_setting("ads_refresh_token", tok.get("refresh_token", ""))
    return {"stored": bool(tok.get("refresh_token"))}


async def access_token() -> str:
    rt = _cfg("ads_refresh_token")
    if not rt:
        raise ValueError("SCRPT is not authorised for Amazon Ads yet")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(TOKEN_URL, data={
            "grant_type": "refresh_token", "refresh_token": rt,
            "client_id": _cfg("ads_client_id"),
            "client_secret": _cfg("ads_client_secret")})
    if r.status_code != 200:
        raise RuntimeError(f"Token refresh failed ({r.status_code}): {r.text[:200]}")
    return r.json()["access_token"]


async def _headers(with_profile: bool = True, content_type: str = "") -> dict:
    h = {"Amazon-Advertising-API-ClientId": _cfg("ads_client_id"),
         "Authorization": f"Bearer {await access_token()}"}
    if with_profile:
        pid = _cfg("ads_profile_id")
        if not pid:
            raise ValueError("No advertising profile selected yet")
        h["Amazon-Advertising-API-Scope"] = pid
    if content_type:
        h["Content-Type"] = content_type
        h["Accept"] = content_type
    return h


async def list_profiles() -> list[dict]:
    """Advertising profiles on the account (pick the KDP author one)."""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{host()}/v2/profiles",
                        headers=await _headers(with_profile=False))
    if r.status_code != 200:
        raise RuntimeError(f"Profiles failed ({r.status_code}): {r.text[:200]}")
    return r.json()


async def create_campaign(catalog: str, daily_budget: float, keywords: list[str],
                          bid: Optional[float] = None,
                          name: str = "", state: str = "PAUSED") -> dict:
    """Create a Sponsored Products campaign, ad group, product ad and keywords.

    Created PAUSED by default: nothing spends until it is deliberately enabled.
    """
    from ..database import get_book_by_catalog
    from .ads import bid_plan, save_plan

    book = get_book_by_catalog(catalog)
    if not book:
        raise ValueError("Book not found")
    asin = ((book["data"].get("publishing") or {}).get("asin")
            or book["data"].get("asin"))
    if not asin:
        raise ValueError("This book has no ASIN yet — sync the KDP bookshelf first")

    plan = bid_plan(catalog, daily_budget)
    bid = bid or plan["starting_bid"]
    name = name or f"SCRPT · {book['title'][:40]}"
    today = date.today().strftime("%Y-%m-%d")
    created: dict = {"plan": plan, "state": state}

    async with httpx.AsyncClient(timeout=60) as c:
        # 1. campaign
        r = await c.post(
            f"{host()}/sp/campaigns",
            headers=await _headers(content_type="application/vnd.spCampaign.v3+json"),
            json={"campaigns": [{
                "name": name, "targetingType": "MANUAL", "state": state,
                "budget": {"budgetType": "DAILY", "budget": round(daily_budget, 2)},
                "startDate": today,
                "dynamicBidding": {"strategy": "LEGACY_FOR_SALES"},
            }]})
        created["campaign_status"] = r.status_code
        if r.status_code >= 300:
            raise RuntimeError(f"Campaign create failed ({r.status_code}): {r.text[:300]}")
        camp = r.json()["campaigns"]["success"][0]
        campaign_id = camp["campaignId"]
        created["campaign_id"] = campaign_id

        # 2. ad group
        r = await c.post(
            f"{host()}/sp/adGroups",
            headers=await _headers(content_type="application/vnd.spAdGroup.v3+json"),
            json={"adGroups": [{"name": "Keywords", "campaignId": campaign_id,
                                "state": state, "defaultBid": round(bid, 2)}]})
        if r.status_code >= 300:
            raise RuntimeError(f"Ad group failed ({r.status_code}): {r.text[:300]}")
        ad_group_id = r.json()["adGroups"]["success"][0]["adGroupId"]
        created["ad_group_id"] = ad_group_id

        # 3. the book itself
        r = await c.post(
            f"{host()}/sp/productAds",
            headers=await _headers(content_type="application/vnd.spProductAd.v3+json"),
            json={"productAds": [{"campaignId": campaign_id,
                                  "adGroupId": ad_group_id,
                                  "asin": asin, "state": state}]})
        created["product_ad_status"] = r.status_code

        # 4. keywords, exact and phrase
        kw_payload = []
        for k in keywords[:200]:
            for match in ("EXACT", "PHRASE"):
                kw_payload.append({"campaignId": campaign_id,
                                   "adGroupId": ad_group_id,
                                   "keywordText": k, "matchType": match,
                                   "state": state, "bid": round(bid, 2)})
        if kw_payload:
            r = await c.post(
                f"{host()}/sp/keywords",
                headers=await _headers(content_type="application/vnd.spKeyword.v3+json"),
                json={"keywords": kw_payload})
            created["keywords_status"] = r.status_code
            created["keywords_created"] = len(kw_payload)

    save_plan(catalog, daily_budget, keywords)
    return created


async def set_campaign_state(campaign_id: str, state: str) -> dict:
    """ENABLED / PAUSED / ARCHIVED — how SCRPT stops a losing campaign."""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.put(
            f"{host()}/sp/campaigns",
            headers=await _headers(content_type="application/vnd.spCampaign.v3+json"),
            json={"campaigns": [{"campaignId": campaign_id, "state": state}]})
    return {"status": r.status_code, "body": r.text[:300]}


async def set_campaign_budget(campaign_id: str, daily_budget: float) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.put(
            f"{host()}/sp/campaigns",
            headers=await _headers(content_type="application/vnd.spCampaign.v3+json"),
            json={"campaigns": [{"campaignId": campaign_id,
                                 "budget": {"budgetType": "DAILY",
                                            "budget": round(daily_budget, 2)}}]})
    return {"status": r.status_code, "body": r.text[:300]}


async def sync_spend(days: int = 7) -> dict:
    """Pull campaign performance into ad_spend so the daily report and the
    budget allocator work from real numbers."""
    from .store import init as _init
    _init()
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    body = {
        "name": f"scrpt-{start}-{end}",
        "startDate": start.isoformat(), "endDate": end.isoformat(),
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "groupBy": ["campaign"],
            "columns": ["date", "campaignName", "campaignId", "cost",
                        "sales30d", "clicks", "impressions"],
            "reportTypeId": "spCampaigns",
            "timeUnit": "DAILY",
            "format": "GZIP_JSON",
        },
    }
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{host()}/reporting/reports",
                         headers=await _headers(
                             content_type="application/vnd.createasyncreportrequest.v3+json"),
                         json=body)
        if r.status_code >= 300:
            raise RuntimeError(f"Report request failed ({r.status_code}): {r.text[:300]}")
        report_id = r.json()["reportId"]

        import asyncio
        url = None
        for _ in range(30):                      # reports are generated async
            await asyncio.sleep(10)
            s = await c.get(f"{host()}/reporting/reports/{report_id}",
                            headers=await _headers())
            if s.status_code >= 300:
                continue
            doc = s.json()
            if doc.get("status") == "COMPLETED":
                url = doc.get("url")
                break
            if doc.get("status") == "FAILED":
                raise RuntimeError("Amazon reported a failure generating the report")
        if not url:
            return {"rows": 0, "note": "report still generating; try again shortly"}

        d = await c.get(url)
        raw = d.content

    try:
        rows = json.loads(gzip.decompress(raw).decode())
    except OSError:
        rows = json.loads(raw.decode())

    n = 0
    conn = get_connection()
    try:
        for row in rows:
            conn.execute(
                "INSERT OR REPLACE INTO ad_spend (day, campaign, spend, sales, "
                "clicks, impressions) VALUES (?,?,?,?,?,?)",
                (str(row.get("date"))[:10], str(row.get("campaignName", ""))[:120],
                 float(row.get("cost") or 0), float(row.get("sales30d") or 0),
                 int(row.get("clicks") or 0), int(row.get("impressions") or 0)))
            n += 1
        conn.commit()
    finally:
        conn.close()
    return {"rows": n, "from": start.isoformat(), "to": end.isoformat()}


async def list_campaigns() -> list[dict]:
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            f"{host()}/sp/campaigns/list",
            headers=await _headers(content_type="application/vnd.spCampaign.v3+json"),
            json={"maxResults": 500})
    if r.status_code >= 300:
        raise RuntimeError(f"Campaign list failed ({r.status_code}): {r.text[:200]}")
    return r.json().get("campaigns", [])


async def optimize(ceiling: float, window_days: int = 14,
                   min_spend_to_judge: float = 10.0,
                   apply_changes: bool = True) -> dict:
    """Steer spend toward what earns — inside a ceiling the publisher sets.

    Rules, deliberately asymmetric:
      * spend-REDUCING moves (pausing a campaign that loses money, cutting a
        budget) happen automatically — they can only save money;
      * spend-INCREASING moves are capped by `ceiling` and never exceed it.
    """
    from .ads import allocate, bid_plan

    plan = allocate(ceiling, window_days)
    campaigns = await list_campaigns()
    by_name = {c.get("name", ""): c for c in campaigns}

    conn = get_connection()
    try:
        perf = conn.execute(
            "SELECT campaign, SUM(spend), SUM(sales) FROM ad_spend "
            "WHERE day >= date('now', ?) GROUP BY campaign",
            (f"-{window_days} days",)).fetchall()
    finally:
        conn.close()

    actions = []
    for campaign_name, spend, sales in perf:
        c = by_name.get(campaign_name)
        if not c or not spend or spend < min_spend_to_judge:
            continue
        acos = (spend / sales) if sales else None
        # a campaign that has spent real money and returned nothing is paused
        if acos is None:
            actions.append({"campaign": campaign_name, "action": "pause",
                            "reason": f"${spend:.2f} spent, no attributed sales"})
            if apply_changes:
                await set_campaign_state(c["campaignId"], "PAUSED")
            continue
        # judge against what this book can actually afford
        target = 1.0
        for cat, budget in plan["allocation"].items():
            if cat and cat in campaign_name:
                try:
                    target = bid_plan(cat, budget)["break_even_acos"]
                except Exception:
                    pass
                break
        if acos > target * 1.25:
            actions.append({"campaign": campaign_name, "action": "pause",
                            "reason": f"ACOS {acos:.2f} above break-even {target:.2f}"})
            if apply_changes:
                await set_campaign_state(c["campaignId"], "PAUSED")

    # budgets: never above the ceiling in total
    total = 0.0
    for catalog, budget in plan["allocation"].items():
        c = next((v for k, v in by_name.items() if catalog and catalog in k), None)
        if not c:
            continue
        if total + budget > ceiling:
            budget = max(0.0, ceiling - total)
        total += budget
        if budget <= 0:
            continue
        # a budget change only applies automatically when the book's economics
        # rest on real data; otherwise it is proposed for the publisher, not run
        from .ads import bid_plan as _bp
        safe = True
        for cat in plan["allocation"]:
            if cat and cat in (c.get("name") or ""):
                try:
                    safe = _bp(cat, budget)["trust"]["safe"]
                except Exception:
                    safe = False
                break
        actions.append({"campaign": c.get("name"), "action": "budget",
                        "daily_budget": round(budget, 2),
                        "applied": bool(apply_changes and safe),
                        "held_for_review": bool(apply_changes and not safe)})
        if apply_changes and safe:
            await set_campaign_budget(c["campaignId"], budget)

    return {"ceiling": ceiling, "applied": apply_changes,
            "total_daily_allocated": round(total, 2),
            "actions": actions, "allocation": plan["allocation"]}
