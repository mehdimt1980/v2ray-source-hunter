from __future__ import annotations

import html
import re
from urllib.parse import unquote

from .raw_uri import extract_raw_uris

HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)


def extract_html_uris(text: str) -> list[str]:
    values = []
    body = html.unescape(text or "")
    values.extend(extract_raw_uris(body))
    for href in HREF_RE.findall(body):
        decoded = unquote(html.unescape(href))
        values.extend(extract_raw_uris(decoded))
    return list(dict.fromkeys(values))
