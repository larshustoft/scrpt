"""
Growth engine API: keyword research, rank tracking, sales, ads, KDP, reports.
"""

from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from .. import database as db
from ..jobs import list_jobs, start_job
from ..market import ads as ads_mod
from ..market import kdp as kdp_mod
from ..market import keywords as kw
from ..market import rank as rank_mod
from ..market import report as report_mod
from ..market import sales as sales_mod
from ..market.store import init as market_init

router = APIRouter(prefix="/api/market", tags=["market"])


# ── keywords ─────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    seed: str
    store: str = "digital-text"      # digital-text | stripbooks | audible
    catalog: str = ""
    top_n: int = 25
    check_competition: int = 12


@router.post("/keywords/research")
async def keywords_research(req: ResearchRequest):
    """Mine Amazon's own autosuggest, size the competition, rank by opportunity."""
    market_init()

    async def job(handle):
        out = await kw.research(
            req.seed, req.store, req.top_n, req.check_competition,
            on_progress=lambda f, d: handle.progress(f, "research", d))
        out["kdp_slots"] = kw.kdp_slots(out["keywords"])
        conn = db.get_connection()
        try:
            import json
            conn.execute("INSERT INTO kw_studies (catalog, seed, store, result) "
                         "VALUES (?,?,?,?)",
                         (req.catalog or None, req.seed, req.store,
                          json.dumps(out)))
            conn.commit()
        finally:
            conn.close()
        return out

    return {"job_id": start_job("kw_research", job,
                                book_catalog=req.catalog or None)}


@router.get("/keywords/studies")
def keyword_studies(catalog: str = "", limit: int = 10):
    market_init()
    conn = db.get_connection()
    try:
        if catalog:
            rows = conn.execute(
                "SELECT id, seed, store, result, created_at FROM kw_studies "
                "WHERE catalog = ? ORDER BY id DESC LIMIT ?",
                (catalog, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, seed, store, result, created_at FROM kw_studies "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        import json
        return {"studies": [{"id": r[0], "seed": r[1], "store": r[2],
                             "result": json.loads(r[3] or "{}"),
                             "created_at": r[4]} for r in rows]}
    finally:
        conn.close()


class ApplyKeywords(BaseModel):
    keywords: list[str]
    categories: list[str] = []


@router.post("/keywords/apply/{catalog}")
def apply_keywords(catalog: str, req: ApplyKeywords):
    """Write the chosen slots onto the book, so the upload package carries them."""
    book = db.get_book_by_catalog(catalog)
    if not book:
        raise HTTPException(404, "Book not found")
    data = dict(book["data"])
    data["keywords"] = [k.strip() for k in req.keywords][:7]
    if req.categories:
        data["categories"] = req.categories[:3]
    db.update_book(book["id"], data)
    return {"keywords": data["keywords"], "categories": data.get("categories")}


# ── rank tracking ────────────────────────────────────────────────

@router.post("/rank/track")
async def rank_track():
    async def job(handle):
        return await rank_mod.track_all(
            on_progress=lambda f, d: handle.progress(f, "rank", d))
    return {"job_id": start_job("rank_track", job)}


@router.get("/rank/{catalog}")
def rank_history(catalog: str, days: int = 30):
    return {"catalog": catalog, "history": rank_mod.history(catalog, days)}


# ── sales & economics ────────────────────────────────────────────

@router.post("/sales/import")
async def sales_import(file: UploadFile = File(...)):
    content = await file.read()
    try:
        return sales_mod.import_report(content, file.filename or "report.xlsx")
    except Exception as e:
        raise HTTPException(400, f"Could not read that report: {e}")


@router.get("/sales/summary")
def sales_summary(days: int = 30):
    return sales_mod.summary(days)


@router.get("/economics/{catalog}")
def economics(catalog: str):
    try:
        return ads_mod.reader_value(catalog)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── advertising ──────────────────────────────────────────────────

@router.get("/ads/plan/{catalog}")
def ads_plan(catalog: str, daily_budget: float = 5.0):
    try:
        return ads_mod.bid_plan(catalog, daily_budget)
    except ValueError as e:
        raise HTTPException(404, str(e))


class CampaignRequest(BaseModel):
    daily_budget: float = 5.0
    keywords: list[str] = []
    campaign_name: str = ""


@router.post("/ads/bulk-sheet/{catalog}")
def ads_bulk_sheet(catalog: str, req: CampaignRequest):
    """A Sponsored Products bulk sheet, ready to upload in Amazon Ads."""
    keywords = req.keywords
    if not keywords:
        book = db.get_book_by_catalog(catalog)
        keywords = (book or {}).get("data", {}).get("keywords") or []
    if not keywords:
        raise HTTPException(400, "No keywords yet — run a keyword study first.")
    csv_text = ads_mod.bulk_sheet(catalog, keywords, req.daily_budget,
                                  campaign_name=req.campaign_name)
    ads_mod.save_plan(catalog, req.daily_budget, keywords)
    return Response(csv_text, media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{catalog}-ads.csv"'})


@router.post("/ads/import")
async def ads_import(file: UploadFile = File(...)):
    content = await file.read()
    try:
        return ads_mod.import_ads_report(content, file.filename or "ads.csv")
    except Exception as e:
        raise HTTPException(400, f"Could not read that ads report: {e}")


@router.get("/ads/allocate")
def ads_allocate(total_daily_budget: float = 20.0, days: int = 30):
    """Split the daily pot across the catalogue by what actually earns."""
    return ads_mod.allocate(total_daily_budget, days)


# ── the daily report ─────────────────────────────────────────────

@router.get("/report/daily")
def report_daily(day: str = ""):
    return report_mod.daily(day)


@router.get("/report/daily.txt", response_class=PlainTextResponse)
def report_daily_text(day: str = ""):
    return report_mod.as_text(report_mod.daily(day))


# ── KDP ──────────────────────────────────────────────────────────

@router.get("/kdp/status")
async def kdp_status():
    return await kdp_mod.session_status()


@router.post("/kdp/login")
async def kdp_login():
    """Open a visible window for the publisher to sign in. SCRPT never types
    credentials and never stores them."""
    return await kdp_mod.open_login()


@router.get("/kdp/bookshelf")
def kdp_bookshelf():
    """The last-synced KDP catalogue for display inside SCRPT."""
    return kdp_mod.stored_bookshelf()


@router.post("/kdp/sync-bookshelf")
async def kdp_sync():
    async def job(handle):
        handle.progress(0.2, "kdp", "Reading the KDP bookshelf")
        return await kdp_mod.sync_bookshelf()
    return {"job_id": start_job("kdp_sync", job)}


@router.post("/kdp/reports")
async def kdp_reports():
    async def job(handle):
        handle.progress(0.2, "kdp", "Downloading KDP reports")
        res = await kdp_mod.download_reports()
        imported = []
        for path in res.get("files", []):
            with open(path, "rb") as fh:
                imported.append(sales_mod.import_report(fh.read(), path))
        return {**res, "imported": imported}
    return {"job_id": start_job("kdp_reports", job)}


@router.post("/kdp/prepare-draft/{catalog}")
async def kdp_prepare(catalog: str):
    """Fill a new KDP title from the upload package and stop before Publish."""
    try:
        return await kdp_mod.prepare_draft(catalog)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Amazon Ads API ───────────────────────────────────────────────

from ..market import amazon_ads as aads  # noqa: E402


class AdsCredentials(BaseModel):
    client_id: str = ""
    client_secret: str = ""
    region: str = "na"


@router.get("/ads/api/status")
def ads_api_status():
    return aads.configured()


@router.post("/ads/api/credentials")
def ads_api_credentials(req: AdsCredentials):
    """Store the Login with Amazon application keys. These identify SCRPT to
    Amazon; they are not account credentials and carry no payment access."""
    if req.client_id:
        db.set_setting("ads_client_id", req.client_id.strip())
    if req.client_secret:
        db.set_setting("ads_client_secret", req.client_secret.strip())
    db.set_setting("ads_region", (req.region or "na").strip())
    return aads.configured()


@router.get("/ads/api/authorize-url")
def ads_api_authorize_url(redirect_uri: str = "https://localhost:8000/ads-callback"):
    try:
        return {"url": aads.authorize_url(redirect_uri), "redirect_uri": redirect_uri}
    except ValueError as e:
        raise HTTPException(400, str(e))


class AdsCode(BaseModel):
    code: str
    redirect_uri: str = "https://localhost:8000/ads-callback"


@router.post("/ads/api/exchange")
async def ads_api_exchange(req: AdsCode):
    try:
        return await aads.exchange_code(req.code.strip(), req.redirect_uri)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/ads/api/profiles")
async def ads_api_profiles():
    try:
        return {"profiles": await aads.list_profiles()}
    except Exception as e:
        raise HTTPException(400, str(e))


class ProfilePick(BaseModel):
    profile_id: str


@router.post("/ads/api/select-profile")
def ads_api_select_profile(req: ProfilePick):
    db.set_setting("ads_profile_id", req.profile_id.strip())
    return aads.configured()


class ApiCampaign(BaseModel):
    daily_budget: float = 5.0
    keywords: list[str] = []
    state: str = "PAUSED"
    name: str = ""


@router.post("/ads/api/campaign/{catalog}")
async def ads_api_campaign(catalog: str, req: ApiCampaign):
    """Create a live Sponsored Products campaign. PAUSED unless asked
    otherwise — nothing spends until it is deliberately enabled."""
    keywords = req.keywords or ((db.get_book_by_catalog(catalog) or {})
                                .get("data", {}).get("keywords") or [])
    if not keywords:
        raise HTTPException(400, "No keywords yet — run a keyword study first.")
    try:
        return await aads.create_campaign(catalog, req.daily_budget, keywords,
                                          name=req.name, state=req.state)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/ads/api/sync-spend")
async def ads_api_sync(days: int = 7):
    async def job(handle):
        handle.progress(0.2, "ads", "Requesting the campaign report")
        return await aads.sync_spend(days)
    return {"job_id": start_job("ads_sync", job)}


class Optimize(BaseModel):
    ceiling: float
    window_days: int = 14
    apply_changes: bool = False


@router.post("/ads/api/optimize")
async def ads_api_optimize(req: Optimize):
    """Steer spend within a ceiling. Dry run by default: pass apply_changes to
    let SCRPT actually pause losers and set budgets."""
    try:
        return await aads.optimize(req.ceiling, req.window_days,
                                   apply_changes=req.apply_changes)
    except Exception as e:
        raise HTTPException(400, str(e))


# ── autopilot ────────────────────────────────────────────────────

from ..market import ads_console as console  # noqa: E402
from ..market import autopilot as auto  # noqa: E402


class AutopilotConfig(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = None
    ads_ceiling: Optional[float] = None
    apply_ad_changes: Optional[bool] = None


@router.get("/autopilot")
def autopilot_status():
    return {**auto.settings(), "runs": auto.history(7)}


@router.post("/autopilot")
def autopilot_configure(req: AutopilotConfig):
    return auto.configure(req.enabled, req.hour, req.ads_ceiling,
                          req.apply_ad_changes)


@router.post("/autopilot/run")
async def autopilot_run():
    async def job(handle):
        handle.progress(0.1, "autopilot", "Running the daily cycle")
        return await auto.daily_cycle(force=True)
    return {"job_id": start_job("autopilot", job)}


@router.get("/ads/console/status")
async def ads_console_status():
    return await console.session_status()


@router.post("/ads/console/login")
async def ads_console_login():
    return await console.open_login()


@router.post("/ads/console/upload/{catalog}")
async def ads_console_upload(catalog: str, req: CampaignRequest):
    """Generate the bulk sheet and hand it to Amazon's uploader — no file
    ever touches the publisher's hands."""
    keywords = req.keywords or ((db.get_book_by_catalog(catalog) or {})
                                .get("data", {}).get("keywords") or [])
    if not keywords:
        raise HTTPException(400, "No keywords yet — run a keyword study first.")
    csv_text = ads_mod.bulk_sheet(catalog, keywords, req.daily_budget,
                                  campaign_name=req.campaign_name)
    ads_mod.save_plan(catalog, req.daily_budget, keywords)
    return await console.upload_bulk_sheet(csv_text, f"{catalog}-campaign.csv")


@router.post("/kdp/import-existing")
async def kdp_import_existing():
    """Bring the account's existing KDP books into SCRPT with real covers."""
    from ..market import import_kdp
    async def job(handle):
        handle.progress(0.1, "import", "Importing existing KDP books")
        res = await import_kdp.import_existing(
            on_progress=lambda f, d: handle.progress(0.1 + 0.8 * f, "import", d))
        return res
    return {"job_id": start_job("kdp_import", job)}


@router.get("/preflight/{catalog}")
def preflight(catalog: str):
    """Is this book ready to upload to KDP? Full pass/fail checklist."""
    from ..market import preflight as pf
    try:
        return pf.check(catalog)
    except ValueError as e:
        raise HTTPException(404, str(e))
