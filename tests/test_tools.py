"""Tool registration, the SDK calls each tool makes, and output trimming."""

import json

import anyio
import pytest

from conftest import call, call_error, load, make_server, ok

EXPECTED_TOOLS = {
    "search",
    "get_tracks",
    "get_track_play_count",
    "get_track_insights",
    "get_artists_stats",
    "get_artist_overview",
    "get_artist_insights",
    "get_related_artists",
    "get_album",
    "get_playlist",
    "get_chart",
    "isrc_lookup",
}
# Endpoints this server must never reach (copyright and cost).
FORBIDDEN_PATH_PARTS = ("lyrics", "download", "webhook", "tracking", "/ai/", "snapshot")

BAD_BUNNY = "4q3ewBCX7sLwd24euuV69X"
KAROL_G = "790FomKkXshlbRYZFtlgla"
BLINDING_LIGHTS = "0VjIjW4GlUZAMYd2vXMi3b"
UN_VERANO = "3RQQmkQEvNCY4prGKE6oc5"
TODAYS_TOP_HITS = "37i9dQZF1DXcBWIGoYBM5M"


def list_tools(server):
    async def run():
        return await server.list_tools()

    return {tool.name: tool for tool in anyio.run(run)}


def test_tool_names_and_annotations():
    server, _ = make_server()
    tools = list_tools(server)
    assert set(tools) == EXPECTED_TOOLS
    for tool in tools.values():
        assert tool.description and len(tool.description) > 60
        assert tool.title
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.open_world_hint is True
        assert tool.output_schema is None  # compact JSON text, not duplicated structured content
        assert not any(part.strip("/") in tool.name for part in FORBIDDEN_PATH_PARTS)


def test_input_schemas():
    tools = list_tools(make_server()[0])
    schema = tools["get_tracks"].input_schema
    assert schema["required"] == ["tracks"]
    assert schema["properties"]["tracks"]["type"] == "array"
    assert schema["properties"]["tracks"]["maxItems"] == 50
    assert schema["properties"]["include_play_counts"]["default"] is True

    search = tools["search"].input_schema["properties"]
    assert search["type"]["enum"] == ["tracks", "artists", "albums", "playlists"]
    assert search["limit"]["maximum"] == 20

    assert tools["get_artist_insights"].input_schema["properties"]["artists"]["maxItems"] == 20
    chart = tools["get_chart"].input_schema
    assert chart["properties"]["chart"]["enum"] == ["top_tracks", "viral_tracks", "top_artists", "top_albums"]
    assert chart["properties"]["limit"]["maximum"] == 200
    assert "required" not in chart or chart["required"] == []
    for tool in tools.values():
        json.dumps(tool.input_schema)  # serialisable
        for prop in tool.input_schema["properties"].values():
            assert prop.get("description"), (tool.name, prop)


def test_schema_rejects_out_of_range_arguments():
    server, session = make_server()
    message = call_error(server, "search", {"query": "x", "limit": 21})
    assert "limit" in message
    message = call_error(server, "get_tracks", {"tracks": []})
    assert "tracks" in message
    assert session.calls == []


def test_rapidapi_request_headers():
    server, session = make_server({"/partner/tracks/count": ok(load("track_counts.json"))})
    call(server, "get_track_play_count", {"tracks": [BLINDING_LIGHTS]})
    sent = session.calls[0]
    assert sent["base"] == "https://spotify81.p.rapidapi.com"
    assert sent["headers"]["x-rapidapi-key"] == "test-rapidapi-key"
    assert sent["headers"]["x-rapidapi-host"] == "spotify81.p.rapidapi.com"
    assert sent["headers"]["user-agent"].startswith("checkleaked-spotify-mcp/")


def test_direct_key_goes_to_the_direct_api():
    key = "sapi_" + "0f" * 32
    server, session = make_server({"/partner/tracks/count": ok(load("track_counts.json"))}, env={"SPOTIFY_API_KEY": key})
    call(server, "get_track_play_count", {"tracks": [BLINDING_LIGHTS]})
    sent = session.calls[0]
    assert sent["url"].startswith("https://spotify-proxy.checkleaked.cc/spotify-data/partner/tracks/count?")
    assert sent["headers"]["x-rapidapi-key"] == key
    assert "x-rapidapi-host" not in sent["headers"]


def test_custom_base_url():
    env = {"SPOTIFY_API_KEY": "k", "SPOTIFY_API_PROVIDER": "direct", "SPOTIFY_API_BASE": "http://127.0.0.1:3029/spotify-data"}
    server, session = make_server({"/artist_related": ok(load("artist_related.json"))}, env=env)
    call(server, "get_related_artists", {"artist": BAD_BUNNY})
    assert session.calls[0]["url"] == f"http://127.0.0.1:3029/spotify-data/artist_related?id={BAD_BUNNY}"


def test_search_tracks_with_play_counts():
    server, session = make_server({"/search": ok(load("search_tracks.json"))})
    out = call(server, "search", {"query": "bad bunny", "limit": 2, "include_play_counts": True})
    assert session.calls[0]["query"] == {"q": "bad bunny", "type": "tracks", "limit": "2", "include": "playcount"}
    assert len(out["tracks"]) == 2
    first = out["tracks"][0]
    assert first == {
        "id": "3sK8wGT43QFpWrvNQsrQya",
        "name": "DtMF",
        "artists": "Bad Bunny",
        "album": "DeBÍ TiRAR MáS FOToS",
        "duration": "3:57",
        "explicit": True,
        "play_count": 2232856710,
        "url": "https://open.spotify.com/track/3sK8wGT43QFpWrvNQsrQya",
    }


@pytest.mark.parametrize(
    ("kind", "fixture", "first"),
    [
        ("artists", "search_artists.json", {"id": BAD_BUNNY, "name": "Bad Bunny", "verified": True}),
        ("albums", "search_albums.json", {"id": UN_VERANO, "name": "Un Verano Sin Ti", "type": "album", "year": 2022}),
        ("playlists", "search_playlists.json", {"id": "37i9dQZF1DWZjqjZMudx9T", "owner": "Spotify"}),
    ],
)
def test_search_other_types(kind, fixture, first):
    server, session = make_server({"/search": ok(load(fixture))})
    out = call(server, "search", {"query": "q", "type": kind, "include_play_counts": True})
    assert "include" not in session.calls[0]["query"]  # play counts only apply to tracks
    assert out[kind][0].items() >= first.items()
    assert out["total_matches"] > 0
    assert all(row["url"].startswith("https://open.spotify.com/") for row in out[kind])
    # The raw payload carries colour sets and wrappers the model never needs.
    assert "extractedColorSet" not in json.dumps(out) and "__typename" not in json.dumps(out)


def test_get_tracks_accepts_mixed_inputs_and_trims():
    server, session = make_server({"/tracks": ok(load("tracks_include.json"))})
    out = call(
        server,
        "get_tracks",
        {"tracks": [f"https://open.spotify.com/track/{BLINDING_LIGHTS}?si=1", "spotify:track:0yNttAVwMr39qyODHNIkrY"], "include_insights": True},
    )
    assert session.calls[0]["query"] == {"ids": f"{BLINDING_LIGHTS},0yNttAVwMr39qyODHNIkrY", "include": "playcount,insights"}
    track = out["tracks"][0]
    assert track["play_count"] == 5643370541
    assert track["isrc"] == "USUG11904206"
    assert track["album"]["release_date"] == "2020-03-20"
    assert track["insights"]["bpm"] == 171
    assert track["insights"]["genres"]["Pop"] == 0.92
    assert len(track["insights"]["credits"]) <= 12
    assert "available_markets" not in json.dumps(out) and "preview_url" not in json.dumps(out)


def test_get_tracks_without_extras():
    server, session = make_server({"/tracks": ok(load("tracks_include.json"))})
    call(server, "get_tracks", {"tracks": [BLINDING_LIGHTS], "include_play_counts": False})
    assert "include" not in session.calls[0]["query"]


def test_play_counts():
    server, session = make_server({"/partner/tracks/count": ok(load("track_counts.json"))})
    out = call(server, "get_track_play_count", {"tracks": [f"{BLINDING_LIGHTS},2JiDi0qAXsPwhPqA2qaKGt"]})
    assert session.calls[0]["path"] == "/partner/tracks/count"
    assert [t["play_count"] for t in out["tracks"]] == [5659652654, 3318807640]
    assert out["tracks"][1]["artists"] == "Queen"


def test_track_insights_use_the_tracks_include():
    server, session = make_server({"/tracks": ok(load("tracks_include.json"))})
    out = call(server, "get_track_insights", {"tracks": [BLINDING_LIGHTS]})
    assert session.calls[0]["query"]["include"] == "insights"
    assert out["tracks"][0]["insights"]["moods"]["Upbeat"] == 0.75
    assert "play_count" not in out["tracks"][0]


def test_artists_stats():
    server, session = make_server({"/artists": ok(load("artists_stats.json"))})
    out = call(server, "get_artists_stats", {"artists": [BAD_BUNNY, f"https://open.spotify.com/artist/{KAROL_G}"]})
    assert session.calls[0]["query"] == {"ids": f"{BAD_BUNNY},{KAROL_G}", "include": "stats"}
    bad_bunny, karol_g = out["artists"]
    assert bad_bunny["monthly_listeners"] == 90118373 and bad_bunny["world_rank"] == 10
    assert karol_g["name"] == "KAROL G"
    assert len(bad_bunny["top_cities"]) == 5 and bad_bunny["top_cities"][0] == {"city": "Mexico City", "country": "MX", "listeners": 4235102}


def test_artist_insights():
    server, session = make_server({"/artists": ok(load("artists_include.json"))})
    out = call(server, "get_artist_insights", {"artists": ["1Xyo4u8uXC1ZmMpatF05PJ"]})
    assert session.calls[0]["query"]["include"] == "insights"
    weeknd = out["artists"][0]
    assert weeknd["bpm"] == {"average": 126.7, "min": 87.5, "max": 186}
    assert weeknd["based_on"] == "10 top tracks"
    assert list(weeknd["genres"])[0] == "Pop"


def test_artist_overview():
    server, session = make_server({"/artist_overview": ok(load("artist_overview_slim.json"))})
    out = call(server, "get_artist_overview", {"artist": f"spotify:artist:{BAD_BUNNY}", "top_tracks": 3})
    assert session.calls[0]["query"] == {"id": BAD_BUNNY, "slim": "true"}
    assert out["monthly_listeners"] == 90118373 and out["world_rank"] == 10 and out["verified"] is True
    assert [t["play_count"] for t in out["top_tracks"]][0] == 2232856710
    assert len(out["top_tracks"]) == 3
    assert len(out["related_artists"]) == 10
    assert out["discography"] == {"albums": 8, "singles": 92, "compilations": 0}
    assert out["biography"].endswith("…") and len(out["biography"]) <= 600
    assert "latest_release" not in out  # Spotify shows none for this artist right now


def test_artist_overview_latest_release():
    payload = load("artist_overview_slim.json")
    payload["data"]["artistUnion"]["discography"]["latest"] = load("artist_overview_latest.json")["latest"]
    server, _ = make_server({"/artist_overview": ok(payload)})
    latest = call(server, "get_artist_overview", {"artist": BAD_BUNNY})["latest_release"]
    assert latest["name"] == "Patient Zero" and latest["type"] == "single" and latest["date"].count("-") == 2
    assert latest["url"] == f"https://open.spotify.com/album/{latest['id']}"


def test_artist_overview_not_found():
    payload = {"data": {"artistUnion": {"__typename": "NotFound"}}}
    server, _ = make_server({"/artist_overview": ok(payload)})
    assert "no artist with id" in call_error(server, "get_artist_overview", {"artist": BAD_BUNNY})


def test_related_artists():
    server, _ = make_server({"/artist_related": ok(load("artist_related.json"))})
    out = call(server, "get_related_artists", {"artist": BAD_BUNNY, "limit": 2})
    assert out["artist"] == {"id": BAD_BUNNY, "name": "Bad Bunny"}
    assert [a["name"] for a in out["related_artists"]] == ["Rauw Alejandro", "J Balvin"]


def test_album_with_play_counts():
    server, session = make_server({"/albums": ok(load("albums_playcounts.json"))})
    out = call(server, "get_album", {"album": f"https://open.spotify.com/album/{UN_VERANO}"})
    assert session.calls[0]["query"] == {"ids": UN_VERANO, "include": "playcounts"}
    assert out["total_tracks"] == 23 and len(out["tracks"]) == 23
    assert out["total_play_count"] == sum(t["play_count"] for t in out["tracks"])
    assert out["tracks"][0] == {"n": 1, "id": "6Xom58OOXk2SoU711L2IXO", "name": "Moscow Mule", "duration": "4:06", "explicit": True, "play_count": 1716797240}
    # Featured artists are named only when a track's artists differ from the album's.
    assert out["tracks"][2]["artists"] == "Bad Bunny, Chencho Corleone"
    assert "tracks_note" not in out


def test_album_missing():
    server, _ = make_server({"/albums": ok({"albums": [], "missing": [UN_VERANO], "unavailable": []})})
    assert f"no album with id {UN_VERANO}" in call_error(server, "get_album", {"album": UN_VERANO})


def test_playlist_first_page_and_paging():
    routes = {"/playlist": ok(load("playlist.json")), "/playlist_tracks": ok(load("playlist_tracks.json"))}
    server, session = make_server(routes)
    out = call(server, "get_playlist", {"playlist": f"spotify:playlist:{TODAYS_TOP_HITS}", "limit": 3})
    assert [c["path"] for c in session.calls] == ["/playlist", "/playlist_tracks"]
    assert session.calls[1]["query"] == {"id": TODAYS_TOP_HITS, "offset": "0", "limit": "3", "include": "playcount"}
    assert out["name"] == "Today’s Top Hits" and out["followers"] == 33643846
    assert out["tracks"][0]["position"] == 1 and out["tracks"][0]["play_count"] == 369156638
    assert out["next_offset"] == 3 and out["total"] == 50

    page = load("playlist_tracks.json")
    page["offset"] = 3
    server, session = make_server({"/playlist_tracks": ok(page)})
    out = call(server, "get_playlist", {"playlist": TODAYS_TOP_HITS, "offset": 3, "limit": 3})
    assert [c["path"] for c in session.calls] == ["/playlist_tracks"]  # later pages skip the metadata
    assert "name" not in out and out["tracks"][0]["position"] == 4 and out["next_offset"] == 6


def test_chart_top_tracks():
    server, session = make_server({"/top_200_tracks": ok(load("chart_top200_br.json"))})
    out = call(server, "get_chart", {"country": "BR", "limit": 2, "include_play_counts": True})
    assert session.calls[0]["query"] == {"period": "daily", "country": "br", "include": "playcount"}
    assert out["chart"] == "top_tracks" and out["country"] == "br" and out["total_entries"] == 5
    first = out["entries"][0]
    assert first["rank"] == 1 and first["streams"] == 2952028 and first["days_on_chart"] == 23
    assert first["url"] == "https://open.spotify.com/track/1uDn0nbzeGPVw97jp7SvzR"
    assert len(out["entries"]) == 2


@pytest.mark.parametrize(
    ("chart", "path", "fixture", "kind"),
    [
        ("viral_tracks", "/viral_tracks", "chart_viral.json", "track"),
        ("top_artists", "/top_artists", "chart_top_artists.json", "artist"),
        ("top_albums", "/top_albums", "chart_top_albums.json", "album"),
    ],
)
def test_other_charts(chart, path, fixture, kind):
    server, session = make_server({path: ok(load(fixture))})
    out = call(server, "get_chart", {"chart": chart, "country": "us", "period": "weekly" if chart != "viral_tracks" else "daily", "date": "2026-10-29"})
    assert session.calls[0]["query"]["date"] == "2026-10-29"
    assert out["entries"][0]["url"].startswith(f"https://open.spotify.com/{kind}/")
    if chart != "viral_tracks":
        assert session.calls[0]["query"]["period"] == "weekly" and "weeks_on_chart" in out["entries"][0]


def test_chart_input_validation():
    server, session = make_server()
    assert "daily only" in call_error(server, "get_chart", {"chart": "viral_tracks", "period": "weekly"})
    assert "YYYY-MM-DD" in call_error(server, "get_chart", {"date": "yesterday"})
    assert "2-letter" in call_error(server, "get_chart", {"country": "Brazil"})
    assert session.calls == []


def test_isrc_lookup():
    server, session = make_server({"/isrc_lookup": ok(load("isrc_lookup.json"))})
    out = call(server, "isrc_lookup", {"isrc": "us-ug1-19-04206"})
    assert session.calls[0]["query"] == {"isrc": "USUG11904206"}
    assert out["isrc"] == "USUG11904206"
    assert out["tracks"][0]["id"] == BLINDING_LIGHTS and out["tracks"][0]["isrc"] == "USUG11904206"


def test_isrc_not_found():
    body = {"success": False, "code": "NOT_FOUND", "error": "Not found", "message": "No track matches this ISRC."}
    server, _ = make_server({"/isrc_lookup": (404, body, {})})
    assert call_error(server, "isrc_lookup", {"isrc": "USUG11904206"}) == "No Spotify track has the ISRC USUG11904206."


def test_bad_ids_never_reach_the_api():
    server, session = make_server()
    assert "is a Spotify album" in call_error(server, "get_tracks", {"tracks": [f"spotify:album:{UN_VERANO}"]})
    assert "is not a Spotify artist id" in call_error(server, "get_artists_stats", {"artists": ["Bad Bunny"]})
    assert session.calls == []


def test_chart_new_entry_has_no_previous_rank():
    entries = load("chart_top200_br.json")
    entries[0]["chartEntryData"].update({"previousRank": -1, "entryStatus": "NEW_ENTRY"})
    server, _ = make_server({"/top_200_tracks": ok(entries)})
    first = call(server, "get_chart", {"limit": 1})["entries"][0]
    assert "previous_rank" not in first and first["status"] == "new_entry"


def test_related_artists_accepts_an_unwrapped_payload():
    server, _ = make_server({"/artist_related": ok({"success": True, "data": load("artist_related.json")["data"]})})
    out = call(server, "get_related_artists", {"artist": BAD_BUNNY, "limit": 1})
    assert out["related_artists"][0]["name"] == "Rauw Alejandro"


def test_blank_search_query():
    server, session = make_server()
    assert call_error(server, "search", {"query": "   "}) == "The search query is empty."
    assert session.calls == []
