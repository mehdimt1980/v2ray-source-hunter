# V2Ray Source Hunter

`v2ray-source-hunter` is the source-of-truth engine for discovering, validating, scoring, exporting and publishing public V2Ray/Xray sources and validated configs.

It is intentionally separate from `v2ray-finder`:

```text
v2ray-source-hunter
-> discovers public source candidates
-> validates and scores source feeds
-> runs optional Xray real validation
-> exports trusted source registries
-> exports exact validated configs
-> publishes Telegram reports and best config files
-> syncs registry/sources.json into v2ray-finder

v2ray-finder
-> consumes registry/sources.json
-> fetches configs from trusted sources
-> deduplicates configs
-> health-checks and ranks runtime configs
```

This separation prevents two different discovery engines from mutating the same app registry.

## Goals

- Discover public V2Ray/Xray sources from GitHub, public web pages and public Telegram web views.
- Validate sources before they become trusted.
- Export app-compatible source registries for `v2ray-finder`.
- Export exact Xray-passed configs as `registry/validated_configs.json`.
- Publish small, protocol-specific "best config" files to Telegram.
- Keep private, login-only, approval-only and paid sources out of the pipeline.
- Keep the Android app registry-driven and free of global discovery logic.

## Public-Only Policy

The hunter targets only public sources.

Accepted:

```text
public GitHub repositories
public raw subscription files
public web pages
public Telegram web views visible at https://t.me/s/<channel>
```

Rejected:

```text
private repositories
private Telegram channels
admin-approval Telegram channels
request-to-join channels
login-only content
paid/paywalled sources
any access-controlled source
```

The hunter does not log in, join channels, bypass access controls or scrape private content.

## Pipeline

```text
auto-discover repositories and public Telegram channels
-> collect curated and discovered candidates
-> prioritize candidate queue
-> preflight until enough live candidates are found
-> fetch source feed
-> extract configs
-> deduplicate by normalized config identity
-> protocol analysis
-> stratified TCP sample validation
-> optional Xray real validation
-> optional multi-endpoint HTTP probing
-> source scoring and classification
-> cross-source redundancy analysis
-> materialize Telegram-derived feeds
-> update source and config history
-> export registries and validated configs
-> optionally sync app registry to v2ray-finder
-> optionally publish Telegram report and best config files
```

## Discovery Inputs

Curated inputs:

```text
registry/seeds.json
registry/repositories.json
registry/web_pages.json
registry/telegram_channels.json
```

Automatic discovery outputs:

```text
registry/discovered_repositories.json
registry/discovered_telegram_channels.json
registry/discovery_report.json
```

Discovery includes:

- GitHub repository search for likely V2Ray/Xray subscription repositories.
- Multilingual search, including Chinese-language query combinations.
- Repository tree inspection through the GitHub tree API.
- Public Telegram channel discovery from public GitHub README links.
- Public Telegram web-view validation before a channel is accepted.
- Link discovery from public Telegram pages and one shallow crawl over public linked pages.

## Validation Signals

The hunter uses layered validation. The most important signal is Xray real validation.

Main signals:

```text
xray_ok              Xray accepted and validated the config path
reachable            the config looked reachable during real validation
google_204_ok        proxy reached Google's lightweight 204 endpoint
latency_ms           measured validation latency
quality_score        quality score from the real validation backend
stability_score      repeated success across hunter runs
```

Extra HTTP endpoint probing can also run through the local SOCKS port when available:

```text
https://www.gstatic.com/generate_204
https://www.cloudflare.com/cdn-cgi/trace
https://cp.cloudflare.com/generate_204
https://www.apple.com/library/test/success.html
```

These fields are best-effort:

```text
http_endpoint_results
http_endpoint_ok_count
http_endpoint_checked
http_endpoint_success_rate
http_endpoint_note
```

If the validation backend closes the local SOCKS listener before the endpoint probe runs, the hunter records that as not checked instead of treating it as a real config failure.

## Stability Tracking

The hunter tracks exact normalized config identities across runs in:

```text
registry/config_history.json
```

Each validated config can receive a `stability` block:

```json
{
  "times_validated": 2,
  "success_streak": 2,
  "first_validated_at": "2026-07-15T18:37:13+00:00",
  "last_validated_at": "2026-07-16T07:01:41+00:00",
  "stability_score": 70
}
```

This lets the hunter prefer configs that keep working across daily runs instead of only ranking by one moment of validation.

## Best Config Exports

The full exact validated output is:

```text
registry/validated_configs.json
```

This file contains every deduplicated Xray-passed config plus metadata such as source, protocol, latency, quality, stability and validation location.

The hunter publishes permanent, smaller feeds under `registry/best/` instead of asking consumers to use every validated config:

```text
registry/best/index.json
registry/best/fresh.json
registry/best/stable.json
registry/best/elite.json
registry/best/fresh_vless.txt
registry/best/stable_vless.txt
registry/best/elite_vless.txt
```

Every tier requires `xray_ok`, `reachable`, and `google_204_ok`. The tiers are:

- `fresh`: strong in the current run: quality at least 90 and latency no higher than 500 ms.
- `stable`: repeatedly passed: stability at least 70, quality at least 70, and latency no higher than 1000 ms.
- `elite`: strong and fully proven: stability 100, quality at least 90, and latency no higher than 500 ms.

`index.json` gives consumers the generated time, rule, count, and protocol files for every tier. The `.json` files contain metadata-rich rows; the protocol `.txt` files contain raw config links only, one per line.

Telegram sends the combined `fresh` plus `stable` set. This replaces the earlier temporary-only best-config rule:

```text
xray_ok = true
reachable = true
google_204_ok = true
quality_score >= 70
latency_ms <= 1000
AND (
  stability_score >= 70
  OR
  quality_score >= 90 and latency_ms <= 500
)
```

Generated Telegram attachments are protocol-specific:

```text
best_configs_ss.txt
best_configs_trojan.txt
best_configs_vless.txt
best_configs_vmess.txt
validated_configs.json
```

The `.txt` files contain raw config links only, one per line, so users can copy or import them easily. The full JSON remains attached for audit/debug.

## Quality Controls

A feed must pass multiple checks before it becomes trusted:

- Dead URLs are filtered into `registry/dead_paths.json`.
- TCP sampling is stratified by protocol.
- Weak TCP feeds become `experimental`, not trusted.
- Trusted feeds need enough unique configs, TCP success rate and score.
- Optional real validation runs when `HUNTER_REAL_CHECK=1` and `XRAY_BINARY` are configured.
- Real validation can promote or demote feeds.
- Cross-source overlap can demote highly redundant feeds to `redundant`.
- App-compatible output includes only trusted feeds.
- CI runs `python -m source_hunter.quality_gate` before syncing to the Android app.

## Telegram Materialization

Telegram web pages are useful for discovery, but the Android app should not parse Telegram HTML directly.

For trusted Telegram-derived feeds, the hunter extracts configs from Telegram HTML and writes clean generated subscription files:

```text
registry/generated/telegram/<stable-id>.txt
registry/generated_telegram_feeds.json
```

Example:

```text
Telegram public HTML page
-> extract configs
-> registry/generated/telegram/<stable-id>.txt
-> raw GitHub URL
-> v2ray-finder registry/sources.json
```

The original Telegram page is kept as upstream metadata where supported.

## Outputs

Primary outputs:

```text
registry/trusted_sources.json
registry/candidates.json
registry/experimental.json
registry/redundant.json
registry/rejected.json
registry/dead_paths.json
registry/hunt_report.json
registry/candidate_queue.json
registry/v2ray_finder_sources.json
registry/validated_configs.json
registry/config_history.json
registry/source_history.json
registry/best/index.json
registry/best/fresh.json
registry/best/stable.json
registry/best/elite.json
```

Discovery outputs:

```text
registry/discovered_repositories.json
registry/discovered_telegram_channels.json
registry/discovery_report.json
```

Generated feed outputs:

```text
registry/generated_telegram_feeds.json
registry/generated/telegram/*.txt
```

`registry/v2ray_finder_sources.json` is compatible with the `v2ray-finder` app registry format and is the file synced into the app repository.

## CLI

```bash
pip install -e .
source-hunter run --max-candidates 120 --preflight-scan-limit 700 --tcp-sample-size 30 --json
```

Quality gate:

```bash
python -m source_hunter.quality_gate
```

Telegram report preview:

```bash
python -m source_hunter.telegram_report
```

Telegram send:

```bash
python -m source_hunter.telegram_report --send --send-validated-configs
```

## Environment Variables

Core:

```text
GITHUB_TOKEN                    GitHub token used for discovery and repository API calls
HUNTER_AUTO_DISCOVER            set to 0 to disable auto-discovery for a run
HUNTER_REAL_CHECK               set to 1 to enable optional Xray real validation
XRAY_BINARY                     path to the Xray binary for real validation
HUNTER_REAL_CHECK_LOCATION      label for where validation ran, e.g. github_actions_eu
```

Extra endpoint probing:

```text
HUNTER_HTTP_ENDPOINT_CHECK          set to 0 to disable extra endpoint probing
HUNTER_HTTP_ENDPOINT_MAX_PER_SOURCE default 3
HUNTER_HTTP_ENDPOINT_TIMEOUT        default 3.0 seconds
```

Telegram notifications:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

`TELEGRAM_CHAT_ID` should be the channel username, for example:

```text
@freev2rayhunter
```

The bot must be an admin in the channel with permission to post messages.

## Web and Telegram Seeds

`registry/web_pages.json` accepts records like:

```json
[
  {"label": "Example public page", "url": "https://example.com/page", "tags": ["web"]}
]
```

`registry/telegram_channels.json` accepts public channel names only:

```json
[
  {"channel": "example_public_channel", "label": "Example channel", "tags": ["telegram"], "discover_links": true}
]
```

Before adding a Telegram channel, verify that this URL shows public posts without login, membership or approval:

```text
https://t.me/s/<channel>
```

If the page shows request-to-join, admin approval or private-channel messaging, do not add it.

## Sync To v2ray-finder

The workflow can publish `registry/v2ray_finder_sources.json` to `v2ray-finder/registry/sources.json` when these secrets/variables are configured:

```text
TARGET_REPO_TOKEN  GitHub token with write access to the target repository
TARGET_REPO        example: mehdimt1980/v2ray-finder
TARGET_PATH        example: registry/sources.json
```

This sync makes `v2ray-source-hunter` the single writer of trusted source registry updates, while `v2ray-finder` remains the consumer.

## GitHub Actions

The CI workflow can be run manually and also runs on schedule. It:

```text
checks out the hunter repo
installs the package
installs Xray
runs source-hunter
runs quality gates
commits updated registry outputs
syncs the app-compatible registry to v2ray-finder
uploads registry artifacts
sends Telegram summary and best config files
```

The workflow commits the full `registry` directory so generated Telegram subscription files, history files and validated config outputs are preserved.

There is also a fast manual workflow:

```text
Telegram Test
```

It only installs the package and sends the Telegram report/attachments, so Telegram secrets and channel permissions can be tested without running the full hunter.
