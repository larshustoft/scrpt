"""
Amazon Ads console automation — the fallback that removes the upload step
when API access isn't available.

Same rules as the KDP work: SCRPT never types credentials (the publisher signs
in once in a visible window, and the session lives in the persistent profile),
and campaigns land PAUSED so nothing spends unattended.
"""

import tempfile
from pathlib import Path

from .browser import Page

CONSOLE = "https://advertising.amazon.com/"
BULK = "https://advertising.amazon.com/bulk-operations"


async def session_status() -> dict:
    try:
        async with Page(persistent=True) as page:
            await page.goto(CONSOLE, timeout=60000, wait_until="domcontentloaded")
            url = page.url
            return {"signed_in": "signin" not in url and "ap/signin" not in url,
                    "url": url}
    except Exception as e:
        return {"signed_in": False, "error": str(e)[:200]}


async def open_login() -> dict:
    """Visible window for the publisher to sign in to Amazon Ads once."""
    from playwright.async_api import async_playwright
    from .browser import PROFILE_DIR, _ARGS, _STEALTH, context_kwargs
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(
        str(PROFILE_DIR), headless=False, args=_ARGS, **context_kwargs())
    await ctx.add_init_script(_STEALTH)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(CONSOLE, timeout=60000)
    return {"opened": True,
            "instruction": "Sign in to Amazon Ads in the window that opened, "
                           "then close it. SCRPT reuses that session."}


async def upload_bulk_sheet(csv_text: str, filename: str = "scrpt-campaign.csv",
                            headless: bool = True) -> dict:
    """Hand a generated bulk sheet to Amazon's bulk-operations uploader."""
    tmp = Path(tempfile.gettempdir()) / filename
    tmp.write_text(csv_text, encoding="utf-8")
    async with Page(persistent=True, headless=headless) as page:
        await page.goto(BULK, timeout=60000, wait_until="domcontentloaded")
        if "signin" in page.url:
            return {"signed_in": False,
                    "message": "Sign in to Amazon Ads first."}
        await page.wait_for_timeout(3000)
        try:
            file_input = page.locator("input[type='file']").first
            await file_input.wait_for(timeout=20000)
            await file_input.set_input_files(str(tmp))
        except Exception as e:
            return {"signed_in": True, "uploaded": False,
                    "error": f"No file control found on the bulk page: {e}"[:200],
                    "file": str(tmp)}
        # the console shows an explicit upload/submit control once a file is set
        for name in ("upload", "submit", "apply"):
            try:
                btn = page.get_by_role("button", name=lambda n, x=name: n and x in n.lower())
                if await btn.count():
                    await btn.first.click()
                    break
            except Exception:
                continue
        await page.wait_for_timeout(6000)
        body = (await page.content()).lower()
    return {"signed_in": True, "uploaded": True, "file": str(tmp),
            "amazon_reported_error": "error" in body and "no error" not in body,
            "note": "Campaigns arrive paused; enable them when you are ready."}
