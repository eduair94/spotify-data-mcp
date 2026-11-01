"""Input parsing: Spotify ids, URIs and URLs, ISRCs and chart countries.

Every bad value is rejected here, before a request is spent on it.
"""

from __future__ import annotations

import re
from typing import Iterable, List

from mcp.server.mcpserver.exceptions import ToolError

_BASE62_ID = re.compile(r"^[A-Za-z0-9]{22}$")
# spotify:track:ID, and the legacy spotify:user:<name>:playlist:ID form.
_URI = re.compile(
    r"^spotify:(?:user:[^:\s]+:)?(track|artist|album|playlist|show|episode):([A-Za-z0-9]+)$",
    re.IGNORECASE,
)
# open.spotify.com/track/ID, /intl-es/track/ID, /embed/track/ID,
# /user/<name>/playlist/ID, with or without a scheme or a query string.
_URL = re.compile(
    r"^(?:https?://)?(?:open|play)\.spotify\.com/"
    r"(?:intl-[a-z]{2}(?:-[a-z]{2,4})?/)?(?:embed/)?(?:user/[^/\s]+/)?"
    r"(track|artist|album|playlist|show|episode)/([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"[\s,]+")
_ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")


def parse_id(value: str, kind: str) -> str:
    """Reduce a bare id, ``spotify:<kind>:<id>`` URI or open.spotify.com URL to its id."""

    text = str(value).strip().strip("<>\"'")
    match = _URI.match(text) or _URL.match(text)
    if match:
        found = match.group(1).lower()
        if found != kind:
            raise ToolError(
                f"{value!r} is a Spotify {found}, but this tool needs a {kind} "
                f"(an id, spotify:{kind}:<id> URI or open.spotify.com/{kind}/<id> URL)."
            )
        text = match.group(2)
    if not _BASE62_ID.match(text):
        hint = ""
        if "spotify.link" in text or "spoti.fi" in text:
            hint = " Short links cannot be resolved here: open it and copy the open.spotify.com URL."
        raise ToolError(
            f"{value!r} is not a Spotify {kind} id, spotify:{kind}:<id> URI or "
            f"open.spotify.com/{kind}/<id> URL (an id is 22 letters and digits).{hint}"
        )
    return text


def parse_ids(values: Iterable[str], kind: str, max_items: int) -> List[str]:
    """Parse a list of ids/URIs/URLs (items may also be comma separated).

    Duplicates are dropped, order is kept.
    """

    ids: List[str] = []
    for value in values:
        for token in _SPLIT.split(str(value)):
            if not token:
                continue
            parsed = parse_id(token, kind)
            if parsed not in ids:
                ids.append(parsed)
    if not ids:
        raise ToolError(f"Give at least one Spotify {kind} id, URI or URL.")
    if len(ids) > max_items:
        raise ToolError(
            f"{len(ids)} {kind}s given; this tool takes at most {max_items} per call. "
            "Split them into several calls."
        )
    return ids


def parse_isrc(value: str) -> str:
    """Upper-case an ISRC and drop spaces and dashes (``US-UG1-19-04206``)."""

    text = re.sub(r"[\s-]", "", str(value)).upper()
    if text.startswith("ISRC:"):
        text = text[5:]
    if not _ISRC.match(text):
        raise ToolError(
            f"{value!r} is not an ISRC: 12 characters, a 2-letter country code, a 3-character "
            "registrant code and 7 digits (e.g. USUG11904206)."
        )
    return text


def parse_country(value: str) -> str:
    """``global`` or a lower-case ISO 3166-1 alpha-2 code (``UK`` becomes ``gb``)."""

    text = str(value or "").strip().lower()
    if text in ("", "global", "world", "worldwide", "ww"):
        return "global"
    if text == "uk":
        return "gb"
    if not re.match(r"^[a-z]{2}$", text):
        raise ToolError(
            f"{value!r} is not a chart country: use 'global' or a 2-letter ISO country code "
            "such as 'us', 'br' or 'mx'."
        )
    return text
