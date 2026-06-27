from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from .protocols import endpoint_from_config


def _check_one(config: str, timeout: float) -> bool:
    endpoint = endpoint_from_config(config)
    if not endpoint:
        return False
    host, port = endpoint
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def tcp_sample(configs: list[str], *, sample_size: int = 30, timeout: float = 4.0, workers: int = 12) -> tuple[int, int]:
    sample = configs[: max(0, sample_size)]
    if not sample:
        return 0, 0
    ok = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_check_one, cfg, timeout) for cfg in sample]
        for fut in as_completed(futures):
            if fut.result():
                ok += 1
    return ok, len(sample)
