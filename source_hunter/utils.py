from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def stable_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:72]
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}" if slug else digest


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dedupe_keep_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys([x for x in items if x]))
