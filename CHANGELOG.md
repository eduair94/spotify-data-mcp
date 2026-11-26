# Changelog

## Hosted server, 2026-11-26

- Two hosted-only tools, `get_play_count_history` and `get_artist_history`: daily series from
  the API's `/history` endpoints (collected since 2026-11-26). The package itself is unchanged.

## Hosted server, 2026-11-25

- The hosted server at `https://spotify-proxy.checkleaked.cc/mcp` also takes tool calls with
  no key, paid per call over [x402](https://www.x402.org): $0.005 in USDC on Base, settled only
  when the tool succeeds. The package itself is unchanged.

## 0.1.1 - 2026-11-01

- A hosted remote server at `https://spotify-proxy.checkleaked.cc/mcp` (Streamable HTTP) for
  Claude.ai, ChatGPT and other remote MCP clients: the same 12 tools, keys from
  spotify.checkleaked.cc by `Authorization: Bearer` or `?key=`. Listed in `server.json`.

## 0.1.0 - 2026-11-01

First release.

- 12 read-only tools over the CheckLeaked Spotify Data API: `search`, `get_tracks`,
  `get_track_play_count`, `get_track_insights`, `get_artists_stats`, `get_artist_overview`,
  `get_artist_insights`, `get_related_artists`, `get_album`, `get_playlist`, `get_chart`,
  `isrc_lookup`.
- Ids, `spotify:` URIs and `open.spotify.com` URLs accepted everywhere; bad input is
  rejected before a request is spent.
- RapidAPI (`spotify81`) and direct keys; direct keys are detected from their format.
- Readable errors for a missing or invalid key, trial limits, rate limits, exhausted quotas
  and outages.
- Also published as a container image, `ghcr.io/eduair94/spotify-data-mcp` (linux/amd64 and
  linux/arm64).
