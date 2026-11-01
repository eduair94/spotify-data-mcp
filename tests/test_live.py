"""Live smoke test against the real API (one request per test).

Skipped unless SPOTIFY_MCP_LIVE=1 and SPOTIFY_API_KEY are set:

    SPOTIFY_MCP_LIVE=1 SPOTIFY_API_KEY=... pytest -m live
"""

import os

import pytest

from checkleaked_spotify_mcp.config import load_settings
from checkleaked_spotify_mcp.server import create_server
from conftest import call

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("SPOTIFY_MCP_LIVE") != "1" or not os.environ.get("SPOTIFY_API_KEY"),
        reason="set SPOTIFY_MCP_LIVE=1 and SPOTIFY_API_KEY to run live tests",
    ),
]


@pytest.fixture(scope="module")
def server():
    return create_server(load_settings())


def test_live_play_count(server):
    out = call(server, "get_track_play_count", {"tracks": ["0VjIjW4GlUZAMYd2vXMi3b"]})
    assert out["tracks"][0]["play_count"] > 1_000_000_000


def test_live_artist_stats(server):
    out = call(server, "get_artists_stats", {"artists": ["4q3ewBCX7sLwd24euuV69X"]})
    assert out["artists"][0]["monthly_listeners"] > 1_000_000
