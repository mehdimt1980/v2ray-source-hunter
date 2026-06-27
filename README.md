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

Supported inputs:

- Seed raw URLs from `registry/seeds.json`
- Seed repositories and file paths from `registry/repositories.json`
- Repository tree discovery through the GitHub tree API, not Code Search
- Public web pages from `registry/web_pages.json`
- Public Telegram channel web pages from `registry/telegram_channels.json`

The engine only targets public sources. It does not bypass login, private groups, private channels, paywalls or access controls.

## Pipeline

```text
collect candidates
→ preflight URL check
→ fetch
→ extract configs
→ deduplicate
→ protocol analysis
→ stratified TCP sample validation
→ optional real validation
→ score
→ classify
→ cross-source redundancy analysis
→ export registries
```

## Quality controls

The hunter now applies these controls before a feed can become trusted:

- Dead URLs are filtered into `registry/dead_paths.json` before evaluation.
- TCP sampling is stratified by protocol instead of taking only the first N configs.
- Very weak TCP feeds become `experimental`, not normal candidates.
- Trusted feeds need at least 30 unique configs, TCP success rate >= 0.25 and score >= 60.
- Optional real validation can run when `HUNTER_REAL_CHECK=1` and `XRAY_BINARY` are configured.
- Cross-source overlap demotes highly redundant feeds to `redundant`.
- App-compatible output includes only `trusted` feeds.

## Outputs

```text
registry/trusted_sources.json
registry/candidates.json
registry/experimental.json
registry/redundant.json
registry/rejected.json
registry/dead_paths.json
registry/hunt_report.json
registry/v2ray_finder_sources.json
```

`v2ray_finder_sources.json` is compatible with the Android app registry format.

## CLI

```bash
pip install -e .
source-hunter run --max-candidates 80 --tcp-sample-size 30 --json
```

## Web and Telegram seeds

`registry/web_pages.json` accepts records like:

```json
[
  {"label": "Example public page", "url": "https://example.com/page", "tags": ["web"]}
]
```

`registry/telegram_channels.json` accepts public channel names:

```json
[
  {"channel": "example_public_channel", "label": "Example channel", "tags": ["telegram"]}
]
```

The Telegram collector reads the public web view at `https://t.me/s/<channel>` only. It also performs one shallow crawl over links found in the public channel page so subscription files linked from Telegram posts, GitHub README pages, or raw text feeds can enter the normal scoring pipeline as `telegram_discovered_link` candidates. It does not log in, join channels, fetch private content, or bypass Telegram access controls.

## Optional sync to Android registry repo

The workflow can publish `registry/v2ray_finder_sources.json` to another repository when these secrets are configured:

```text
TARGET_REPO_TOKEN  GitHub token with write access to the target repository
TARGET_REPO        example: mehdimt1980/v2ray-finder
TARGET_PATH        example: registry/hunter_sources.json
```

If the secrets are missing, sync is skipped safely.

## GitHub Actions

The workflow runs every 6 hours by default, commits updated output files to this repository, uploads artifacts, and optionally syncs the Android-compatible registry to a target repo.
