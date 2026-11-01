"""Offline test helpers: a fake ``requests.Session`` serving recorded API answers.

The fake sits under the real checkleaked-spotify-api SDK, so the tests also
check the SDK calls the server makes (paths, query strings, headers) and the
SDK's own error handling. The fixtures are real API answers captured on
2026-11-01 (and 2026-10-13), trimmed for size.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlsplit

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from checkleaked_spotify_mcp.config import load_settings
from checkleaked_spotify_mcp.server import create_server

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

Reply = Tuple[int, Any, Dict[str, str]]
Route = Union[Reply, Callable[[Dict[str, str]], Reply]]


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def ok(body: Any, headers: Optional[Dict[str, str]] = None) -> Reply:
    return (200, body, headers or {})


class FakeResponse:
    def __init__(self, status: int, body: Any, headers: Dict[str, str]) -> None:
        self.status_code = status
        self.headers = {key.lower(): value for key, value in headers.items()}
        if isinstance(body, (dict, list)):
            self.content = json.dumps(body).encode("utf-8")
            self.headers.setdefault("content-type", "application/json; charset=utf-8")
        elif body is None:
            self.content = b""
        else:
            self.content = body.encode("utf-8") if isinstance(body, str) else body
            self.headers.setdefault("content-type", "text/plain")


class FakeSession:
    """Routes requests by path (``/spotify-data`` prefix removed) and records them."""

    def __init__(self, routes: Optional[Dict[str, Route]] = None) -> None:
        self.routes: Dict[str, Route] = dict(routes or {})
        self.calls: List[Dict[str, Any]] = []

    def request(self, method: str, url: str, headers: Any = None, data: Any = None, timeout: Any = None) -> FakeResponse:
        parts = urlsplit(url)
        path = parts.path
        if path.startswith("/spotify-data/"):
            path = path[len("/spotify-data") :]
        query = {key: values[0] for key, values in parse_qs(parts.query).items()}
        self.calls.append(
            {
                "method": method,
                "url": url,
                "base": f"{parts.scheme}://{parts.netloc}",
                "path": path,
                "query": query,
                "headers": {k.lower(): v for k, v in dict(headers or {}).items()},
            }
        )
        route = self.routes.get(path)
        if route is None:
            return FakeResponse(404, {"message": f"Endpoint '{path}' does not exist"}, {})
        status, body, reply_headers = route(query) if callable(route) else route
        return FakeResponse(status, body, reply_headers)

    def close(self) -> None:
        pass


def make_server(routes: Optional[Dict[str, Route]] = None, env: Optional[Dict[str, str]] = None):
    session = FakeSession(routes)
    settings = load_settings({"SPOTIFY_API_KEY": "test-rapidapi-key"} if env is None else env)
    return create_server(settings, session=session), session


def call(server: Any, name: str, arguments: Dict[str, Any]) -> Any:
    """Call a tool in-process; return its decoded JSON (ToolError propagates)."""

    async def run() -> Any:
        return await server.call_tool(name, arguments)

    result = anyio.run(run)
    assert not result.is_error, result.content
    assert len(result.content) == 1 and result.content[0].type == "text"
    return json.loads(result.content[0].text)


def call_error(server: Any, name: str, arguments: Dict[str, Any]) -> str:
    """Call a tool that must fail; return the error text the model reads.

    The MCP SDK prefixes every tool error with ``Error executing tool <name>: ``.
    """

    with pytest.raises(ToolError) as caught:
        call(server, name, arguments)
    text = str(caught.value)
    prefix = f"Error executing tool {name}: "
    assert text.startswith(prefix), text
    return text[len(prefix) :]
