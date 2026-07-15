from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class RealCheckSummary:
    requested: bool = False
    available: bool = False
    checked: int = 0
    ok: int = 0
    validation_location: str = ""
    validated_configs: list[dict[str, Any]] | None = None
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
            "validation_location": self.validation_location,
            "validated_config_count": len(self.validated_configs or []),
            "note": self.note,
        }

    def validated_rows(self) -> list[dict[str, Any]]:
        return self.validated_configs or []


def run_optional_real_check(configs: list[str], *, max_items: int = 30) -> RealCheckSummary:
    enabled = os.environ.get("HUNTER_REAL_CHECK", "").lower() in {"1", "true", "yes"}
    path = os.environ.get("XRAY_BINARY") or ""
    validation_location = os.environ.get("HUNTER_REAL_CHECK_LOCATION", "github_actions_eu")
    if not enabled:
        return RealCheckSummary(requested=False, available=False, note="disabled")
    if not path or not os.path.isfile(path):
        return RealCheckSummary(
            requested=True,
            available=False,
            validation_location=validation_location,
            note="XRAY_BINARY missing",
        )
    try:
        proc = subprocess.run([path, "version"], capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            return RealCheckSummary(
                requested=True,
                available=False,
                validation_location=validation_location,
                note=proc.stderr[:200],
            )
    except Exception as exc:
        return RealCheckSummary(
            requested=True,
            available=False,
            validation_location=validation_location,
            note=str(exc),
        )

    checker, backend, import_error = _load_real_checker()
    if checker is None:
        return RealCheckSummary(
            requested=True,
            available=False,
            validation_location=validation_location,
            note=import_error,
        )

    sample = configs[:max_items]
    if not sample:
        return RealCheckSummary(
            requested=True,
            available=True,
            checked=0,
            ok=0,
            validation_location=validation_location,
            note="no configs",
        )
    try:
        rows = checker(
            sample,
            max_workers=4,
            timeout=12.0,
            binary_path=path,
            auto_download=False,
        )
        ok = sum(1 for row in rows if _real_row_ok(row))
        passed = [
            _real_row_to_dict(row, validation_location=validation_location)
            for row in rows
            if _real_row_ok(row)
        ]
        return RealCheckSummary(
            requested=True,
            available=True,
            checked=len(rows),
            ok=ok,
            validation_location=validation_location,
            validated_configs=passed,
            note=f"real validation completed via {backend}",
        )
    except Exception as exc:
        return RealCheckSummary(
            requested=True,
            available=True,
            checked=0,
            ok=0,
            validation_location=validation_location,
            note="real validation failed: " + str(exc),
        )


def _load_real_checker() -> tuple[Callable[..., list] | None, str, str]:
    extra_path = os.environ.get("HUNTER_V2RAY_FINDER_PATH", "").strip()
    if extra_path:
        repo_path = Path(extra_path)
        if repo_path.is_dir():
            sys.path.insert(0, str(repo_path))

    try:
        from v2ray_finder.real_validation import check_real_validation_batch

        def _legacy_checker(configs: list[str], **kwargs) -> list:
            return check_real_validation_batch(configs, stability_attempts=1, **kwargs)

        return _legacy_checker, "v2ray_finder.real_validation", ""
    except Exception as legacy_exc:
        try:
            from v2ray_finder.xray_connectivity import check_real_connectivity_batch

            def _connectivity_checker(configs: list[str], **kwargs) -> list:
                return check_real_connectivity_batch(configs, **kwargs)

            return _connectivity_checker, "v2ray_finder.xray_connectivity", ""
        except Exception as connectivity_exc:
            return (
                None,
                "",
                "v2ray_finder real validation unavailable: "
                f"real_validation={legacy_exc}; xray_connectivity={connectivity_exc}",
            )


def _real_row_ok(row: object) -> bool:
    if bool(getattr(row, "validation_ok", False)):
        return True
    return bool(getattr(row, "google_204_ok", False) or getattr(row, "reachable", False))


def _real_row_to_dict(row: object, *, validation_location: str) -> dict[str, Any]:
    config = str(getattr(row, "config", "") or "")
    return {
        "config": config,
        "protocol": str(getattr(row, "protocol", "") or ""),
        "validation_location": validation_location,
        "xray_ok": _real_row_ok(row),
        "google_204_ok": bool(getattr(row, "google_204_ok", False)),
        "reachable": bool(getattr(row, "reachable", False)),
        "latency_ms": getattr(row, "latency_ms", None),
        "quality_score": getattr(row, "quality_score", None),
        "error": getattr(row, "error", None),
        "socks_port": getattr(row, "socks_port", None),
        "retried": bool(getattr(row, "retried", False)),
    }
