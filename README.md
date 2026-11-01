# Spotify Data MCP Server

<!-- mcp-name: cc.checkleaked/spotify-data -->

[![PyPI](https://img.shields.io/pypi/v/checkleaked-spotify-mcp)](https://pypi.org/project/checkleaked-spotify-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/checkleaked-spotify-mcp)](https://pypi.org/project/checkleaked-spotify-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/eduair94/spotify-data-mcp/blob/main/LICENSE)

An [MCP](https://modelcontextprotocol.io) server that lets AI assistants (Claude Desktop,
Claude Code, Cursor, VS Code and other MCP clients) look up Spotify data: **track play
counts, artist monthly listeners, world rank and top cities, Top 200 and viral charts by
country, albums and playlists with per-track play counts, search, ISRC lookup, and genres,
moods and BPM**.

It runs on your machine and calls the
[CheckLeaked Spotify Data API](https://spotify.checkleaked.cc) with **your own API key**.
A free trial key needs no card.

```bash
uvx checkleaked-spotify-mcp
```

> Unofficial. Not affiliated with, endorsed by or sponsored by Spotify.
> Spotify is a trademark of Spotify AB.

## Ask things like

- "What are the monthly listeners of Bad Bunny and Karol G?"
- "Give me the play counts of every track on this album:
  https://open.spotify.com/album/3RQQmkQEvNCY4prGKE6oc5"
- "Show today's Top 200 in Brazil, top 20 only."
- "Which cities listen to Taylor Swift the most?"
- "Compare the streams of Blinding Lights and Bohemian Rhapsody."
- "List the first 30 tracks of Today's Top Hits with their play counts, sorted by plays."
- "What genres, moods and BPM does The Weeknd's music have?"
- "Which Spotify track has the ISRC USUG11904206?"
- "Who are the artists related to Rosalía, and how many monthly listeners does each have?"

## 1. Get an API key

Every user needs their own key. Pick one:

| Option | Cost | Where | `SPOTIFY_API_PROVIDER` |
| --- | --- | --- | --- |
| **Free trial**: 500 requests over 7 days, no card | Free | [spotify.checkleaked.cc/pricing#trial](https://spotify.checkleaked.cc/pricing#trial) | `direct` (detected automatically) |
| **RapidAPI** listing `spotify81` | Free Basic plan, paid tiers | [rapidapi.com/airaudoeduardo/api/spotify81](https://rapidapi.com/airaudoeduardo/api/spotify81) | `rapidapi` (default) |
| **Direct paid key** | From the pricing page | [spotify.checkleaked.cc/pricing](https://spotify.checkleaked.cc/pricing) | `direct` (detected automatically) |

Keys issued by spotify.checkleaked.cc (they start with `sapi_`) are sent to the direct API
automatically; any other key is treated as a RapidAPI key. Set `SPOTIFY_API_PROVIDER` only
to override that.

## 2. Add it to your MCP client

The server is published on PyPI and runs with [`uvx`](https://docs.astral.sh/uv/) (part of
`uv`; install it with `pip install uv` or see the
[uv install guide](https://docs.astral.sh/uv/getting-started/installation/)). `uvx`
downloads the package into a cached, isolated environment on first use. Replace
`your-api-key` with your key in the snippets below.

### Claude Desktop

Edit `claude_desktop_config.json` (Settings > Developer > Edit Config; macOS:
`~/Library/Application Support/Claude/claude_desktop_config.json`, Windows:
`%APPDATA%\Claude\claude_desktop_config.json`) and restart Claude Desktop:

```json
{
  "mcpServers": {
    "spotify-data": {
      "command": "uvx",
      "args": ["checkleaked-spotify-mcp"],
      "env": {
        "SPOTIFY_API_KEY": "your-api-key"
      }
    }
  }
}
```

If Claude Desktop cannot find `uvx`, put its full path in `command` (run `which uvx` on
macOS / Linux or `where uvx` on Windows).

### Claude Code

```bash
claude mcp add spotify-data -s user -e SPOTIFY_API_KEY=your-api-key -- uvx checkleaked-spotify-mcp
```

### Cursor

Add to `~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project):

```json
{
  "mcpServers": {
    "spotify-data": {
      "command": "uvx",
      "args": ["checkleaked-spotify-mcp"],
      "env": {
        "SPOTIFY_API_KEY": "your-api-key"
      }
    }
  }
}
```

### VS Code (GitHub Copilot agent mode)

Add to `.vscode/mcp.json`. VS Code asks for the key once and stores it securely:

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "spotify-api-key",
      "description": "Spotify Data API key",
      "password": true
    }
  ],
  "servers": {
    "spotify-data": {
      "type": "stdio",
      "command": "uvx",
      "args": ["checkleaked-spotify-mcp"],
      "env": {
        "SPOTIFY_API_KEY": "${input:spotify-api-key}"
      }
    }
  }
}
```

### Any other MCP client

Run `uvx checkleaked-spotify-mcp` (stdio transport) with `SPOTIFY_API_KEY` in its
environment. Without `uvx`: `pip install checkleaked-spotify-mcp`, then run
`checkleaked-spotify-mcp` (or `python -m checkleaked_spotify_mcp`).

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `SPOTIFY_API_KEY` | yes | Your API key (see above). |
| `SPOTIFY_API_PROVIDER` | no | `rapidapi` (RapidAPI `spotify81.p.rapidapi.com`) or `direct` (`https://spotify-proxy.checkleaked.cc/spotify-data`). Default: detected from the key. |
| `SPOTIFY_API_BASE` | no | Override the base URL of the chosen provider. |

Without a key the server still starts, and every tool answers with an error that says where
to get a free key, so you can see what is wrong from inside your chat.

## Tools

All tools are read-only. Every id parameter accepts a bare id, a `spotify:` URI or an
`open.spotify.com` URL (with or without `/intl-xx/` and `?si=`).

| Tool | What it returns | Batch | Requests |
| --- | --- | --- | --- |
| `search` | Tracks, artists, albums or playlists matching a query, with ids and URLs (optionally play counts for tracks) | up to 20 hits | 1 |
| `get_tracks` | Track details: artists, album, release date, duration, ISRC, popularity, play count; optional genres / moods / BPM / credits | 50 tracks | 1 |
| `get_track_play_count` | Lifetime play counts with name, artists, release date | 50 tracks | 1 |
| `get_track_insights` | Genres, moods, activities (with weights), BPM, credits, lyrics flag, languages | 50 tracks | 1 |
| `get_artists_stats` | Monthly listeners, followers, world rank, popularity, genres, top 5 cities | 50 artists | 1 |
| `get_artist_overview` | Profile with stats, top tracks with play counts, latest release, discography counts, related artists, biography, links | 1 artist | 1 |
| `get_artist_insights` | Genre, mood and tempo profile from the artist's top tracks | 20 artists | 1 |
| `get_related_artists` | "Fans also like" artists | 1 artist | 1 |
| `get_album` | Album details and every track with its play count, plus the album total | 1 album | 1 |
| `get_playlist` | Name, owner, followers, description and up to 100 tracks per page with play counts | 100 tracks | 2 on the first page, then 1 |
| `get_chart` | Top 200, viral, top artists or top albums for a country (daily or weekly, latest or by date), optional play counts | up to 200 entries | 1 |
| `isrc_lookup` | Spotify tracks for an ISRC | 1 ISRC | 1 |

Outputs are compact JSON: ids, names, numbers and `open.spotify.com` URLs, with lists capped,
so they fit in the model's context. Notes:

- Spotify shows a play count of **0** for tracks with fewer than 1,000 plays.
- Play counts are lifetime plays; chart `streams` are the plays in that chart's day or week.
- Results may be cached by the API for a while (play counts about an hour).
- Lyrics, audio downloads, webhooks, tracking and AI endpoints of the API are deliberately
  not exposed.

## Privacy

The server only talks to the API you configure (RapidAPI's `spotify81.p.rapidapi.com` or
`spotify-proxy.checkleaked.cc`). It sends your key in the `x-rapidapi-key` header, stores
nothing on disk and has no telemetry. Requests carry a `checkleaked-spotify-mcp/<version>`
user agent.

## Development

```bash
git clone https://github.com/eduair94/spotify-data-mcp
cd spotify-data-mcp
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                          # offline tests (recorded API answers)
SPOTIFY_MCP_LIVE=1 SPOTIFY_API_KEY=... pytest -m live   # optional live smoke test
```

Built on the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
and the [`checkleaked-spotify-api`](https://pypi.org/project/checkleaked-spotify-api/) SDK.
API reference: [spotify-proxy.checkleaked.cc/docs](https://spotify-proxy.checkleaked.cc/docs).
Service status: [spotify.checkleaked.cc/status](https://spotify.checkleaked.cc/status).

## License

[MIT](https://github.com/eduair94/spotify-data-mcp/blob/main/LICENSE)
