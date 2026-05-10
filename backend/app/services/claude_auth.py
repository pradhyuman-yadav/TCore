from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

_CREDS_FILE = Path.home() / ".claude" / ".credentials.json"
_TOKEN_ENDPOINT = "https://claude.ai/oauth/token"
_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code OAuth client

# In-memory cache so we don't re-read disk every call
_cached_token: str = ""
_cached_expires_at: int = 0
_cached_refresh_token: str = ""


def _read_env() -> tuple[str, str, int] | None:
    token = os.environ.get("CLAUDE_ACCESS_TOKEN", "")
    refresh = os.environ.get("CLAUDE_REFRESH_TOKEN", "")
    expires = int(os.environ.get("CLAUDE_TOKEN_EXPIRES_AT", "0"))
    return (token, refresh, expires) if token else None


def _read_file() -> tuple[str, str, int] | None:
    try:
        data = json.loads(_CREDS_FILE.read_text(encoding="utf-8"))
        oauth = data.get("claudeAiOauth", {})
        token = oauth.get("accessToken", "")
        refresh = oauth.get("refreshToken", "")
        expires = int(oauth.get("expiresAt", 0))
        return (token, refresh, expires) if token else None
    except Exception:
        return None


def _is_expired(expires_at_ms: int) -> bool:
    if expires_at_ms == 0:
        return False
    return time.time() * 1000 > expires_at_ms - 60_000  # 1 min buffer


async def _do_refresh(refresh_token: str) -> tuple[str, str, int]:
    """Exchange refresh token for a new access token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _TOKEN_ENDPOINT,
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": _CLIENT_ID,
            },
            headers={"content-type": "application/json"},
        )
        resp.raise_for_status()
        body = resp.json()

    new_access: str = body["access_token"]
    new_refresh: str = body.get("refresh_token", refresh_token)
    expires_in: int = int(body.get("expires_in", 3600))
    new_expires_at = int(time.time() * 1000) + expires_in * 1000

    # Persist back to env so sibling requests in this process see the fresh token
    os.environ["CLAUDE_ACCESS_TOKEN"] = new_access
    os.environ["CLAUDE_REFRESH_TOKEN"] = new_refresh
    os.environ["CLAUDE_TOKEN_EXPIRES_AT"] = str(new_expires_at)

    return new_access, new_refresh, new_expires_at


async def get_access_token() -> str:
    """
    Returns a valid Claude OAuth access token.

    Priority:
      1. In-memory cache (avoids repeated I/O)
      2. Environment variables CLAUDE_ACCESS_TOKEN / CLAUDE_REFRESH_TOKEN / CLAUDE_TOKEN_EXPIRES_AT
         (set these in .env for Docker deployments)
      3. ~/.claude/.credentials.json  (local dev — populated by `claude login`)

    Refreshes automatically when the token is within 1 minute of expiry.
    Raises RuntimeError with a clear message if no credentials are available.
    """
    global _cached_token, _cached_expires_at, _cached_refresh_token

    # Fast path: cached and still valid
    if _cached_token and not _is_expired(_cached_expires_at):
        return _cached_token

    # Load from env or file
    creds = _read_env() or _read_file()
    if not creds:
        raise RuntimeError(
            "No Claude credentials found. "
            "For Docker: set CLAUDE_ACCESS_TOKEN in .env (run scripts/setup_claude_auth.ps1). "
            "For local dev: run `claude login`."
        )

    access_token, refresh_token, expires_at = creds

    if _is_expired(expires_at):
        if not refresh_token:
            raise RuntimeError(
                "Claude access token expired and no refresh token available. "
                "Re-run scripts/setup_claude_auth.ps1 or `claude login`."
            )
        try:
            access_token, refresh_token, expires_at = await _do_refresh(refresh_token)
        except Exception as exc:
            raise RuntimeError(
                f"Claude token refresh failed: {exc}. "
                "Re-run scripts/setup_claude_auth.ps1 to update credentials."
            ) from exc

    _cached_token = access_token
    _cached_refresh_token = refresh_token
    _cached_expires_at = expires_at
    return _cached_token
