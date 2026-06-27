from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import requests


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "source-hunter-sync/0.1",
    }


def sync_registry(
    *,
    source_path: Path = Path("registry/v2ray_finder_sources.json"),
    target_repo: str | None = None,
    target_path: str = "registry/hunter_sources.json",
    token: str | None = None,
) -> dict:
    token = token or os.environ.get("TARGET_REPO_TOKEN") or ""
    target_repo = target_repo or os.environ.get("TARGET_REPO") or ""
    target_path = os.environ.get("TARGET_PATH") or target_path
    if not token or not target_repo:
        return {"ok": False, "message": "TARGET_REPO_TOKEN or TARGET_REPO missing"}
    content = source_path.read_text(encoding="utf-8")
    api = "https://api.github.com/repos/" + target_repo + "/contents/" + target_path
    existing = requests.get(api, headers=_headers(token), timeout=20)
    sha = existing.json().get("sha") if existing.ok else None
    payload = {
        "message": "Update hunter source registry",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    response = requests.put(api, headers=_headers(token), data=json.dumps(payload), timeout=30)
    return {"ok": response.ok, "status_code": response.status_code, "message": response.text[:500]}


if __name__ == "__main__":
    print(json.dumps(sync_registry(), ensure_ascii=False, indent=2))
