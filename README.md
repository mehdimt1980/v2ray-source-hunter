# V2Ray Source Hunter

`v2ray-source-hunter` is the source-of-truth engine for discovering, validating, scoring and exporting public V2Ray/Xray subscription sources.

It is intentionally separate from `v2ray-finder`. The hunter owns source discovery and registry generation; the app/runtime repository consumes the trusted registry and focuses on fetching configs, deduplication, health checks, real validation and source-performance reporting.

```text
v2ray-source-hunter
→ discovers public source candidates
→ validates and scores source feeds
→ materializes generated feeds when needed
→ exports app-compatible trusted registry records
→ syncs registry/sources.json into v2ray-finder

v2ray-finder
→ consumes registry/sources.json
→ fetches configs from enabled trusted sources
→ deduplicates configs
→ health-checks and real-validates configs
→ ranks configs and reports source performance
```

This separation prevents two different discovery engines from mutating the same app registry.

## Goals

- Automatically discover public sources from GitHub, public web pages and public Telegram web views.
- Validate sources before they become trusted.
- Produce machine-readable registries for review, debugging and app consumption.
- Keep the Android app small, registry-driven and free of global discovery logic.
- Avoid relying only on GitHub Code Search.
- Keep private, login-only, approval-only and access-controlled content out of the pipeline.
- Improve multilingual discovery, including Chinese-language public repositories.

## Public-only policy

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

## Discovery inputs

The hunter has both curated inputs and automatic discovery outputs.

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

Discovery currently includes:

- GitHub repository search for likely V2Ray/Xray subscription repositories.
- Multilingual GitHub repository search, including Chinese-language query combinations.
- Repository tree inspection through the GitHub tree API.
- Public Telegram channel discovery from public GitHub README links.
- Public Telegram web-view validation before a channel is accepted.
- Link discovery from public Telegram pages and one shallow crawl over public linked pages.

Manual seed files are still supported as curated hints, but the main direction is automatic source discovery.

## Multilingual repository discovery

The repository auto-discovery stage now includes both English and Chinese query families.

Chinese-language repository discovery combines local public-source terms with protocol and client terms such as:

```text
v2ray
xray
vless
vmess
trojan
clash
mihomo
sing-box
Shadowrocket
```

It also combines Chinese discovery terms with high-signal filenames such as:

```text
clash.yaml
sub.yaml
subscribe.txt
nodes.txt
v2ray.txt
```

Repositories found through this path are tagged with metadata such as:

```json
{
  "tags": ["auto", "github", "zh", "chinese", "github_zh_search"],
  "metadata": {
    "discovery_provider": "github_repository_search",
    "language_hint": "zh",
    "region_hint": "cn",
    "discovery_query": "..."
  }
}
```

This keeps the discovery context visible during later scoring and registry review.

## Pipeline

```text
auto-discover repositories and public Telegram channels
→ collect curated and discovered candidates
→ prioritize candidate queue
→ preflight until enough live candidates are found
→ fetch source feed
→ extract configs
→ deduplicate configs
→ protocol analysis
→ stratified TCP sample validation
→ optional real validation with Xray
→ score
→ classify
→ cross-source redundancy analysis
→ materialize Telegram-derived feeds
→ export registries
→ optionally sync app-compatible registry to v2ray-finder
```

## Candidate queue

The hunter does not simply evaluate the first N raw candidates. It prioritizes candidates first, then preflights candidates in batches until the selected live-candidate target is filled.

The queue favors:

```text
telegram_discovered_link
repository_tree
curated seeds
high-signal file names such as tested, all_configs, subscription, vless, vmess, trojan, clash
```

It downranks low-signal paths such as README, license, examples and workflow files.

Diagnostic output:

```text
registry/candidate_queue.json
```

This shows raw groups, selected groups, preflight counts and the top queue entries.

## Quality controls

A feed must pass multiple checks before it becomes trusted:

- Dead URLs are filtered into `registry/dead_paths.json` before evaluation.
- TCP sampling is stratified by protocol instead of taking only the first N configs.
- Very weak TCP feeds become `experimental`, not normal candidates.
- Trusted feeds need at least 30 unique configs, TCP success rate >= 0.25 and score >= 60.
- Optional real validation can run when `HUNTER_REAL_CHECK=1` and `XRAY_BINARY` are configured.
- Cross-source overlap can demote highly redundant feeds to `redundant`.
- App-compatible output includes only trusted feeds.

## Telegram materialization

Telegram web pages are useful for discovery, but the Android app should not need to parse Telegram HTML.

For trusted Telegram-derived feeds, the hunter extracts configs from Telegram HTML and writes clean generated subscription files:

```text
registry/generated/telegram/<stable-id>.txt
registry/generated_telegram_feeds.json
```

The app registry then points to the generated raw GitHub URL instead of the original `https://t.me/s/...` page.

Example shape:

```text
Telegram public HTML page
→ extract configs
→ registry/generated/telegram/<stable-id>.txt
→ https://raw.githubusercontent.com/mehdimt1980/v2ray-source-hunter/main/registry/generated/telegram/<stable-id>.txt
→ v2ray-finder registry/sources.json
```

The original Telegram page is kept as metadata/upstream context where supported, but runtime consumption should use the clean generated subscription file.

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

Useful environment variables:

```text
GITHUB_TOKEN          GitHub token used for discovery and repository API calls
HUNTER_AUTO_DISCOVER  set to 0 to disable auto-discovery for a run
HUNTER_REAL_CHECK     set to 1 to enable optional Xray real validation
XRAY_BINARY           path to the Xray binary for real validation
```

## Web and Telegram seeds

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

## Sync to v2ray-finder

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
installs Xray for optional real validation
runs source-hunter
commits updated registry outputs
uploads registry artifacts
syncs the app-compatible registry to v2ray-finder when configured
```

The workflow commits the full `registry` directory so generated Telegram subscription files are preserved and available through raw GitHub URLs.
