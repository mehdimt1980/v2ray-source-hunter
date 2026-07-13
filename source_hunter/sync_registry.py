from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import requests

from .quality_gate import evaluate_quality_gate


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "source-hunter-sync/0.1",
    }


def _decode_content(payload: dict[str, Any]) -> str:
    raw = payload.get("content") or ""
    return base64.b64decode(raw).decode("utf-8") if raw else "[]\n"


def _is_hunter_record(record: dict[str, Any]) -> bool:
    tags = record.get("tags") or []
    if "hunter" in tags:
        return True
    notes = str(record.get("notes") or "")
    return "source-hunter" in notes


def _merge_registry(existing: list[dict[str, Any]], hunter: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manual = [item for item in existing if isinstance(item, dict) and not _is_hunter_record(item)]
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in manual + hunter:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or item.get("url") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def sync_registry(
    *,
    source_path: Path = Path("registry/v2ray_finder_sources.json"),
    target_repo: str | None = None,
    target_path: str = "registry/sources.json",
    token: str | None = None,
    quality_gate: bool = True,
) -> dict:
    token = token or os.environ.get("TARGET_REPO_TOKEN") or os.environ.get("GH_PAT") or ""
    target_repo = target_repo or os.environ.get("TARGET_REPO") or "mehdimt1980/v2ray-finder"
    target_path = os.environ.get("TARGET_PATH") or target_path
    if not token or not target_repo:
        return {"ok": False, "message": "TARGET_REPO_TOKEN or TARGET_REPO missing"}

    if quality_gate:
        gate = evaluate_quality_gate(app_registry_path=source_path)
        if not gate["ok"]:
            return {
                "ok": False,
                "message": "quality gate failed; Android registry sync skipped",
                "quality_gate": gate,
            }

    hunter = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(hunter, list):
        return {"ok": False, "message": "hunter source file must be a JSON list"}

    api = "https://api.github.com/repos/" + target_repo + "/contents/" + target_path
    existing_response = requests.get(api, headers=_headers(token), timeout=20)
    sha = existing_response.json().get("sha") if existing_response.ok else None
    existing: list[dict[str, Any]] = []
    if existing_response.ok:
        try:
            decoded = _decode_content(existing_response.json())
            parsed = json.loads(decoded)
            existing = parsed if isinstance(parsed, list) else []
        except Exception:
            existing = []

    merged = _merge_registry(existing, hunter)
    content = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
    payload: dict[str, Any] = {
        "message": "Update Android source registry from source hunter",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    response = requests.put(api, headers=_headers(token), data=json.dumps(payload), timeout=30)
    return {
        "ok": response.ok,
        "status_code": response.status_code,
        "target_repo": target_repo,
        "target_path": target_path,
        "manual_preserved": len([x for x in existing if isinstance(x, dict) and not _is_hunter_record(x)]),
        "hunter_written": len(hunter),
        "total_written": len(merged),
        "message": response.text[:500],
    }


if __name__ == "__main__":
    result = sync_registry()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get("ok") else 1)
