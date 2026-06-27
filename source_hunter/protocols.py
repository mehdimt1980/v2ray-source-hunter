from __future__ import annotations

import base64
import json
from urllib.parse import urlparse


def protocol_of(config: str) -> str:
    return config.split("://", 1)[0].lower() if "://" in config else "unknown"


def protocol_counts(configs: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for cfg in configs:
        proto = protocol_of(cfg)
        out[proto] = out.get(proto, 0) + 1
    return dict(sorted(out.items()))


def endpoint_from_config(config: str) -> tuple[str, int] | None:
    proto = protocol_of(config)
    try:
        if proto == "vmess":
            payload = config.split("://", 1)[1]
            missing = len(payload) % 4
            if missing:
                payload += "=" * (4 - missing)
            data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode(errors="ignore"))
            host = str(data.get("add") or "").strip()
            port = int(data.get("port") or 0)
            return (host, port) if host and port else None
        parsed = urlparse(config)
        host = parsed.hostname
        port = parsed.port
        return (host, int(port)) if host and port else None
    except Exception:
        return None
