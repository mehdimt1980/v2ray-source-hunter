from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass
class RealCheckSummary:
    requested: bool = False
    available: bool = False
    checked: int = 0
    ok: int = 0
    note: str = ""

    @property
    def success_rate(self) -> float:
        return round(self.ok / self.checked, 4) if self.checked else 0.0

    def to_dict(self) -> dict:
        return {
            "requested": self.requested,
            "available": self.available,
            "checked": self.checked,
            "ok": self.ok,
            "success_rate": self.success_rate,
            "note": self.note,
        }


def run_optional_real_check(configs: list[str], *, max_items: int = 10) -> RealCheckSummary:
    enabled = os.environ.get("HUNTER_REAL_CHECK", "").lower() in {"1", "true", "yes"}
    path = os.environ.get("XRAY_BINARY") or ""
    if not enabled:
        return RealCheckSummary(requested=False, available=False, note="disabled")
    if not path or not os.path.isfile(path):
        return RealCheckSummary(requested=True, available=False, note="XRAY_BINARY missing")
    try:
        proc = subprocess.run([path, "version"], capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            return RealCheckSummary(requested=True, available=False, note=proc.stderr[:200])
    except Exception as exc:
        return RealCheckSummary(requested=True, available=False, note=str(exc))

    try:
        from v2ray_finder.real_validation import check_real_validation_batch
    except Exception as exc:
        return RealCheckSummary(requested=True, available=False, note="v2ray_finder.real_validation unavailable: " + str(exc))

    sample = configs[:max_items]
    if not sample:
        return RealCheckSummary(requested=True, available=True, checked=0, ok=0, note="no configs")
    try:
        rows = check_real_validation_batch(
            sample,
            max_workers=2,
            timeout=8.0,
            binary_path=path,
            auto_download=False,
            stability_attempts=1,
        )
        ok = sum(1 for row in rows if getattr(row, "validation_ok", False))
        return RealCheckSummary(requested=True, available=True, checked=len(rows), ok=ok, note="real validation completed")
    except Exception as exc:
        return RealCheckSummary(requested=True, available=True, checked=0, ok=0, note="real validation failed: " + str(exc))
