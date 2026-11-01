"""The MCP server: tool definitions and the ``checkleaked-spotify-mcp`` entry point."""

# No `from __future__ import annotations`: the tool signatures are read at runtime.
import argparse
import functools
import json
import logging
import re
import sys
import threading
from typing import Annotated, Any, Callable, List, Literal, Optional, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from spotify_api_sdk import SpotifyApiClient, SpotifyApiError
from spotify_api_sdk import __version__ as sdk_version

from . import __version__, shape
from .config import Settings, load_settings
from .errors import to_tool_error
from .ids import parse_country, parse_id, parse_ids, parse_isrc

logger = logging.getLogger("checkleaked_spotify_mcp")

ISSUES_URL = "https://github.com/eduair94/spotify-data-mcp/issues"
USER_AGENT = (
    f"checkleaked-spotify-mcp/{__version__} (+https://github.com/eduair94/spotify-data-mcp) "
    f"checkleaked-spotify-api/{sdk_version}"
)

INSTRUCTIONS = """\
Read-only Spotify catalog data from the CheckLeaked Spotify Data API: track play counts, \
artist monthly listeners, followers, world rank and top cities, Top 200 and viral charts, \
search, albums, playlists, ISRC lookup, and genres / moods / BPM.

- Every tool accepts Spotify ids, spotify: URIs and open.spotify.com URLs. With only a \
name, call `search` first to get the id.
- Each call spends one request of the user's API key (get_playlist spends two on its first \
page), so pass up to 50 ids in one call instead of one call per item.
- Spotify shows a play count of 0 for tracks with fewer than 1,000 plays.
- Unofficial: not affiliated with or endorsed by Spotify."""

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

T = TypeVar("T")

_ID_HELP = "Spotify {kind} id, spotify:{kind}:<id> URI or open.spotify.com/{kind}/<id> URL."
_IDS_HELP = "Spotify {kind} ids, spotify:{kind}:<id> URIs or open.spotify.com/{kind}/<id> URLs (1-{max})."


class Backend:
    """Builds the SDK client on first use and maps its errors."""

    def __init__(self, settings: Settings, session: Any = None) -> None:
        self.settings = settings
        self._session = session
        self._client: Optional[SpotifyApiClient] = None
        self._lock = threading.Lock()

    def client(self) -> SpotifyApiClient:
        if self.settings.error:
            raise ToolError(self.settings.error)
        with self._lock:
            if self._client is None:
                options: dict = {
                    "provider": self.settings.sdk_provider,
                    # A tool call should answer within a minute: one retry, short waits.
                    "timeout": 45.0,
                    "retries": 1,
                    "max_retry_delay": 5.0,
                    "user_agent": USER_AGENT,
                }
                if self.settings.base_url:
                    options["base_url"] = self.settings.base_url
                if self._session is not None:
                    options["session"] = self._session
                self._client = SpotifyApiClient(self.settings.api_key, **options)
            return self._client

    def call(self, fn: Callable[[SpotifyApiClient], T], not_found: Optional[str] = None) -> T:
        """Run ``fn`` with the client; ``not_found`` replaces the message of an HTTP 404."""

        client = self.client()
        try:
            return fn(client)
        except SpotifyApiError as error:
            # RapidAPI answers 404 "Endpoint ... does not exist" for unlisted routes: keep that one.
            if not_found and error.status == 404 and "does not exist" not in str(error).lower():
                raise ToolError(not_found) from error
            raise to_tool_error(error, self.settings) from error


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _guard(fn: Callable[..., Any]) -> Callable[..., str]:
    """Return compact JSON; turn an unexpected failure into a readable tool error."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return _dump(fn(*args, **kwargs))
        except ToolError:
            raise
        except Exception as error:  # noqa: BLE001 - reported to the model, logged in full
            logger.exception("Tool %s failed", fn.__name__)
            raise ToolError(
                f"Unexpected error in {fn.__name__}: {type(error).__name__}: {error}. "
                f"If it persists, report it at {ISSUES_URL}"
            ) from error

    return wrapper


def create_server(settings: Optional[Settings] = None, *, session: Any = None) -> MCPServer:
    """Build the MCP server. ``session`` replaces the SDK's ``requests.Session`` (tests)."""

    backend = Backend(settings or load_settings(), session=session)
    mcp = MCPServer(
        name="spotify-data",
        title="Spotify Data (CheckLeaked)",
        description="Spotify play counts, monthly listeners, charts and catalog data.",
        instructions=INSTRUCTIONS,
        website_url="https://spotify.checkleaked.cc",
        version=__version__,
        log_level="WARNING",
    )

    def tool(name: str, title: str, description: str) -> Callable[[Callable[..., Any]], Any]:
        def register(fn: Callable[..., Any]) -> Any:
            mcp.add_tool(
                _guard(fn),
                name=name,
                title=title,
                description=description,
                annotations=READ_ONLY,
                structured_output=False,
            )
            return fn

        return register

    # ─── search ──────────────────────────────────────────────────────────────

    @tool(
        "search",
        "Search Spotify",
        "Search the Spotify catalog by name to find ids for the other tools. `type` picks what "
        "to search: tracks, artists, albums or playlists. Returns up to `limit` hits (max 20) "
        "with id, name, key fields and open.spotify.com URL. For track searches, "
        "include_play_counts adds each hit's lifetime play count.",
    )
    def search(
        query: Annotated[str, Field(min_length=1, max_length=300, description="Search text, e.g. 'Bad Bunny' or 'blinding lights the weeknd'.")],
        type: Annotated[Literal["tracks", "artists", "albums", "playlists"], Field(description="What to search for.")] = "tracks",
        limit: Annotated[int, Field(ge=1, le=20, description="Number of results (1-20).")] = 10,
        include_play_counts: Annotated[bool, Field(description="Track searches only: add lifetime play counts (slightly slower).")] = False,
    ) -> Any:
        text = query.strip()
        if not text:
            raise ToolError("The search query is empty.")
        include = ["playcount"] if include_play_counts and type == "tracks" else None
        payload = backend.call(lambda c: c.search.search(text, type=type, limit=limit, include=include))
        return shape.search(payload, type, limit)

    # ─── tracks ──────────────────────────────────────────────────────────────

    @tool(
        "get_tracks",
        "Get tracks",
        "Track details for up to 50 tracks in one call: name, artists, album, release date, "
        "duration, explicit flag, popularity, ISRC and (by default) lifetime play count. "
        "include_insights adds genres, moods, activities, BPM, credits, lyrics flag and "
        "languages. A play count of 0 means fewer than 1,000 plays.",
    )
    def get_tracks(
        tracks: Annotated[List[str], Field(min_length=1, max_length=50, description=_IDS_HELP.format(kind="track", max=50))],
        include_play_counts: Annotated[bool, Field(description="Add each track's lifetime play count.")] = True,
        include_insights: Annotated[bool, Field(description="Add genres, moods, BPM, credits and languages (slower).")] = False,
    ) -> Any:
        ids = parse_ids(tracks, "track", 50)
        include = (["playcount"] if include_play_counts else []) + (["insights"] if include_insights else [])
        payload = backend.call(lambda c: c.tracks.get(ids, include=include or None))
        return shape.tracks(payload, with_insights=include_insights)

    @tool(
        "get_track_play_count",
        "Track play counts",
        "Lifetime Spotify play counts (streams) for up to 50 tracks in one call, with track "
        "name, artists and release date. The fastest way to compare streams. A play count of "
        "0 means fewer than 1,000 plays.",
    )
    def get_track_play_count(
        tracks: Annotated[List[str], Field(min_length=1, max_length=50, description=_IDS_HELP.format(kind="track", max=50))],
    ) -> Any:
        ids = parse_ids(tracks, "track", 50)
        payload = backend.call(lambda c: c.tracks.counts(ids))
        return shape.play_counts(payload)

    @tool(
        "get_track_insights",
        "Track genres, moods and BPM",
        "Genres, moods and activities (with Spotify's 0-1 weights), tempo in BPM, credits "
        "(writers, producers), lyrics flag and vocal languages for up to 50 tracks.",
    )
    def get_track_insights(
        tracks: Annotated[List[str], Field(min_length=1, max_length=50, description=_IDS_HELP.format(kind="track", max=50))],
    ) -> Any:
        ids = parse_ids(tracks, "track", 50)
        payload = backend.call(lambda c: c.tracks.get(ids, include=["insights"]))
        return shape.insights_only(payload)

    # ─── artists ─────────────────────────────────────────────────────────────

    @tool(
        "get_artists_stats",
        "Artist monthly listeners and stats",
        "Monthly listeners, followers, world rank, popularity, genres and top 5 cities (with "
        "listener counts) for up to 50 artists in one call.",
    )
    def get_artists_stats(
        artists: Annotated[List[str], Field(min_length=1, max_length=50, description=_IDS_HELP.format(kind="artist", max=50))],
    ) -> Any:
        ids = parse_ids(artists, "artist", 50)
        payload = backend.call(lambda c: c.artists.get(ids, include=["stats"]))
        return shape.artist_stats(payload)

    @tool(
        "get_artist_overview",
        "Artist overview",
        "One artist's profile: monthly listeners, followers, world rank, top cities, top "
        "tracks with play counts, latest release, discography counts, related artists, "
        "biography and social links.",
    )
    def get_artist_overview(
        artist: Annotated[str, Field(min_length=1, description=_ID_HELP.format(kind="artist"))],
        top_tracks: Annotated[int, Field(ge=1, le=10, description="How many top tracks to return (1-10).")] = 10,
    ) -> Any:
        ident = parse_id(artist, "artist")
        payload = backend.call(lambda c: c.artists.overview(ident, slim=True), not_found=f"Spotify has no artist with id {ident}.")
        result = shape.artist_overview(payload, top_tracks_limit=top_tracks)
        if result is None:
            raise ToolError(f"Spotify has no artist with id {ident}.")
        return result

    @tool(
        "get_artist_insights",
        "Artist genres, moods and BPM",
        "An artist's sound profile from their top tracks: genres, moods and activities with "
        "0-1 weights, and tempo (average, min, max BPM). Up to 20 artists per call.",
    )
    def get_artist_insights(
        artists: Annotated[List[str], Field(min_length=1, max_length=20, description=_IDS_HELP.format(kind="artist", max=20))],
    ) -> Any:
        ids = parse_ids(artists, "artist", 20)
        payload = backend.call(lambda c: c.artists.get(ids, include=["insights"]))
        return shape.artist_insights(payload)

    @tool(
        "get_related_artists",
        "Related artists",
        "Artists Spotify lists as related to (\"Fans also like\") the given artist.",
    )
    def get_related_artists(
        artist: Annotated[str, Field(min_length=1, description=_ID_HELP.format(kind="artist"))],
        limit: Annotated[int, Field(ge=1, le=20, description="How many related artists to return (1-20).")] = 20,
    ) -> Any:
        ident = parse_id(artist, "artist")
        payload = backend.call(lambda c: c.artists.related(ident), not_found=f"Spotify has no artist with id {ident}.")
        result = shape.related_artists(payload, limit)
        if result is None:
            raise ToolError(f"Spotify has no artist with id {ident}.")
        return result

    # ─── albums and playlists ────────────────────────────────────────────────

    @tool(
        "get_album",
        "Get album",
        "An album with its track list and (by default) every track's lifetime play count, "
        "plus the album total, release date, label, UPC and popularity.",
    )
    def get_album(
        album: Annotated[str, Field(min_length=1, description=_ID_HELP.format(kind="album"))],
        include_play_counts: Annotated[bool, Field(description="Add each track's lifetime play count and the album total.")] = True,
    ) -> Any:
        ident = parse_id(album, "album")
        include = ["playcounts"] if include_play_counts else None
        payload = backend.call(lambda c: c.albums.get([ident], include=include), not_found=f"Spotify has no album with id {ident}.")
        result = shape.album(payload)
        if result is None:
            raise ToolError(f"Spotify has no album with id {ident}.")
        return result

    @tool(
        "get_playlist",
        "Get playlist",
        "A playlist's name, owner, followers and description, plus `limit` tracks (max 100) "
        "from `offset` with lifetime play counts. Use next_offset from the answer to page "
        "through long playlists (later pages skip the metadata and cost one request).",
    )
    def get_playlist(
        playlist: Annotated[str, Field(min_length=1, description=_ID_HELP.format(kind="playlist"))],
        limit: Annotated[int, Field(ge=1, le=100, description="Tracks to return (1-100).")] = 50,
        offset: Annotated[int, Field(ge=0, description="Index of the first track (0 = start).")] = 0,
        include_play_counts: Annotated[bool, Field(description="Add each track's lifetime play count.")] = True,
    ) -> Any:
        ident = parse_id(playlist, "playlist")
        include = ["playcount"] if include_play_counts else None
        missing = f"Spotify has no public playlist with id {ident}."
        result: dict = {}
        if offset == 0:
            meta = backend.call(lambda c: c.playlists.get(ident), not_found=missing)
            result.update(shape.playlist_meta(meta))
        page = backend.call(
            lambda c: c.playlists.tracks(ident, offset=offset, limit=limit, include=include),
            not_found=missing,
        )
        result.update(shape.playlist_tracks(page))
        return result

    # ─── charts and lookups ──────────────────────────────────────────────────

    @tool(
        "get_chart",
        "Spotify charts",
        "Spotify Charts by country: top_tracks (Top 200), viral_tracks (Viral 50, daily "
        "only), top_artists or top_albums. Each entry has rank, previous and peak rank, days "
        "(or weeks) on the chart, movement and, for top_tracks, the streams in that period. "
        "Defaults to the latest published daily chart.",
    )
    def get_chart(
        chart: Annotated[
            Literal["top_tracks", "viral_tracks", "top_artists", "top_albums"],
            Field(description="Which chart."),
        ] = "top_tracks",
        country: Annotated[str, Field(description="'global' or a 2-letter country code, e.g. 'us', 'br', 'mx'.")] = "global",
        period: Annotated[Literal["daily", "weekly"], Field(description="Daily or weekly chart (viral_tracks is daily only).")] = "daily",
        date: Annotated[Optional[str], Field(description="Chart date YYYY-MM-DD; omit for the latest published chart.")] = None,
        limit: Annotated[int, Field(ge=1, le=200, description="Entries to return (1-200).")] = 50,
        include_play_counts: Annotated[bool, Field(description="top_tracks / viral_tracks: add each track's lifetime play count (slower).")] = False,
    ) -> Any:
        market = parse_country(country)
        if date is not None:
            date = date.strip() or None
        if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise ToolError(f"{date!r} is not a date: use YYYY-MM-DD, or omit it for the latest chart.")
        if chart == "viral_tracks" and period == "weekly":
            raise ToolError("The viral chart is published daily only: use period='daily'.")
        include = ["playcount"] if include_play_counts and chart in ("top_tracks", "viral_tracks") else None

        def fetch(c: SpotifyApiClient) -> Any:
            if chart == "top_tracks":
                return c.charts.top200_tracks(period=period, country=market, date=date, include=include)
            if chart == "viral_tracks":
                return c.charts.viral_tracks(country=market, date=date, include=include)
            if chart == "top_artists":
                return c.charts.top_artists(period=period, country=market, date=date)
            return c.charts.top_albums(period=period, country=market, date=date)

        if chart == "viral_tracks":
            period = "daily"
        result = shape.chart(backend.call(fetch), chart, limit, period)
        return {"chart": chart, "country": market, "period": period, **result}

    @tool(
        "isrc_lookup",
        "Find tracks by ISRC",
        "Find the Spotify track(s) for an ISRC (International Standard Recording Code), "
        "e.g. USUG11904206. Returns ids, names, artists, album and release date.",
    )
    def isrc_lookup(
        isrc: Annotated[str, Field(min_length=12, max_length=20, description="12-character ISRC; spaces and dashes are ignored.")],
    ) -> Any:
        code = parse_isrc(isrc)
        missing = f"No Spotify track has the ISRC {code}."
        payload = backend.call(lambda c: c.lookups.isrc(code), not_found=missing)
        result = shape.isrc_lookup(payload)
        if not result.get("tracks"):
            raise ToolError(missing)
        return {"isrc": code, **result}

    return mcp


def main(argv: Optional[List[str]] = None) -> None:
    """Console entry point: run the server over stdio."""

    parser = argparse.ArgumentParser(
        prog="checkleaked-spotify-mcp",
        description=(
            "MCP server (stdio) for the CheckLeaked Spotify Data API. Configure it with "
            "SPOTIFY_API_KEY, and optionally SPOTIFY_API_PROVIDER (rapidapi | direct) and "
            "SPOTIFY_API_BASE."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)

    settings = load_settings()
    if settings.error:
        # stderr only: stdout carries the MCP protocol.
        print(f"[checkleaked-spotify-mcp] {settings.error}", file=sys.stderr, flush=True)
    create_server(settings).run("stdio")


if __name__ == "__main__":
    main()
