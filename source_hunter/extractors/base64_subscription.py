from __future__ import annotations

import base64
import binascii

from .raw_uri import extract_raw_uris


def _decode_maybe_base64(text: str) -> str:
    compact = "".join((text or "").split())
    if len(compact) < 16:
        return ""
    missing = len(compact) % 4
    if missing:
        compact += "=" * (4 - missing)
    try:
        raw = base64.b64decode(compact, validate=False)
        return raw.decode("utf-8", errors="ignore")
    except (binascii.Error, ValueError):
        return ""


def extract_base64_uris(text: str) -> list[str]:
    decoded = _decode_maybe_base64(text)
    return extract_raw_uris(decoded) if decoded else []
