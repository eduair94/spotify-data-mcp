"""Turn SDK errors into tool errors a model (and its user) can act on."""

from __future__ import annotations

import math
import re
from typing import Optional

from mcp.server.mcpserver.exceptions import ToolError
from spotify_api_sdk import NetworkError, SpotifyApiError
from spotify_api_sdk import TimeoutError as SdkTimeoutError

from .config import GET_A_KEY, PRICING_URL, RAPIDAPI_PRICING_URL, RAPIDAPI_URL, STATUS_URL, Settings, TRIAL_URL


def _retry_hint(error: SpotifyApiError) -> str:
    if error.retry_after_ms is None:
        return ""
    seconds = max(1, math.ceil(error.retry_after_ms / 1000))
    return f" Retry after {seconds} s."


def _suffix(error: SpotifyApiError) -> str:
    return f" (request id {error.request_id})" if error.request_id else ""


def _api_message(error: SpotifyApiError) -> str:
    """The API's own message, without a trailing period (the SDK's ``HTTP 503`` fallback is dropped)."""

    text = str(error).strip().rstrip(".").strip()
    return text if text and not re.match(r"^HTTP \d{3}$", text) else ""


def _provider_hint(settings: Settings) -> str:
    if settings.provider == "rapidapi":
        return (
            "The key was sent to RapidAPI (spotify81). If it came from spotify.checkleaked.cc "
            "(including a free-trial key), set SPOTIFY_API_PROVIDER=direct."
        )
    return (
        "The key was sent to the direct API (spotify-proxy.checkleaked.cc). If it is a "
        "RapidAPI key, set SPOTIFY_API_PROVIDER=rapidapi."
    )


def to_tool_error(error: SpotifyApiError, settings: Settings) -> ToolError:
    """Map an SDK error to a :class:`ToolError` with a readable, actionable message."""

    status: Optional[int] = error.status
    code = (error.code or "").upper()
    message = _api_message(error)
    lowered = message.lower()
    tail = _suffix(error)

    if isinstance(error, SdkTimeoutError):
        return ToolError(f"The Spotify Data API did not answer in time ({error}). Retry in a moment.")
    if isinstance(error, NetworkError):
        return ToolError(
            f"Could not reach the Spotify Data API ({error}). Check the network connection"
            + (" and SPOTIFY_API_BASE" if settings.base_url else "")
            + f". Service status: {STATUS_URL}"
        )

    if status == 401 or (status != 403 and code in ("INVALID_API_KEY", "MISSING_API_KEY")):
        if code == "KEY_EXPIRED" or "expired" in lowered:
            return ToolError(
                f"This API key has expired. Renew it at {PRICING_URL} to reactivate the same key, "
                f"or start a free trial at {TRIAL_URL}.{tail}"
            )
        if code == "KEY_REVOKED" or "revoked" in lowered:
            return ToolError(f"This API key has been revoked. {GET_A_KEY}{tail}")
        return ToolError(
            f"The API rejected SPOTIFY_API_KEY (HTTP {status or 401}"
            + (f" {code}" if code else "")
            + f"). {_provider_hint(settings)} {GET_A_KEY}{tail}"
        )

    if status == 403:
        if code == "TRIAL_ROUTE_NOT_INCLUDED":
            text = message or "This endpoint is not included in the free trial key"
            link = "" if PRICING_URL in text else f" Paid keys: {PRICING_URL}."
            return ToolError(f"{text}.{link}{tail}")
        if "not subscribed" in lowered:
            return ToolError(
                "Your RapidAPI account is not subscribed to the spotify81 API. Subscribe to its "
                f"free Basic plan at {RAPIDAPI_URL} (or use a direct key: {TRIAL_URL}).{tail}"
            )
        return ToolError(
            (message or "This API key's plan does not include this endpoint")
            + " (HTTP 403"
            + (f" {code}" if code else "")
            + f"). Plans: {PRICING_URL}{tail}"
        )

    if status == 429:
        if code == "QUOTA_EXCEEDED" or "quota" in lowered:
            where = RAPIDAPI_PRICING_URL if settings.provider == "rapidapi" else PRICING_URL
            return ToolError(
                "This API key has used all of its requests (HTTP 429 QUOTA_EXCEEDED). Upgrade or "
                f"renew it at {where}.{tail}"
            )
        return ToolError(
            "Rate limited by the Spotify Data API (HTTP 429): too many requests in a short time."
            + (_retry_hint(error) or " Wait a few seconds and retry.")
            + tail
        )

    if status == 404:
        if "does not exist" in lowered and settings.provider == "rapidapi":
            return ToolError(
                f"RapidAPI does not list this endpoint yet ({message}). A direct key reaches every "
                f"endpoint: free trial at {TRIAL_URL}.{tail}"
            )
        return ToolError(f"Not found: {message or 'Spotify has no such item'}.{tail}")

    if status in (400, 422) or code in ("INVALID_PARAMETER", "MISSING_PARAMETER", "VALIDATION"):
        return ToolError(f"The API rejected the request: {message or code or 'invalid parameter'}.{tail}")

    if status is not None and status >= 500:
        return ToolError(
            f"The Spotify Data API is temporarily unavailable (HTTP {status}"
            + (f" {code}" if code else "")
            + ")."
            + (_retry_hint(error) or " Retry in a minute.")
            + f" Service status: {STATUS_URL}{tail}"
        )

    detail = message or code or "unknown error"
    shown = f" (HTTP {status})" if status and not 200 <= status < 300 else ""
    return ToolError(f"The Spotify Data API returned an error: {detail}{shown}.{tail}")
