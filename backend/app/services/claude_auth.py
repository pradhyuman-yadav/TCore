from __future__ import annotations

import os


async def get_auth_headers() -> dict[str, str]:
    """
    Returns auth headers for direct Anthropic API calls.
    Only used when CLAUDE_PROXY_URL is not set (fallback path).
    Primary path is the external Claude proxy — no auth headers needed there.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        return {"x-api-key": api_key}

    raise RuntimeError(
        "No Claude config. Set CLAUDE_PROXY_URL (proxy) or ANTHROPIC_API_KEY (direct)."
    )
