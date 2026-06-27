from __future__ import annotations

import random

from .protocols import protocol_of


def adaptive_sample_size(total: int, requested: int) -> int:
    if total <= 0:
        return 0
    if total < 300:
        return min(total, max(30, requested))
    if total < 2000:
        return min(total, max(60, requested))
    return min(total, max(100, requested))


def stratified_sample(items: list[str], *, requested: int, seed: str = "source-hunter") -> list[str]:
    target = adaptive_sample_size(len(items), requested)
    if target <= 0:
        return []
    groups: dict[str, list[str]] = {}
    for item in items:
        groups.setdefault(protocol_of(item), []).append(item)
    rng = random.Random(seed)
    for values in groups.values():
        rng.shuffle(values)
    out: list[str] = []
    names = sorted(groups.keys())
    while len(out) < target and names:
        next_names = []
        for name in names:
            values = groups.get(name) or []
            if values and len(out) < target:
                out.append(values.pop())
            if values:
                next_names.append(name)
        names = next_names
    return out
