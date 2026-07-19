from __future__ import annotations

import os
import inspect
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


HTTP_ENDPOINTS = [
    ("google_204", "https://www.gstatic.com/generate_204"),
    ("cloudflare_trace", "https://www.cloudflare.com/cdn-cgi/trace"),
    ("cloudflare_204", "https://cp.cloudflare.com/generate_204"),
    ("apple_success", "https://www.apple.com/library/test/success.html"),
]


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
        endpoint_limit = int(os.environ.get("HUNTER_HTTP_ENDPOINT_MAX_PER_SOURCE", "3"))
        endpoint_counter = [0]
        endpoint_lock = threading.Lock()

        def _live_endpoint_probe(socks_port: int) -> dict[str, Any]:
            with endpoint_lock:
                if endpoint_counter[0] >= endpoint_limit:
                    return _empty_endpoint_result("sample limit")
                endpoint_counter[0] += 1
            return _run_http_endpoint_checks(socks_port)

        rows = checker(
            sample,
            max_workers=4,
            timeout=12.0,
            binary_path=path,
            auto_download=False,
            live_probe=_live_endpoint_probe,
        )
        ok = sum(1 for row in rows if _real_row_ok(row))
        passed_rows = [row for row in rows if _real_row_ok(row)]
        passed = [
            _real_row_to_dict(
                row,
                validation_location=validation_location,
                run_endpoint_checks=index < endpoint_limit,
            )
            for index, row in enumerate(passed_rows)
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
            if "live_probe" not in inspect.signature(check_real_validation_batch).parameters:
                kwargs.pop("live_probe", None)
            return check_real_validation_batch(configs, stability_attempts=1, **kwargs)

        return _legacy_checker, "v2ray_finder.real_validation", ""
    except Exception as legacy_exc:
        try:
            from v2ray_finder.xray_connectivity import check_real_connectivity_batch

            def _connectivity_checker(configs: list[str], **kwargs) -> list:
                if "live_probe" not in inspect.signature(check_real_connectivity_batch).parameters:
                    kwargs.pop("live_probe", None)
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


def _real_row_to_dict(
    row: object,
    *,
    validation_location: str,
    run_endpoint_checks: bool = True,
) -> dict[str, Any]:
    config = str(getattr(row, "config", "") or "")
    captured_endpoint_result = getattr(row, "endpoint_probe", None)
    if isinstance(captured_endpoint_result, dict):
        endpoint_result = captured_endpoint_result
    elif run_endpoint_checks:
        endpoint_result = _empty_endpoint_result("live endpoint checks unavailable")
    else:
        endpoint_result = _empty_endpoint_result("sample limit")
    return {
        "config": config,
        "protocol": str(getattr(row, "protocol", "") or ""),
        "validation_location": validation_location,
        "xray_ok": _real_row_ok(row),
        "google_204_ok": bool(getattr(row, "google_204_ok", False)),
        "reachable": bool(getattr(row, "reachable", False)),
        "http_endpoint_results": endpoint_result["results"],
        "http_endpoint_ok_count": endpoint_result["ok_count"],
        "http_endpoint_checked": endpoint_result["checked"],
        "http_endpoint_success_rate": endpoint_result["success_rate"],
        "http_endpoint_note": endpoint_result.get("note", ""),
        "latency_ms": getattr(row, "latency_ms", None),
        "quality_score": getattr(row, "quality_score", None),
        "error": getattr(row, "error", None),
        "socks_port": getattr(row, "socks_port", None),
        "retried": bool(getattr(row, "retried", False)),
    }


def _run_http_endpoint_checks(socks_port: Any) -> dict[str, Any]:
    if os.environ.get("HUNTER_HTTP_ENDPOINT_CHECK", "1").lower() in {"0", "false", "no"}:
        return _empty_endpoint_result("disabled")
    curl = shutil.which("curl")
    if not curl:
        return _empty_endpoint_result("curl unavailable")
    try:
        port = int(socks_port)
    except (TypeError, ValueError):
        return _empty_endpoint_result("socks port unavailable")
    if port <= 0:
        return _empty_endpoint_result("socks port unavailable")

    timeout = float(os.environ.get("HUNTER_HTTP_ENDPOINT_TIMEOUT", "3.0"))
    with ThreadPoolExecutor(max_workers=len(HTTP_ENDPOINTS)) as pool:
        results = list(
            pool.map(
                lambda endpoint: _check_http_endpoint(
                    curl,
                    port,
                    endpoint[0],
                    endpoint[1],
                    timeout,
                ),
                HTTP_ENDPOINTS,
            )
        )
    if results and all(_socks_port_closed(item) for item in results):
        return _empty_endpoint_result("socks port closed before endpoint checks")
    checked = len(results)
    ok_count = sum(1 for item in results if item["ok"])
    return {
        "results": results,
        "ok_count": ok_count,
        "checked": checked,
        "success_rate": round(ok_count / checked, 4) if checked else 0.0,
    }


def _empty_endpoint_result(note: str) -> dict[str, Any]:
    return {
        "results": [],
        "ok_count": 0,
        "checked": 0,
        "success_rate": 0.0,
        "note": note,
    }


def _check_http_endpoint(
    curl: str,
    socks_port: int,
    name: str,
    url: str,
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [
                curl,
                "--silent",
                "--show-error",
                "--location",
                "--max-time",
                str(timeout),
                "--socks5-hostname",
                f"127.0.0.1:{socks_port}",
                "--output",
                os.devnull,
                "--write-out",
                "%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 2.0,
        )
    except Exception as exc:
        return {
            "name": name,
            "url": url,
            "ok": False,
            "status_code": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": str(exc)[:160],
        }
    status_text = (proc.stdout or "").strip()
    try:
        status_code = int(status_text[-3:])
    except ValueError:
        status_code = None
    return {
        "name": name,
        "url": url,
        "ok": proc.returncode == 0 and status_code is not None and 200 <= status_code < 400,
        "status_code": status_code,
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
        "error": (proc.stderr or "").strip()[:160],
    }


def _socks_port_closed(result: dict[str, Any]) -> bool:
    error = str(result.get("error") or "").lower()
    return (
        "failed to connect to 127.0.0.1" in error
        or "couldn't connect to server" in error
    )
