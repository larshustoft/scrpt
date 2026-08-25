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

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

PROFILE_DIR = Path(os.path.expanduser("~/.scrpt/browser-profile"))

_STEALTH = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"

_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox",
         "--disable-dev-shm-usage"]


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
                user_agent=UA, viewport={"width": 1440, "height": 900},
                locale="en-US", timezone_id="America/New_York")
        else:
            self._browser = await self._pw.chromium.launch(
                headless=self.headless, args=_ARGS)
            self._ctx = await self._browser.new_context(
                user_agent=UA, viewport={"width": 1440, "height": 900},
                locale="en-US", timezone_id="America/New_York")
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
