import pytest

from checkleaked_spotify_mcp.config import MISSING_KEY_MESSAGE, load_settings

DIRECT_KEY = "sapi_" + "ab12" * 16
RAPID_KEY = "0123456789abcdefmsh0123456789abcdefp1a2b3cjsn0123456789ab"


def test_missing_key_is_reported_not_raised():
    settings = load_settings({})
    assert settings.api_key is None
    assert settings.error == MISSING_KEY_MESSAGE
    for url in ("https://spotify.checkleaked.cc/pricing#trial", "https://rapidapi.com/airaudoeduardo/api/spotify81", "https://spotify.checkleaked.cc/pricing"):
        assert url in settings.error


def test_rapidapi_is_the_default():
    settings = load_settings({"SPOTIFY_API_KEY": RAPID_KEY})
    assert (settings.provider, settings.provider_source, settings.sdk_provider) == ("rapidapi", "default", "rapidapi")
    assert settings.error is None


@pytest.mark.parametrize("key", [DIRECT_KEY, "123e4567-e89b-12d3-a456-426614174000"])
def test_direct_keys_are_detected(key):
    settings = load_settings({"SPOTIFY_API_KEY": key})
    assert (settings.provider, settings.provider_source, settings.sdk_provider) == ("direct", "key", "proxy")


@pytest.mark.parametrize(("value", "expected"), [("direct", "direct"), ("PROXY", "direct"), (" rapidapi ", "rapidapi")])
def test_explicit_provider_wins(value, expected):
    settings = load_settings({"SPOTIFY_API_KEY": DIRECT_KEY, "SPOTIFY_API_PROVIDER": value})
    assert (settings.provider, settings.provider_source) == (expected, "env")


def test_bad_provider_is_reported():
    settings = load_settings({"SPOTIFY_API_KEY": RAPID_KEY, "SPOTIFY_API_PROVIDER": "spotify"})
    assert "SPOTIFY_API_PROVIDER='spotify' is not valid" in settings.error


def test_quotes_and_spaces_are_stripped():
    settings = load_settings({"SPOTIFY_API_KEY": f' "{RAPID_KEY}" ', "SPOTIFY_API_BASE": "https://example.test/api/"})
    assert settings.api_key == RAPID_KEY
    assert settings.base_url == "https://example.test/api"


def test_bad_base_url_is_reported():
    assert "is not a URL" in load_settings({"SPOTIFY_API_KEY": RAPID_KEY, "SPOTIFY_API_BASE": "localhost:3029"}).error
