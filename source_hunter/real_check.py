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
    path = os.environ.get("XRAY_BINARY") or os.environ.get("SING_BOX_BINARY") or ""
    if not path:
        return RealCheckSummary(requested=False, available=False, note="disabled")
    if not os.path.isfile(path):
        return RealCheckSummary(requested=True, available=False, note="binary not found")
    # Conservative placeholder: verify the binary can start and report version.
    # Full per-config proxy probing can be enabled later using the app's xray adapter.
    try:
        proc = subprocess.run([path, "version"], capture_output=True, text=True, timeout=10)
        available = proc.returncode == 0
        return RealCheckSummary(requested=True, available=available, checked=0, ok=0, note="binary available" if available else proc.stderr[:200])
    except Exception as exc:
        return RealCheckSummary(requested=True, available=False, note=str(exc))
