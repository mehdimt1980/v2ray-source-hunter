from __future__ import annotations

from .base64_subscription import extract_base64_uris
from .clash_yaml import extract_clash_uris
from .html_links import extract_html_uris
from .raw_uri import extract_raw_uris


def extract_all(text: str) -> list[str]:
    out: list[str] = []
    out.extend(extract_raw_uris(text))
    out.extend(extract_base64_uris(text))
    out.extend(extract_clash_uris(text))
    out.extend(extract_html_uris(text))
    return list(dict.fromkeys(out))
