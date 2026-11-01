"""Release metadata stays consistent, and the server never reaches excluded endpoints."""

import json
import pathlib
import re

import checkleaked_spotify_mcp
from checkleaked_spotify_mcp import server as server_module

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pyproject_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', text, re.MULTILINE).group(1)


def test_versions_match():
    manifest = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    version = _pyproject_version()
    assert checkleaked_spotify_mcp.__version__ == version
    assert manifest["version"] == version
    assert manifest["packages"][0]["version"] == version
    assert manifest["packages"][0]["identifier"] == "checkleaked-spotify-mcp"


def test_registry_name_is_in_the_readme():
    manifest = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert re.search(r"mcp-name: " + re.escape(manifest["name"]) + r"(\s|-->)", readme)
    assert len(manifest["description"]) <= 100


def test_excluded_endpoints_are_never_called():
    source = pathlib.Path(server_module.__file__).read_text(encoding="utf-8")
    for namespace in ("lyrics", "downloads", "webhooks", "tracking", "ai", "snapshots", "analysis"):
        assert not re.search(r"\bc\." + namespace + r"\b", source), namespace
    assert "c.request(" not in source and ".lyrics(" not in source
