"""
Local house password — auth for the installed (on-disk) edition of SCRPT.

One password for the machine, set once on first run, stored as a PBKDF2 hash
in the engine's own database. No accounts, no signup, no cloud dependency —
Supabase auth remains in the frontend for the hosted product later; the
frontend picks local mode via NEXT_PUBLIC_AUTH_MODE=local.

Sessions are opaque random tokens (kept to the last 10 issued, so signing in
on a new browser doesn't kill the desktop app's session).
"""

import hashlib
import hmac
import json
import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import database as db

router = APIRouter(prefix="/api/auth/local", tags=["auth"])

_ITERATIONS = 200_000
_MAX_TOKENS = 10


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), _ITERATIONS
    ).hex()


def _tokens() -> list:
    try:
        return json.loads(db.get_setting("local_auth_tokens", "[]") or "[]")
    except (TypeError, ValueError):
        return []


def _issue_token() -> str:
    token = secrets.token_hex(32)
    tokens = _tokens()
    tokens.append(token)
    db.set_setting("local_auth_tokens", json.dumps(tokens[-_MAX_TOKENS:]))
    return token


def _password_set() -> bool:
    return bool(db.get_setting("local_auth_salt"))


def _check(password: str) -> bool:
    salt = db.get_setting("local_auth_salt")
    stored = db.get_setting("local_auth_hash")
    if not salt or not stored:
        return False
    return hmac.compare_digest(_hash(password, salt), stored)


class PasswordRequest(BaseModel):
    password: str


class ChangeRequest(BaseModel):
    current_password: str
    new_password: str


class TokenRequest(BaseModel):
    token: str


@router.get("/status")
def status():
    return {"password_set": _password_set()}


@router.post("/setup")
def setup(req: PasswordRequest):
    """First-run only: set the house password. 409 once one exists."""
    if _password_set():
        raise HTTPException(409, "A password is already set")
    if len(req.password) < 8:
        raise HTTPException(400, "At least 8 characters")
    salt = secrets.token_hex(16)
    db.set_setting("local_auth_salt", salt)
    db.set_setting("local_auth_hash", _hash(req.password, salt))
    return {"token": _issue_token()}


@router.post("/login")
def login(req: PasswordRequest):
    if not _password_set():
        raise HTTPException(409, "No password set yet")
    if not _check(req.password):
        raise HTTPException(401, "Wrong password")
    return {"token": _issue_token()}


@router.post("/verify")
def verify(req: TokenRequest):
    return {"valid": req.token in _tokens()}


@router.post("/change")
def change(req: ChangeRequest):
    if not _check(req.current_password):
        raise HTTPException(401, "Current password is wrong")
    if len(req.new_password) < 8:
        raise HTTPException(400, "At least 8 characters")
    salt = secrets.token_hex(16)
    db.set_setting("local_auth_salt", salt)
    db.set_setting("local_auth_hash", _hash(req.new_password, salt))
    db.set_setting("local_auth_tokens", "[]")  # sign out everywhere else
    return {"token": _issue_token()}
