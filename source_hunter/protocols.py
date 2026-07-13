from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, unquote, urlparse


def protocol_of(config: str) -> str:
    return config.split("://", 1)[0].lower() if "://" in config else "unknown"


def protocol_counts(configs: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for cfg in configs:
        proto = protocol_of(cfg)
        out[proto] = out.get(proto, 0) + 1
    return dict(sorted(out.items()))


def dedupe_by_normalized_identity(configs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cfg in configs:
        key = normalized_config_identity(cfg)
        if key in seen:
            continue
        seen.add(key)
        out.append(cfg)
    return out


def normalized_config_identities(configs: list[str]) -> set[str]:
    return {normalized_config_identity(cfg) for cfg in configs if cfg}


def normalized_config_identity(config: str) -> str:
    proto = protocol_of(config)
    try:
        if proto == "vmess":
            return _vmess_identity(config)
        if proto in {"vless", "trojan"}:
            return _standard_uri_identity(config)
        if proto == "ss":
            return _shadowsocks_identity(config)
        if proto == "ssr":
            return _ssr_identity(config)
    except Exception:
        pass
    return f"raw:{_strip_label(config)}"


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


def _vmess_identity(config: str) -> str:
    payload = config.split("://", 1)[1]
    data = _decode_json_payload(payload)
    host = _clean_host(str(data.get("add") or ""))
    port = _clean_port(data.get("port"))
    user_id = str(data.get("id") or "").strip().lower()
    network = str(data.get("net") or "").strip().lower()
    security = str(data.get("tls") or "").strip().lower()
    sni = _clean_host(str(data.get("sni") or data.get("host") or ""))
    path = str(data.get("path") or "").strip()
    return "|".join(["vmess", host, str(port), user_id, network, security, sni, path])


def _standard_uri_identity(config: str) -> str:
    parsed = urlparse(_strip_label(config))
    query = parse_qs(parsed.query, keep_blank_values=True)
    proto = parsed.scheme.lower()
    host = _clean_host(parsed.hostname or "")
    port = _clean_port(parsed.port)
    user = unquote(parsed.username or "").strip().lower()
    network = _first(query, "type", "network").lower()
    security = _first(query, "security", "tls").lower()
    sni = _clean_host(_first(query, "sni", "peer", "host"))
    path = _first(query, "path", "serviceName")
    return "|".join([proto, host, str(port), user, network, security, sni, path])


def _shadowsocks_identity(config: str) -> str:
    raw = _strip_label(config).split("://", 1)[1]
    before_query = raw.split("?", 1)[0].split("#", 1)[0]
    if "@" not in before_query:
        decoded = _decode_text_payload(before_query)
        if decoded:
            before_query = decoded
    method_password, endpoint = (
        before_query.rsplit("@", 1) if "@" in before_query else ("", before_query)
    )
    if ":" not in endpoint:
        return "raw:" + _strip_label(config)
    host, port_text = endpoint.rsplit(":", 1)
    if ":" not in method_password:
        method_password = _decode_text_payload(method_password) or method_password
    method, password = (
        method_password.split(":", 1) if ":" in method_password else (method_password, "")
    )
    return "|".join(
        [
            "ss",
            _clean_host(host),
            str(_clean_port(port_text)),
            method.strip().lower(),
            password.strip(),
        ]
    )


def _ssr_identity(config: str) -> str:
    decoded = _decode_text_payload(_strip_label(config).split("://", 1)[1])
    main = decoded.split("/?", 1)[0] if decoded else ""
    parts = main.split(":")
    if len(parts) < 6:
        return "raw:" + _strip_label(config)
    host, port, protocol, method, obfs, password = parts[:6]
    return "|".join(
        [
            "ssr",
            _clean_host(host),
            str(_clean_port(port)),
            protocol.strip().lower(),
            method.strip().lower(),
            obfs.strip().lower(),
            password.strip(),
        ]
    )


def _decode_json_payload(payload: str) -> dict:
    decoded = _decode_text_payload(payload)
    return json.loads(decoded or "{}")


def _decode_text_payload(payload: str) -> str:
    try:
        compact = payload.strip().replace("-", "+").replace("_", "/")
        compact = compact.split("#", 1)[0]
        missing = len(compact) % 4
        if missing:
            compact += "=" * (4 - missing)
        return base64.b64decode(compact.encode(), validate=False).decode(errors="ignore")
    except Exception:
        return ""


def _strip_label(config: str) -> str:
    return (config or "").strip().split("#", 1)[0]


def _first(query: dict[str, list[str]], *names: str) -> str:
    for name in names:
        values = query.get(name)
        if values:
            return unquote(values[0]).strip()
    return ""


def _clean_host(value: str) -> str:
    return value.strip().strip("[]").lower()


def _clean_port(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
