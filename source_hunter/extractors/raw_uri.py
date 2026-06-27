from __future__ import annotations

import re

URI_RE = re.compile(
    r"(?:vmess|vless|trojan|ss|ssr)://[A-Za-z0-9+/=_\-@:.?&#%]+",
    re.IGNORECASE,
)


def extract_raw_uris(text: str) -> list[str]:
    return list(dict.fromkeys(URI_RE.findall(text or "")))
