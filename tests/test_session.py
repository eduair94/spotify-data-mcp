"""End to end through an MCP client session (in-process, no subprocess)."""

import json

import anyio
import pytest
from mcp import Client

from checkleaked_spotify_mcp import __version__
from conftest import load, make_server, ok


@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_client_session(mode):
    server, session = make_server({"/artists": ok(load("artists_stats.json"))})

    async def run():
        async with Client(server, mode=mode) as client:
            if mode == "legacy":  # initialize handshake: server identity and instructions
                assert client.server_info.name == "spotify-data"
                assert client.server_info.version == __version__
                assert "play counts" in client.instructions
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            ok_result = await client.call_tool(
                "get_artists_stats", {"artists": ["4q3ewBCX7sLwd24euuV69X", "790FomKkXshlbRYZFtlgla"]}
            )
            bad_result = await client.call_tool("get_artists_stats", {"artists": ["not an id"]})
            unknown = await client.call_tool("get_lyrics", {"id": "x"})
            return names, ok_result, bad_result, unknown

    names, ok_result, bad_result, unknown = anyio.run(run)
    assert len(names) == 12 and "get_artists_stats" in names
    assert ok_result.is_error is False
    data = json.loads(ok_result.content[0].text)
    assert [a["name"] for a in data["artists"]] == ["Bad Bunny", "KAROL G"]
    assert bad_result.is_error is True and "is not a Spotify artist id" in bad_result.content[0].text
    assert unknown.is_error is True
    assert len(session.calls) == 1


def test_client_session_without_key():
    server, _ = make_server(env={})

    async def run():
        async with Client(server, mode="legacy") as client:
            listed = await client.list_tools()
            result = await client.call_tool("get_chart", {"country": "br"})
            return listed, result

    listed, result = anyio.run(run)
    assert len(listed.tools) == 12  # the server starts and lists its tools without a key
    assert result.is_error is True
    assert "https://spotify.checkleaked.cc/pricing#trial" in result.content[0].text
