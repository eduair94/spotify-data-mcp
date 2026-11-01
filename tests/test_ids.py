import pytest
from mcp.server.mcpserver.exceptions import ToolError

from checkleaked_spotify_mcp.ids import parse_country, parse_id, parse_ids, parse_isrc

TRACK = "0VjIjW4GlUZAMYd2vXMi3b"


@pytest.mark.parametrize(
    "value",
    [
        TRACK,
        f"  {TRACK}  ",
        f"spotify:track:{TRACK}",
        f"https://open.spotify.com/track/{TRACK}",
        f"https://open.spotify.com/track/{TRACK}?si=abc123&context=x",
        f"https://open.spotify.com/intl-es/track/{TRACK}",
        f"https://open.spotify.com/intl-pt-BR/track/{TRACK}",
        f"open.spotify.com/track/{TRACK}",
        f"http://open.spotify.com/embed/track/{TRACK}",
        f"https://play.spotify.com/track/{TRACK}",
        f"<https://open.spotify.com/track/{TRACK}>",
    ],
)
def test_track_forms(value):
    assert parse_id(value, "track") == TRACK


def test_legacy_user_playlist_forms():
    pid = "37i9dQZF1DXcBWIGoYBM5M"
    assert parse_id(f"spotify:user:spotify:playlist:{pid}", "playlist") == pid
    assert parse_id(f"https://open.spotify.com/user/spotify/playlist/{pid}", "playlist") == pid


def test_wrong_kind_is_named():
    with pytest.raises(ToolError, match="is a Spotify album, but this tool needs a track"):
        parse_id("https://open.spotify.com/album/3RQQmkQEvNCY4prGKE6oc5", "track")


@pytest.mark.parametrize("value", ["", "abc", "Bad Bunny", TRACK + "x", "spotify:track:", "https://example.com/track/" + TRACK])
def test_invalid_ids(value):
    with pytest.raises(ToolError, match="is not a Spotify track id"):
        parse_id(value, "track")


def test_short_links_get_a_hint():
    with pytest.raises(ToolError, match="Short links cannot be resolved"):
        parse_id("https://spotify.link/abcdef", "track")


def test_parse_ids_splits_dedupes_and_keeps_order():
    a, b = "0VjIjW4GlUZAMYd2vXMi3b", "2JiDi0qAXsPwhPqA2qaKGt"
    assert parse_ids([f"{b}, spotify:track:{a}", a, f"https://open.spotify.com/track/{b}"], "track", 50) == [b, a]


def test_parse_ids_limits():
    with pytest.raises(ToolError, match="at least one"):
        parse_ids([" , "], "artist", 50)
    many = ",".join(["0VjIjW4GlUZAMYd2vXMi3b"[:-2] + f"{i:02d}" for i in range(21)])
    with pytest.raises(ToolError, match="at most 20"):
        parse_ids([many], "artist", 20)


@pytest.mark.parametrize("value", ["USUG11904206", "us-ug1-19-04206", " USUG1 1904206 ", "isrc:USUG11904206"])
def test_isrc(value):
    assert parse_isrc(value) == "USUG11904206"


@pytest.mark.parametrize("value", ["USUG1190420", "1SUG11904206", "USUG1190420X", "hello"])
def test_bad_isrc(value):
    with pytest.raises(ToolError, match="is not an ISRC"):
        parse_isrc(value)


@pytest.mark.parametrize(("value", "expected"), [("BR", "br"), (" us ", "us"), ("", "global"), ("Global", "global"), ("UK", "gb")])
def test_country(value, expected):
    assert parse_country(value) == expected


def test_bad_country():
    with pytest.raises(ToolError, match="2-letter ISO country code"):
        parse_country("Brazil")
