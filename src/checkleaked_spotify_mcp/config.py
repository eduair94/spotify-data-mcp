"""Configuration from the environment.

Nothing here raises: a missing key or a bad provider is recorded in
``Settings.error`` so the server still starts and every tool can explain the
problem to the user.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional

TRIAL_URL = "https://spotify.checkleaked.cc/pricing#trial"
RAPIDAPI_URL = "https://rapidapi.com/airaudoeduardo/api/spotify81"
RAPIDAPI_PRICING_URL = "https://rapidapi.com/airaudoeduardo/api/spotify81/pricing"
PRICING_URL = "https://spotify.checkleaked.cc/pricing"
STATUS_URL = "https://spotify.checkleaked.cc/status"

GET_A_KEY = (
    "Get a key: a free trial (500 requests over 7 days, no card) at "
    f"{TRIAL_URL}, the free Basic plan of the RapidAPI listing at {RAPIDAPI_URL}, "
    f"or a paid key at {PRICING_URL}."
)

MISSING_KEY_MESSAGE = (
    "SPOTIFY_API_KEY is not set, so this server cannot call the Spotify Data API. "
    + GET_A_KEY
    + " Then add SPOTIFY_API_KEY to this server's env in your MCP client "
    "configuration and restart the server."
)

# Keys issued by spotify.checkleaked.cc: `sapi_<64 hex>` (and UUIDs from older
# portals). RapidAPI keys look nothing like either.
_DIRECT_KEY_RE = re.compile(
    r"^(?:sapi_[0-9a-f]{16,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    re.IGNORECASE,
)

_PROVIDER_ALIASES = {
    "rapidapi": "rapidapi",
    "rapid": "rapidapi",
    "direct": "direct",
    "proxy": "direct",
    "checkleaked": "direct",
}


@dataclass(frozen=True)
class Settings:
    """Resolved server configuration."""

    api_key: Optional[str]
    #: ``rapidapi`` or ``direct``.
    provider: str
    #: How ``provider`` was chosen: ``env`` (SPOTIFY_API_PROVIDER), ``key``
    #: (detected from a direct key's format) or ``default``.
    provider_source: str
    base_url: Optional[str] = None
    #: A configuration problem every tool reports instead of calling the API.
    error: Optional[str] = None

    @property
    def sdk_provider(self) -> str:
        """The provider name the checkleaked-spotify-api SDK expects."""

        return "proxy" if self.provider == "direct" else "rapidapi"


def _clean(value: Optional[str]) -> str:
    text = (value or "").strip()
    # A value pasted with its quotes ("abc" or 'abc') still works.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def looks_like_direct_key(key: str) -> bool:
    return bool(_DIRECT_KEY_RE.match(key))


def load_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    """Read SPOTIFY_API_KEY, SPOTIFY_API_PROVIDER and SPOTIFY_API_BASE."""

    env = os.environ if env is None else env
    api_key = _clean(env.get("SPOTIFY_API_KEY")) or None
    raw_provider = _clean(env.get("SPOTIFY_API_PROVIDER")).lower()
    base_url = _clean(env.get("SPOTIFY_API_BASE")).rstrip("/") or None

    error: Optional[str] = None
    if raw_provider:
        provider = _PROVIDER_ALIASES.get(raw_provider, "")
        source = "env"
        if not provider:
            provider = "rapidapi"
            error = (
                f"SPOTIFY_API_PROVIDER={raw_provider!r} is not valid. Use 'rapidapi' "
                "for a RapidAPI key or 'direct' for a key from spotify.checkleaked.cc "
                "(or leave it unset to detect it from the key)."
            )
    elif api_key and looks_like_direct_key(api_key):
        provider, source = "direct", "key"
    else:
        provider, source = "rapidapi", "default"

    if base_url and not re.match(r"^https?://", base_url, re.IGNORECASE):
        error = error or (
            f"SPOTIFY_API_BASE={base_url!r} is not a URL. Leave it unset to use the "
            "default endpoint of the provider."
        )

    if api_key is None:
        error = MISSING_KEY_MESSAGE

    return Settings(
        api_key=api_key,
        provider=provider,
        provider_source=source,
        base_url=base_url,
        error=error,
    )
