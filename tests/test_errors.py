"""API errors become readable tool errors; a missing key never crashes the server."""

from conftest import call_error, load, make_server

TRACK = "0VjIjW4GlUZAMYd2vXMi3b"
TRIAL = "https://spotify.checkleaked.cc/pricing#trial"
RAPIDAPI = "https://rapidapi.com/airaudoeduardo/api/spotify81"
DIRECT_ENV = {"SPOTIFY_API_KEY": "sapi_" + "ab" * 32}


def envelope(status, code, message, **extra):
    """The proxy's error envelope (servers/spotify-data-api-proxy.ts proxyErrorBody)."""

    return {
        "success": False,
        "error": code.replace("_", " ").title(),
        "message": message,
        "code": code,
        "status": status,
        "status_code": status,
        "retryable": status >= 500 or status == 429,
        "request_id": "req-123",
        **extra,
    }


def fail(status, body, headers=None, env=None):
    server, session = make_server({"/partner/tracks/count": (status, body, headers or {})}, env=env)
    return call_error(server, "get_track_play_count", {"tracks": [TRACK]}), session


def test_missing_key_every_tool_explains_where_to_get_one():
    server, session = make_server(env={})
    for tool, args in [
        ("search", {"query": "bad bunny"}),
        ("get_track_play_count", {"tracks": [TRACK]}),
        ("get_chart", {}),
    ]:
        message = call_error(server, tool, args)
        assert "SPOTIFY_API_KEY is not set" in message
        assert TRIAL in message and RAPIDAPI in message
    assert session.calls == []


def test_invalid_rapidapi_key():
    message, _ = fail(401, {"message": "Invalid API key. Go to https://docs.rapidapi.com/docs/keys for more info."})
    assert "rejected SPOTIFY_API_KEY (HTTP 401)" in message
    assert "SPOTIFY_API_PROVIDER=direct" in message
    assert TRIAL in message


def test_invalid_direct_key():
    body = envelope(401, "INVALID_API_KEY", 'The API key is not valid. Check the "x-rapidapi-key" header.')
    message, _ = fail(401, body, env=DIRECT_ENV)
    assert "HTTP 401 INVALID_API_KEY" in message
    assert "SPOTIFY_API_PROVIDER=rapidapi" in message
    assert "request id req-123" in message


def test_expired_key():
    body = envelope(401, "KEY_EXPIRED", "This API key has passed its expiry date. Renew it to reactivate the same key.")
    message, _ = fail(401, body, env=DIRECT_ENV)
    assert message.startswith("This API key has expired.")
    assert "https://spotify.checkleaked.cc/pricing" in message


def test_trial_route_not_included():
    body = envelope(
        403,
        "TRIAL_ROUTE_NOT_INCLUDED",
        "This endpoint is not included in the free trial key. Get a paid key at "
        "https://spotify.checkleaked.cc/pricing to use downloads, AI, tracking, webhooks and snapshots.",
    )
    message, _ = fail(403, body, env=DIRECT_ENV)
    assert message.startswith("This endpoint is not included in the free trial key.")
    assert "https://spotify.checkleaked.cc/pricing" in message


def test_rapidapi_not_subscribed():
    message, _ = fail(403, {"message": "You are not subscribed to this API."})
    assert "not subscribed to the spotify81 API" in message and RAPIDAPI in message


def test_rate_limited_with_retry_after():
    body = envelope(429, "RATE_LIMITED", "Requests must be at least 1 seconds apart.", retry_after_s=1)
    message, session = fail(429, body, headers={"Retry-After": "1"})
    assert "Rate limited" in message and "Retry after 1 s." in message
    # The SDK retried once (honouring Retry-After), then gave up.
    assert len(session.calls) == 2


def test_quota_exceeded_is_not_retried():
    message, session = fail(429, {"message": "You have exceeded the MONTHLY quota for Requests on your current plan, BASIC."})
    assert "QUOTA_EXCEEDED" in message and "rapidapi.com/airaudoeduardo/api/spotify81/pricing" in message
    assert len(session.calls) == 1


def test_service_unavailable():
    body = envelope(503, "UPSTREAM_UNAVAILABLE", "Spotify is temporarily unavailable. Please retry shortly.", retry_after_s=0)
    message, session = fail(503, body, headers={"Retry-After": "0"})
    assert "temporarily unavailable (HTTP 503 UPSTREAM_UNAVAILABLE)" in message
    assert "https://spotify.checkleaked.cc/status" in message
    assert len(session.calls) == 2


def test_cloudflare_plain_text_5xx():
    message, _ = fail(502, "error code: 502", headers={"Retry-After": "0"})
    assert "temporarily unavailable (HTTP 502)" in message


def test_bad_request_message_is_passed_through():
    message, _ = fail(400, load("error_invalid_ids.json"))
    assert message.startswith('The API rejected the request: "ids" must be a comma-separated list')


def test_rapidapi_unlisted_endpoint_points_to_direct_keys():
    message, _ = fail(404, {"message": "Endpoint '/partner/tracks/count' does not exist"})
    assert "RapidAPI does not list this endpoint yet" in message and TRIAL in message


def test_error_inside_a_2xx_body():
    body = {"error": True, "code": "UPSTREAM_THROTTLED", "message": "Spotify is throttling this request."}
    message, _ = fail(200, body)
    assert "Spotify is throttling this request" in message


def test_network_failure():
    from checkleaked_spotify_mcp.config import load_settings
    from checkleaked_spotify_mcp.server import create_server

    class Broken:
        def request(self, *args, **kwargs):
            raise ConnectionError("connection refused")

    server = create_server(load_settings({"SPOTIFY_API_KEY": "k"}), session=Broken())
    assert call_error(server, "get_track_play_count", {"tracks": [TRACK]}).startswith("Could not reach the Spotify Data API")


def test_unexpected_payload_is_a_readable_error(monkeypatch):
    from checkleaked_spotify_mcp import shape

    def boom(payload):
        raise KeyError("tracks")

    monkeypatch.setattr(shape, "play_counts", boom)
    message, _ = fail(200, {"tracks": []})
    assert message.startswith("Unexpected error in get_track_play_count: KeyError")
    assert "github.com/eduair94/spotify-data-mcp/issues" in message


def test_plan_does_not_include_endpoint():
    # express-api-key's "insufficient role" refusal: a 403 that carries INVALID_API_KEY.
    body = envelope(403, "INVALID_API_KEY", "This API key's plan does not include this endpoint.")
    message, _ = fail(403, body, env=DIRECT_ENV)
    assert message.startswith("This API key's plan does not include this endpoint (HTTP 403 INVALID_API_KEY).")
    assert "SPOTIFY_API_PROVIDER" not in message
