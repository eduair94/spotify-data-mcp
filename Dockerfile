# The MCP server as a container, for clients that run servers with Docker:
#   docker run -i --rm -e SPOTIFY_API_KEY ghcr.io/eduair94/spotify-data-mcp
# It speaks MCP over stdio, so -i is required and no port is exposed.
FROM python:3.12-slim

# The MCP Registry reads this label to confirm the image belongs to the server it lists.
LABEL io.modelcontextprotocol.server.name="cc.checkleaked/spotify-data" \
      org.opencontainers.image.title="Spotify Data MCP server" \
      org.opencontainers.image.description="Spotify play counts, monthly listeners, charts, artist stats, albums, playlists and ISRC lookup." \
      org.opencontainers.image.source="https://github.com/eduair94/spotify-data-mcp" \
      org.opencontainers.image.url="https://spotify.checkleaked.cc" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install . && rm -rf /app

USER nobody
ENTRYPOINT ["checkleaked-spotify-mcp"]
