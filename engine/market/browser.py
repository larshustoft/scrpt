"""
Shared browser layer for the growth engine.

Amazon fingerprints plain headless Chromium and serves a stub page, so every
market request goes through a stealth context. Two profiles:

  ephemeral  — throwaway context for public pages (search, product, categories)
  session    — a PERSISTENT profile at ~/.scrpt/browser-profile that keeps the
               publisher's own logins (KDP). SCRPT never types credentials:
               the publisher signs in once, by hand, in a visible window.
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

# No user-agent override. Real Chrome sends Sec-CH-UA client hints carrying its
# true version; a spoofed UA claiming an older Chrome contradicts them, and that
# mismatch is a louder automation signal than sending nothing at all.

# The publisher's own machine and network. A browser claiming a US timezone from
# a French IP reads as a proxy — which is how KDP sessions were being burned.
LOCALE = "en-US"
TIMEZONE = "Europe/Paris"

PROFILE_DIR = Path(os.path.expanduser("~/.scrpt/browser-profile"))

_STEALTH = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"

# --no-sandbox and --disable-dev-shm-usage are container workarounds that do
# nothing on a Mac and are passed by almost nothing except automation.
_ARGS = ["--disable-blink-features=AutomationControlled"]

# Real Chrome, not Playwright's bundled Chrome for Testing. The testing build is
# distinguishable from the shipping one, and KDP re-challenges it hard.
CHANNEL = "chrome"


def context_kwargs(**over) -> dict:
    """The one fingerprint every launch site shares.

    Several modules open their own window on this same profile. If they don't
    agree — one sending a spoofed user-agent, another the real one — Amazon
    sees a single session whose client keeps changing, which is a worse signal
    than any of them alone. So the settings live here and nowhere else.
    """
    kw = {"channel": CHANNEL, "viewport": {"width": 1440, "height": 900},
          "locale": LOCALE, "timezone_id": TIMEZONE}
    kw.update(over)
    return kw


class Page:
    """Async context manager yielding a ready page, closing everything after."""

    def __init__(self, persistent: bool = False, headless: bool = True):
        self.persistent = persistent
        self.headless = headless
        self._pw = None
        self._browser = None
        self._ctx = None

    async def __aenter__(self):
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        if self.persistent:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            self._ctx = await self._pw.chromium.launch_persistent_context(
                str(PROFILE_DIR), headless=self.headless, args=_ARGS,
                channel=CHANNEL, viewport={"width": 1440, "height": 900},
                locale=LOCALE, timezone_id=TIMEZONE)
        else:
            self._browser = await self._pw.chromium.launch(
                headless=self.headless, args=_ARGS, channel=CHANNEL)
            self._ctx = await self._browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale=LOCALE, timezone_id=TIMEZONE)
        await self._ctx.add_init_script(_STEALTH)
        pages = self._ctx.pages
        return pages[0] if pages else await self._ctx.new_page()

    async def __aexit__(self, *exc):
        try:
            if self._ctx:
                await self._ctx.close()
            if self._browser:
                await self._browser.close()
        finally:
            if self._pw:
                await self._pw.stop()


async def fetch_html(url: str, wait: str = "domcontentloaded",
                     timeout: int = 45000) -> str:
    async with Page() as page:
        await page.goto(url, timeout=timeout, wait_until=wait)
        return await page.content()
