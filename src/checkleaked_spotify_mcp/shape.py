"""Trim API payloads to compact, LLM-friendly objects.

Every function takes the decoded API payload (whatever ``client.request()``
returned) and keeps the fields a model needs: ids, names, numbers and an
open.spotify.com URL. ``None``, empty strings and empty lists are dropped.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, Iterable, List, Optional

Obj = Dict[str, Any]

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


# ─── helpers ──────────────────────────────────────────────────────────────────


def obj(value: Any) -> Obj:
    return value if isinstance(value, dict) else {}


def items(value: Any) -> List[Any]:
    """A list, or the ``items`` list of a paging object."""

    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("items"), list):
        return value["items"]
    return []


def dig(value: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def clean(value: Any) -> Any:
    """Drop ``None``, ``""``, ``[]`` and ``{}`` recursively."""

    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            item = clean(item)
            if item is None or item == "" or item == [] or item == {}:
                continue
            out[key] = item
        return out
    if isinstance(value, list):
        return [clean(item) for item in value if item is not None]
    return value


def to_int(value: Any) -> Optional[int]:
    """An int from an int, float or numeric string (play counts arrive as strings)."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _positive(value: Optional[int]) -> Optional[int]:
    return value if value is not None and value > 0 else None


def id_from_uri(uri: Any) -> Optional[str]:
    if isinstance(uri, str) and uri.startswith("spotify:"):
        return uri.rsplit(":", 1)[-1] or None
    return None


def spotify_url(kind: str, ident: Optional[str]) -> Optional[str]:
    return f"https://open.spotify.com/{kind}/{ident}" if ident else None


def duration(ms: Any) -> Optional[str]:
    value = to_int(ms)
    if value is None:
        return None
    seconds = round(value / 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def plain_text(value: Any, limit: int = 0) -> Optional[str]:
    """HTML to plain text (entities decoded, tags dropped), optionally truncated."""

    if not isinstance(value, str) or not value.strip():
        return None
    text = html.unescape(_TAG_RE.sub(" ", html.unescape(value)))
    text = _SPACE_RE.sub(" ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text or None


def pick_image(images: Any, prefer: int = 300) -> Optional[str]:
    """The URL of the image closest to ``prefer`` px (Web API ``images`` or ``sources``)."""

    candidates = [i for i in items(images) if isinstance(i, dict) and isinstance(i.get("url"), str)]
    if not candidates:
        return None

    def distance(image: Obj) -> int:
        size = to_int(image.get("width")) or to_int(image.get("height")) or to_int(image.get("maxWidth"))
        return abs(size - prefer) if size else 10_000

    return min(candidates, key=distance)["url"]


def weights(tags: Any, limit: int) -> Optional[Dict[str, float]]:
    """``[{display_name, weight}]`` -> ``{"Pop": 0.92, ...}``, strongest first."""

    pairs = []
    for tag in items(tags):
        if not isinstance(tag, dict):
            continue
        name = tag.get("display_name") or tag.get("name")
        weight = tag.get("weight")
        if isinstance(name, str) and isinstance(weight, (int, float)):
            pairs.append((name, round(float(weight), 2)))
    pairs.sort(key=lambda pair: -pair[1])
    return dict(pairs[:limit]) or None


def artist_refs(artists: Any) -> List[Obj]:
    """Web API ``artists`` or pathfinder ``artists.items`` -> ``[{id, name}]``."""

    out = []
    for artist in items(artists):
        if not isinstance(artist, dict):
            continue
        name = artist.get("name") or dig(artist, "profile", "name")
        ident = artist.get("id") or id_from_uri(artist.get("uri") or artist.get("spotifyUri"))
        if name or ident:
            out.append(clean({"id": ident, "name": name}))
    return out


def artist_names(artists: Any) -> Optional[str]:
    names = [a["name"] for a in artist_refs(artists) if a.get("name")]
    return ", ".join(names) or None


def release_date(date: Any) -> Optional[str]:
    """A pathfinder ``{year, month, day}`` date (or a string) as ``YYYY[-MM[-DD]]``."""

    if isinstance(date, str):
        return date or None
    date = obj(date)
    year = to_int(date.get("year"))
    if not year:
        iso = date.get("isoString")
        return iso[:10] if isinstance(iso, str) else None
    month, day = to_int(date.get("month")), to_int(date.get("day"))
    precision = str(date.get("precision") or "").upper()
    if month and day and precision in ("", "DAY"):
        return f"{year:04d}-{month:02d}-{day:02d}"
    if month and precision in ("", "DAY", "MONTH"):
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}"


# ─── tracks ───────────────────────────────────────────────────────────────────


def track(t: Obj) -> Obj:
    """A Web API track object (``/tracks``, ``/isrc_lookup``)."""

    album = obj(t.get("album"))
    ident = t.get("id") or id_from_uri(t.get("uri"))
    return clean(
        {
            "id": ident,
            "name": t.get("name"),
            "artists": artist_refs(t.get("artists")),
            "album": clean(
                {
                    "id": album.get("id"),
                    "name": album.get("name"),
                    "release_date": album.get("release_date"),
                    "total_tracks": album.get("total_tracks"),
                }
            ),
            "duration": duration(t.get("duration_ms")),
            "explicit": t.get("explicit"),
            "popularity": t.get("popularity"),
            "isrc": dig(t, "external_ids", "isrc"),
            "play_count": to_int(t.get("playcount")),
            "url": spotify_url("track", ident),
        }
    )


def track_insights(insights: Any) -> Optional[Obj]:
    ins = obj(insights)
    if not ins:
        return None
    credits = []
    for credit in items(ins.get("credits"))[:12]:
        if isinstance(credit, dict) and credit.get("name"):
            credits.append(clean({"name": credit.get("name"), "role": credit.get("role")}))
    return clean(
        {
            "genres": weights(ins.get("genres"), 8),
            "moods": weights(ins.get("moods"), 8),
            "activities": weights(ins.get("activities"), 5),
            "tags": [t if isinstance(t, str) else obj(t).get("display_name") or obj(t).get("name") for t in items(ins.get("tags"))][:8],
            "bpm": ins.get("bpm"),
            "has_lyrics": ins.get("has_lyrics"),
            "languages": ins.get("languages"),
            "credits": credits,
        }
    )


def not_found_ids(payload: Obj) -> Obj:
    """The ``missing`` / ``unavailable`` lists of a batch answer."""

    return clean({"not_found": payload.get("missing"), "unavailable": payload.get("unavailable")})


def tracks(payload: Any, with_insights: bool = False) -> Obj:
    """``GET /tracks`` (optionally ``include=playcount,insights``)."""

    payload = obj(payload)
    out = []
    for t in items(payload.get("tracks")):
        if not isinstance(t, dict):
            continue
        row = track(t)
        if with_insights:
            row["insights"] = track_insights(t.get("insights"))
        out.append(clean(row))
    return clean({"tracks": out, **not_found_ids(payload)})


def insights_only(payload: Any) -> Obj:
    """``GET /tracks?include=insights`` trimmed to the descriptors."""

    payload = obj(payload)
    out = []
    for t in items(payload.get("tracks")):
        if not isinstance(t, dict):
            continue
        ident = t.get("id")
        out.append(
            clean(
                {
                    "id": ident,
                    "name": t.get("name"),
                    "artists": artist_names(t.get("artists")),
                    "release_date": dig(t, "album", "release_date"),
                    "isrc": dig(t, "external_ids", "isrc"),
                    "insights": track_insights(t.get("insights")) or "not available for this track",
                    "url": spotify_url("track", ident),
                }
            )
        )
    return clean({"tracks": out, **not_found_ids(payload)})


def play_counts(payload: Any) -> Obj:
    """``GET /partner/tracks/count``."""

    payload = obj(payload)
    out = []
    for t in items(payload.get("tracks")):
        if not isinstance(t, dict):
            continue
        status = t.get("status")
        out.append(
            clean(
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "artists": artist_names(t.get("artists")),
                    "play_count": to_int(t.get("playcount")),
                    "release_date": t.get("releaseDate"),
                    "status": status if status and status != "ok" else None,
                    "url": spotify_url("track", t.get("id")),
                }
            )
        )
    return clean({"tracks": out, "not_found": payload.get("missing")})


# ─── artists ──────────────────────────────────────────────────────────────────


def top_cities(cities: Any, limit: int = 5) -> List[Obj]:
    out = []
    for city in items(cities)[:limit]:
        if isinstance(city, dict):
            out.append(
                clean(
                    {
                        "city": city.get("city"),
                        "country": city.get("country"),
                        "listeners": to_int(city.get("listeners", city.get("numberOfListeners"))),
                    }
                )
            )
    return out


def artist_stats(payload: Any) -> Obj:
    """``GET /artists?include=stats``."""

    payload = obj(payload)
    out = []
    for a in items(payload.get("artists")):
        if not isinstance(a, dict):
            continue
        stats = obj(a.get("stats"))
        rank = to_int(stats.get("world_rank"))
        out.append(
            clean(
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "monthly_listeners": to_int(stats.get("monthly_listeners")),
                    "followers": to_int(stats.get("followers")) or to_int(dig(a, "followers", "total")),
                    "world_rank": rank or None,
                    "popularity": a.get("popularity"),
                    "genres": a.get("genres"),
                    "top_cities": top_cities(stats.get("top_cities")),
                    "stats": None if stats else "not available for this artist right now",
                    "url": spotify_url("artist", a.get("id")),
                }
            )
        )
    return clean({"artists": out, **not_found_ids(payload)})


def artist_insights(payload: Any) -> Obj:
    """``GET /artists?include=insights``."""

    payload = obj(payload)
    out = []
    for a in items(payload.get("artists")):
        if not isinstance(a, dict):
            continue
        ins = obj(a.get("insights"))
        bpm = obj(ins.get("bpm"))
        basis = to_int(bpm.get("tracks")) or len(items(ins.get("top_track_ids"))) or None
        out.append(
            clean(
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "genres": weights(ins.get("genres"), 10),
                    "moods": weights(ins.get("moods"), 8),
                    "activities": weights(ins.get("activities"), 5),
                    "bpm": clean({"average": bpm.get("average"), "min": bpm.get("min"), "max": bpm.get("max")}),
                    "based_on": f"{basis} top tracks" if basis else None,
                    "insights": None if ins else "not available for this artist",
                    "url": spotify_url("artist", a.get("id")),
                }
            )
        )
    return clean({"artists": out, **not_found_ids(payload)})


def artist_overview(payload: Any, top_tracks_limit: int = 10, related_limit: int = 10) -> Optional[Obj]:
    """``GET /artist_overview?slim=true``; ``None`` when the artist does not exist."""

    union = obj(dig(payload, "data", "artistUnion")) or obj(obj(payload).get("artistUnion"))
    if not union or union.get("__typename") not in (None, "Artist"):
        return None
    ident = union.get("id") or id_from_uri(union.get("uri"))
    profile = obj(union.get("profile"))
    stats = obj(union.get("stats"))
    discography = obj(union.get("discography"))

    top = []
    for entry in items(dig(discography, "topTracks"))[:top_tracks_limit]:
        t = obj(obj(entry).get("track"))
        tid = t.get("id") or id_from_uri(t.get("uri"))
        if not tid:
            continue
        top.append(
            clean(
                {
                    "id": tid,
                    "name": t.get("name"),
                    "play_count": to_int(t.get("playcount")),
                    "artists": artist_names(t.get("artists")),
                    "duration": duration(dig(t, "duration", "totalMilliseconds")),
                    "explicit": dig(t, "contentRating", "label") == "EXPLICIT" or None,
                    "url": spotify_url("track", tid),
                }
            )
        )

    latest = obj(discography.get("latest"))
    latest_id = latest.get("id") or id_from_uri(latest.get("uri"))
    latest_release = (
        clean(
            {
                "id": latest_id,
                "name": latest.get("name"),
                "type": str(latest.get("type") or "").lower() or None,
                "date": release_date(latest.get("date")),
                "tracks": to_int(dig(latest, "tracks", "totalCount")),
                "label": latest.get("label"),
                "url": spotify_url("album", latest_id),
            }
        )
        if latest_id
        else None
    )

    related = []
    for artist in items(dig(union, "relatedContent", "relatedArtists"))[:related_limit]:
        artist = obj(artist)
        rid = artist.get("id") or id_from_uri(artist.get("uri"))
        if rid:
            related.append(clean({"id": rid, "name": dig(artist, "profile", "name"), "url": spotify_url("artist", rid)}))

    rank = to_int(stats.get("worldRank"))
    links = [
        clean({"name": str(link.get("name") or "").lower() or None, "url": link.get("url")})
        for link in items(dig(profile, "externalLinks"))
        if isinstance(link, dict) and link.get("url")
    ]
    return clean(
        {
            "id": ident,
            "name": profile.get("name"),
            "verified": dig(union, "onPlatformReputationTrait", "verification", "isVerified")
            if dig(union, "onPlatformReputationTrait", "verification", "isVerified") is not None
            else profile.get("verified"),
            "monthly_listeners": to_int(stats.get("monthlyListeners")),
            "followers": to_int(stats.get("followers")),
            "world_rank": rank or None,
            "top_cities": top_cities(dig(stats, "topCities")),
            "biography": plain_text(dig(profile, "biography", "text"), 600),
            "links": links[:8],
            "discography": clean(
                {
                    "albums": to_int(dig(discography, "albums", "totalCount")),
                    "singles": to_int(dig(discography, "singles", "totalCount")),
                    "compilations": to_int(dig(discography, "compilations", "totalCount")),
                }
            ),
            "latest_release": latest_release,
            "top_tracks": top,
            "related_artists": related,
            "image": pick_image(dig(union, "visuals", "avatarImage", "sources")),
            "url": spotify_url("artist", ident),
        }
    )


def related_artists(payload: Any, limit: int) -> Optional[Obj]:
    """``GET /artist_related``; ``None`` when the artist does not exist."""

    artist = obj(dig(payload, "data", "artist")) or obj(obj(payload).get("artist"))
    if not artist:
        return None
    out = []
    for entry in items(dig(artist, "relatedContent", "relatedArtists"))[:limit]:
        entry = obj(entry)
        rid = entry.get("id") or id_from_uri(entry.get("uri"))
        if rid:
            out.append(clean({"id": rid, "name": dig(entry, "profile", "name"), "url": spotify_url("artist", rid)}))
    return clean(
        {
            "artist": clean({"id": artist.get("id") or id_from_uri(artist.get("uri")), "name": dig(artist, "profile", "name")}),
            "related_artists": out,
        }
    )


# ─── albums and playlists ─────────────────────────────────────────────────────


def album(payload: Any) -> Optional[Obj]:
    """The first album of ``GET /albums?include=playcounts``; ``None`` when missing."""

    albums = [a for a in items(obj(payload).get("albums")) if isinstance(a, dict)]
    if not albums:
        return None
    a = albums[0]
    album_artists = artist_refs(a.get("artists"))
    album_artist_ids = {x.get("id") for x in album_artists}
    rows = [obj(t) for t in items(a.get("tracks"))]
    multi_disc = len({t.get("disc_number") for t in rows if t.get("disc_number")}) > 1

    track_rows = []
    counts: List[Optional[int]] = []
    for t in rows:
        artists = artist_refs(t.get("artists"))
        count = to_int(t.get("playcount"))
        counts.append(count)
        track_rows.append(
            clean(
                {
                    "disc": t.get("disc_number") if multi_disc else None,
                    "n": t.get("track_number"),
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "artists": ", ".join(x["name"] for x in artists if x.get("name"))
                    if {x.get("id") for x in artists} != album_artist_ids
                    else None,
                    "duration": duration(t.get("duration_ms")),
                    "explicit": t.get("explicit") or None,
                    "play_count": count,
                }
            )
        )
    known = [c for c in counts if c is not None]
    total_tracks = to_int(a.get("total_tracks")) or to_int(dig(a, "tracks", "total"))
    return clean(
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "type": a.get("album_type"),
            "artists": album_artists,
            "release_date": a.get("release_date"),
            "label": a.get("label"),
            "popularity": a.get("popularity"),
            "upc": dig(a, "external_ids", "upc"),
            "total_tracks": total_tracks,
            "total_play_count": sum(known) if known and len(known) == len(counts) else None,
            "tracks": track_rows,
            "tracks_note": f"first {len(track_rows)} of {total_tracks} tracks"
            if total_tracks and len(track_rows) < total_tracks
            else None,
            "image": pick_image(a.get("images")),
            "url": spotify_url("album", a.get("id")),
        }
    )


def playlist_meta(payload: Any) -> Obj:
    """``GET /playlist`` (metadata only)."""

    p = obj(payload)
    owner = obj(p.get("owner"))
    return clean(
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "description": plain_text(p.get("description"), 400),
            "owner": clean({"id": owner.get("id"), "name": owner.get("display_name")}),
            "followers": to_int(dig(p, "followers", "total")),
            "total_tracks": to_int(dig(p, "tracks", "total")),
            "image": pick_image(p.get("images")),
            "url": spotify_url("playlist", p.get("id")),
        }
    )


def playlist_tracks(payload: Any) -> Obj:
    """``GET /playlist_tracks?include=playcount``."""

    page = obj(payload)
    offset = to_int(page.get("offset")) or 0
    rows = []
    skipped = 0
    for index, entry in enumerate(items(page)):
        t = obj(obj(entry).get("track"))
        ident = t.get("id") or id_from_uri(t.get("uri"))
        if not ident:
            skipped += 1
            continue
        kind = t.get("type") or "track"
        rows.append(
            clean(
                {
                    "position": offset + index + 1,
                    "id": ident,
                    "type": kind if kind != "track" else None,
                    "name": t.get("name"),
                    "artists": artist_names(t.get("artists")),
                    "album": dig(t, "album", "name"),
                    "duration": duration(t.get("duration_ms")),
                    "play_count": to_int(t.get("playcount")),
                    "added_at": str(obj(entry).get("added_at") or "")[:10] or None,
                    "url": spotify_url(kind if kind in ("track", "episode") else "track", ident),
                }
            )
        )
    total = to_int(page.get("total"))
    returned_until = offset + len(items(page))
    return clean(
        {
            "tracks": rows,
            "offset": offset,
            "total": total,
            "next_offset": returned_until if total is not None and returned_until < total else None,
            "skipped": skipped or None,
        }
    )


# ─── search ───────────────────────────────────────────────────────────────────


def _search_entries(payload: Obj, bucket: str) -> Iterable[Obj]:
    for entry in items(payload.get(bucket)):
        entry = obj(entry)
        data = obj(entry.get("data")) or obj(dig(entry, "item", "data")) or entry
        if data.get("uri") or data.get("id"):
            yield data


def search(payload: Any, kind: str, limit: int) -> Obj:
    """Typed ``GET /search`` (``tracks``, ``artists``, ``albums`` or ``playlists``)."""

    payload = obj(payload)
    out: List[Obj] = []
    for data in _search_entries(payload, kind):
        ident = data.get("id") or id_from_uri(data.get("uri"))
        if kind == "tracks":
            row = {
                "id": ident,
                "name": data.get("name"),
                "artists": artist_names(data.get("artists")),
                "album": dig(data, "albumOfTrack", "name"),
                "duration": duration(dig(data, "duration", "totalMilliseconds")),
                "explicit": dig(data, "contentRating", "label") == "EXPLICIT" or None,
                "play_count": to_int(data.get("playcount")),
                "url": spotify_url("track", ident),
            }
        elif kind == "artists":
            row = {
                "id": ident,
                "name": dig(data, "profile", "name"),
                "verified": dig(data, "onPlatformReputationTrait", "verification", "isVerified")
                or dig(data, "profile", "verified")
                or None,
                "url": spotify_url("artist", ident),
            }
        elif kind == "albums":
            row = {
                "id": ident,
                "name": data.get("name"),
                "type": str(data.get("type") or "").lower() or None,
                "artists": artist_names(data.get("artists")),
                "year": to_int(dig(data, "date", "year")),
                "url": spotify_url("album", ident),
            }
        else:
            owner = obj(dig(data, "ownerV2", "data"))
            row = {
                "id": ident,
                "name": data.get("name"),
                "owner": owner.get("name") or owner.get("username"),
                "description": plain_text(data.get("description"), 160),
                "url": spotify_url("playlist", ident),
            }
        out.append(clean(row))
        if len(out) >= limit:
            break
    bucket = payload.get(kind)
    total = to_int(bucket.get("totalCount")) if isinstance(bucket, dict) else None
    return clean({kind: out, "total_matches": total})


# ─── charts and lookups ───────────────────────────────────────────────────────


def chart(payload: Any, chart_type: str, limit: int, period: str = "daily") -> Obj:
    """``/top_200_tracks``, ``/viral_tracks``, ``/top_artists`` or ``/top_albums``."""

    entries = [obj(e) for e in items(payload)]
    on_chart = "weeks_on_chart" if period == "weekly" else "days_on_chart"
    rows = []
    for entry in entries[:limit]:
        data = obj(entry.get("chartEntryData"))
        metric = obj(data.get("rankingMetric"))
        base = {
            "rank": to_int(data.get("currentRank")),
            "previous_rank": _positive(to_int(data.get("previousRank"))),
            "peak_rank": to_int(data.get("peakRank")),
            on_chart: to_int(data.get("appearancesOnChart")),
            "status": str(data.get("entryStatus") or "").lower() or None,
            "streams": to_int(metric.get("value")) if metric.get("type") == "STREAMS" else None,
        }
        if chart_type == "top_artists":
            meta = obj(entry.get("artistMetadata"))
            ident = id_from_uri(meta.get("artistUri"))
            row = {**base, "id": ident, "name": meta.get("artistName"), "url": spotify_url("artist", ident)}
        elif chart_type == "top_albums":
            meta = obj(entry.get("albumMetadata"))
            ident = id_from_uri(meta.get("albumUri"))
            row = {
                **base,
                "id": ident,
                "name": meta.get("albumName"),
                "artists": artist_names(meta.get("artists")),
                "release_date": meta.get("releaseDate"),
                "url": spotify_url("album", ident),
            }
        else:
            meta = obj(entry.get("trackMetadata"))
            ident = id_from_uri(meta.get("trackUri"))
            row = {
                **base,
                "id": ident,
                "name": meta.get("trackName"),
                "artists": artist_names(meta.get("artists")),
                "release_date": meta.get("releaseDate"),
                "play_count": to_int(meta.get("playcount")),
                "url": spotify_url("track", ident),
            }
        rows.append(clean(row))
    chart_date = entries[0].get("chartDate") if entries else None
    return clean(
        {
            "chart_date": chart_date if chart_date and chart_date != "latest" else "latest published",
            "entries": rows,
            "total_entries": len(entries),
        }
    )


def isrc_lookup(payload: Any, limit: int = 10) -> Obj:
    """``GET /isrc_lookup`` (a Web API search page)."""

    page = obj(payload).get("tracks")
    found = [track(t) for t in items(page) if isinstance(t, dict)]
    return clean({"tracks": found[:limit], "total_matches": to_int(obj(page).get("total"))})
