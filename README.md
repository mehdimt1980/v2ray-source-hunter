# V2Ray Source Hunter

A standalone source-intelligence engine for discovering, validating, scoring and exporting public proxy subscription sources.

This repository is designed to be separate from the Android app. The Android app should consume a clean trusted registry; this engine is responsible for finding and validating sources.

## Goals

- Discover public sources from multiple channels
- Validate sources before they become trusted
- Produce machine-readable registries
- Keep the Android app small and registry-driven
- Avoid relying only on GitHub Code Search

## Discovery inputs

Initial supported inputs:

- Seed raw URLs
- Seed GitHub repositories and common file paths
- Public web pages
- Public Telegram channel web pages via `https://t.me/s/<channel>`

The engine only targets public sources. It does not bypass login, private groups, private channels, paywalls or access controls.

## Pipeline

```text
collect candidates
→ fetch
→ extract configs
→ deduplicate
→ protocol analysis
→ TCP sample validation
→ score
→ classify
→ export registries
```

## Outputs

```text
registry/trusted_sources.json
registry/candidates.json
registry/rejected.json
registry/hunt_report.json
registry/v2ray_finder_sources.json
```

`v2ray_finder_sources.json` is compatible with the Android app registry format.

## CLI

```bash
pip install -e .
source-hunter hunt --max-candidates 80 --tcp-sample-size 30
```

## GitHub Actions

The workflow runs every 6 hours by default and commits updated registry files when changes are found.
