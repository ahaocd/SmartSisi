from urllib.parse import urlparse

from gateway.app.auth import check_token, resolve_token


def test_resolve_token_from_query():
    parsed = urlparse("/device?token=abc")
    assert resolve_token(parsed, {}) == "abc"


def test_resolve_token_from_header():
    parsed = urlparse("/device")
    headers = {"x-sisi-token": "abc"}
    assert resolve_token(parsed, headers) == "abc"


def test_check_token_disabled():
    parsed = urlparse("/device")
    ok, reason = check_token(parsed, {}, "")
    assert ok is True
    assert reason == "token_not_required"


def test_check_token_mismatch():
    parsed = urlparse("/device?token=bad")
    ok, reason = check_token(parsed, {}, "good")
    assert ok is False
    assert reason == "invalid_token"

