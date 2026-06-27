from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import run_hunt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="source-hunter")
    parser.add_argument("command", nargs="?", default="run")
    parser.add_argument("--registry-dir", default="registry")
    parser.add_argument("--max-candidates", type=int, default=80)
    parser.add_argument("--preflight-scan-limit", type=int, default=None)
    parser.add_argument("--tcp-sample-size", type=int, default=30)
    parser.add_argument("--fetch-timeout", type=float, default=20.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = run_hunt(
        registry_dir=Path(args.registry_dir),
        max_candidates=args.max_candidates,
        preflight_scan_limit=args.preflight_scan_limit,
        tcp_sample_size=args.tcp_sample_size,
        fetch_timeout=args.fetch_timeout,
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"complete: trusted={len(result.trusted)} candidates={len(result.candidates)} rejected={len(result.rejected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
