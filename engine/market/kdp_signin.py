"""KDP signs itself in (Lars, 2026-09-05: "We need a solution where you can
sign in yourself" — "a system where I give you my log in credentials in
settings of SCRPT").

The credentials live in the macOS Keychain, never in the database, never in
a log, never in a screenshot. The publisher types them once into Settings →
Amazon KDP; the engine writes them to the login keychain with `security`
and reads them back only at the moment Amazon shows a sign-in page.

Amazon's flow, as met in the wild:
  * /ap/signin with the account already chosen: password field only.
  * /ap/signin fresh: email, Continue, then password.
  * /ap/mfa: a one-time code. With an authenticator secret stored, the code
    is computed here (TOTP, RFC 6238); otherwise the run stops and says so.
  * /ap/cvf: a challenge (captcha or "approve on your phone") — a person.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import subprocess
import time

from ..database import get_setting, set_setting

SVC_PASSWORD = "scrpt-kdp-password"
SVC_TOTP = "scrpt-kdp-totp"


# ── keychain ────────────────────────────────────────────────────────
def _account() -> str:
    return (get_setting("kdp_email", "") or "").strip()


def _kc_get(service: str, account: str) -> str:
    if not account:
        return ""
    r = subprocess.run(["security", "find-generic-password", "-a", account, "-s", service, "-w"],
                       capture_output=True, text=True, timeout=15)
    return r.stdout.strip() if r.returncode == 0 else ""


def _kc_set(service: str, account: str, secret: str) -> None:
    subprocess.run(["security", "add-generic-password", "-U", "-a", account, "-s", service,
                    "-l", f"SCRPT KDP ({service.split('-')[-1]})", "-w", secret],
                   capture_output=True, text=True, timeout=15, check=True)


def _kc_delete(service: str, account: str) -> None:
    subprocess.run(["security", "delete-generic-password", "-a", account, "-s", service],
                   capture_output=True, text=True, timeout=15)


def credentials_status() -> dict:
    acct = _account()
    return {"email": acct, "has_password": bool(_kc_get(SVC_PASSWORD, acct)),
            "has_totp": bool(_kc_get(SVC_TOTP, acct)),
            "last_signin": get_setting("kdp_last_signin", "") or "",
            "last_signin_result": get_setting("kdp_last_signin_result", "") or ""}


def store_credentials(email: str, password: str = "", totp_secret: str = "") -> dict:
    email = (email or "").strip()
    if not email:
        raise ValueError("the KDP account email is needed")
    old = _account()
    if old and old != email:
        _kc_delete(SVC_PASSWORD, old); _kc_delete(SVC_TOTP, old)
    set_setting("kdp_email", email)
    if password:
        _kc_set(SVC_PASSWORD, email, password)
    if totp_secret:
        s = totp_secret.replace(" ", "").upper()
        totp_now(s)                       # must decode, or it is not a secret
        _kc_set(SVC_TOTP, email, s)
    return credentials_status()


def forget_credentials() -> dict:
    acct = _account()
    _kc_delete(SVC_PASSWORD, acct); _kc_delete(SVC_TOTP, acct)
    set_setting("kdp_last_signin_result", "")
    return credentials_status()


# ── totp ────────────────────────────────────────────────────────────
def totp_now(secret_b32: str, digits: int = 6, period: int = 30) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    counter = int(time.time()) // period
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


# ── the sign-in itself ──────────────────────────────────────────────
def _is_signin_url(url: str) -> bool:
    """Amazon's auth pages live under /ap/ on amazon.com. The PATH decides:
    a signed-in KDP page can carry 'signin' in its query (ref_=ap_signin),
    and matching on the whole url made a signed-in page look signed out."""
    from urllib.parse import urlparse
    u = urlparse(url)
    return u.path.startswith("/ap/") and "amazon." in u.netloc


async def _visible(page, sel: str) -> bool:
    try:
        loc = page.locator(sel).first
        return await loc.count() > 0 and await loc.is_visible()
    except Exception:
        return False


async def auto_signin(page, note=None) -> str:
    """Bring `page` from an Amazon sign-in page to a signed-in KDP page.
    Returns: signed_in · signed_in_after · no_credentials · otp_needed ·
    challenge · failed. Secrets never reach `note`."""
    def say(m):
        if note:
            note(m)
    if not _is_signin_url(page.url):
        return "signed_in"
    acct = _account()
    pw = _kc_get(SVC_PASSWORD, acct)
    if not (acct and pw):
        say("sign-in page, but no KDP password in the keychain (Settings → Amazon KDP)")
        return "no_credentials"
    totp = _kc_get(SVC_TOTP, acct)
    for attempt in range(4):
        url = page.url
        if not _is_signin_url(url):
            _mark("ok"); say("signed in")
            return "signed_in_after"
        if "/ap/cvf" in url or await _visible(page, "#auth-captcha-image, img[alt*='captcha' i]"):
            _mark("challenge"); say("Amazon shows a challenge (captcha or approve-on-phone) — a person must clear it")
            return "challenge"
        if "/ap/mfa" in url or await _visible(page, "#auth-mfa-otpcode"):
            if not totp:
                _mark("otp_needed"); say("Amazon asks for a one-time code and no authenticator secret is stored")
                return "otp_needed"
            await page.fill("#auth-mfa-otpcode", totp_now(totp))
            try:
                box = page.locator("#auth-mfa-remember-device").first
                if await box.count() and not await box.is_checked():
                    await box.check()
            except Exception:
                pass
            await page.locator("#auth-signin-button, input[type=submit]").first.click(timeout=10000)
            await page.wait_for_timeout(5000)
            continue
        # "Switch accounts": the chooser Amazon shows when the account is
        # remembered but the session has aged — pick the stored email's row
        if not await _visible(page, "#ap_password") and not await _visible(page, "#ap_email"):
            picked = await page.evaluate("""(mail) => {
                const cands = [...document.querySelectorAll('a, div[role=button], .a-row, li, button')]
                  .filter(e => e.offsetParent !== null && (e.innerText || '').toLowerCase().includes(mail.toLowerCase()) && (e.innerText || '').length < 200);
                if (!cands.length) return false;
                cands.sort((a, b) => a.innerText.length - b.innerText.length);
                const el = cands[0].closest('a') || cands[0].querySelector('a') || cands[0];
                el.click(); return true; }""", acct)
            if picked:
                say("account chooser: picked the stored account")
                await page.wait_for_timeout(4000)
                continue
        if await _visible(page, "#ap_email"):
            try:
                cur = await page.input_value("#ap_email")
            except Exception:
                cur = ""
            if not cur:
                await page.fill("#ap_email", acct)
            if await _visible(page, "#continue") and not await _visible(page, "#ap_password"):
                await page.locator("#continue").first.click(timeout=10000)
                await page.wait_for_timeout(3000)
                continue
        if await _visible(page, "#ap_password"):
            await page.fill("#ap_password", pw)
            try:
                box = page.locator("#auth-remember-me, input[name=rememberMe]").first
                if await box.count() and not await box.is_checked():
                    await box.check()
            except Exception:
                pass
            await page.locator("#signInSubmit, input#signInSubmit, input[type=submit]").first.click(timeout=10000)
            await page.wait_for_timeout(6000)
            if await _visible(page, "#auth-error-message-box, .a-alert-error"):
                try:
                    msg = (await page.locator("#auth-error-message-box, .a-alert-error").first.inner_text())[:120]
                except Exception:
                    msg = "sign-in error"
                _mark("failed: " + " ".join(msg.split())[:80]); say("Amazon refused the sign-in: " + " ".join(msg.split())[:80])
                return "failed"
            continue
        # a sign-in url with none of the known fields: give it a moment
        await page.wait_for_timeout(2500)
    if not _is_signin_url(page.url):
        _mark("ok"); say("signed in")
        return "signed_in_after"
    _mark("failed: still on " + page.url.split("?")[0][:60]); say("still on a sign-in page after four tries")
    return "failed"


def _mark(result: str) -> None:
    try:
        from datetime import datetime
        set_setting("kdp_last_signin", datetime.now().isoformat(timespec="minutes"))
        set_setting("kdp_last_signin_result", result)
    except Exception:
        pass


async def signin_test() -> dict:
    """Open the engine's own KDP window on a page that demands a fresh
    sign-in, let auto_signin work, report — no secrets in the report."""
    from playwright.async_api import async_playwright
    from .browser import PROFILE_DIR, _ARGS, _STEALTH, context_kwargs
    st = credentials_status()
    if not st["has_password"]:
        return {"ok": False, "result": "no_credentials", **st}
    log: list[str] = []
    pw_ = await async_playwright().start()
    ctx = await pw_.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False, args=_ARGS,
                                                       **context_kwargs(viewport={"width": 1400, "height": 900}))
    try:
        await ctx.add_init_script(_STEALTH)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        # title setup always re-authenticates (max_auth_age=0): the real test
        await page.goto("https://kdp.amazon.com/en_US/title-setup/paperback/new/details", timeout=60000,
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        r = await auto_signin(page, log.append)
        if r == "signed_in":
            _mark("ok")
        url = page.url
        if r in ("signed_in", "signed_in_after") and "/title-setup/" in url:
            # leave no half-made title behind: back to the bookshelf without saving
            await page.goto("https://kdp.amazon.com/en_US/bookshelf", timeout=60000, wait_until="domcontentloaded")
        return {"ok": r in ("signed_in", "signed_in_after"), "result": r, "url": url.split("?")[0][:120], "log": log,
                **credentials_status()}
    finally:
        try:
            await ctx.close()
        finally:
            await pw_.stop()
