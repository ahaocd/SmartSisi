from __future__ import annotations

from typing import Mapping, Optional, Tuple
from urllib.parse import ParseResult, parse_qs


def _pick_first(values) -> str:
    if not values:
        return ""
    if isinstance(values, str):
        return values
    return str(values[0])


def resolve_token(parsed: ParseResult, headers: Optional[Mapping[str, str]] = None) -> str:
    query = parse_qs(parsed.query or "")
    token = _pick_first(query.get("token"))
    if token:
        return token

    if not headers:
        return ""

    for key in ("x-sisi-token", "authorization"):
        value = headers.get(key)
        if value:
            if key == "authorization" and value.lower().startswith("bearer "):
                return value[7:].strip()
            return value.strip()
    return ""


def check_token(
    parsed: ParseResult,
    headers: Optional[Mapping[str, str]],
    required_token: str,
) -> Tuple[bool, str]:
    expected = (required_token or "").strip()
    if not expected:
        return True, "token_not_required"

    actual = resolve_token(parsed, headers).strip()
    if not actual:
        return False, "missing_token"
    if actual != expected:
        return False, "invalid_token"
    return True, "ok"

