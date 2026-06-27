from __future__ import annotations

import base64
import json
from urllib.parse import quote

import yaml


def _vmess(proxy: dict) -> str:
    payload = {
        "v": "2",
        "ps": proxy.get("name", ""),
        "add": proxy.get("server", ""),
        "port": str(proxy.get("port", "")),
        "id": proxy.get("uuid", ""),
        "aid": str(proxy.get("alterId", proxy.get("alterid", 0))),
        "net": proxy.get("network", "tcp"),
        "type": proxy.get("type", "none"),
        "host": proxy.get("servername", proxy.get("sni", "")),
        "path": proxy.get("ws-opts", {}).get("path", "") if isinstance(proxy.get("ws-opts"), dict) else "",
        "tls": "tls" if proxy.get("tls") else "",
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "vmess://" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _simple(proxy: dict, proto: str) -> str:
    server = proxy.get("server", "")
    port = proxy.get("port", "")
    name = quote(str(proxy.get("name", "")))
    if proto == "trojan":
        password = quote(str(proxy.get("password", "")))
        return f"trojan://{password}@{server}:{port}#{name}"
    if proto == "vless":
        uuid = quote(str(proxy.get("uuid", "")))
        return f"vless://{uuid}@{server}:{port}#{name}"
    if proto == "ss":
        method = quote(str(proxy.get("cipher", proxy.get("method", ""))))
        password = quote(str(proxy.get("password", "")))
        auth = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip("=")
        return f"ss://{auth}@{server}:{port}#{name}"
    return ""


def extract_clash_uris(text: str) -> list[str]:
    try:
        data = yaml.safe_load(text) or {}
    except Exception:
        return []
    proxies = data.get("proxies") if isinstance(data, dict) else None
    if not isinstance(proxies, list):
        return []
    out: list[str] = []
    for proxy in proxies:
        if not isinstance(proxy, dict):
            continue
        ptype = str(proxy.get("type", "")).lower()
        try:
            if ptype == "vmess":
                out.append(_vmess(proxy))
            elif ptype in {"vless", "trojan", "ss"}:
                value = _simple(proxy, ptype)
                if value:
                    out.append(value)
        except Exception:
            continue
    return list(dict.fromkeys(out))
