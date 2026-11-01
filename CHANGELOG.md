# Changelog

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
