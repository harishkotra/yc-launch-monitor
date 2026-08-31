# 🚀 YC Launch Monitor — Slack Bot

A personal Slack bot that keeps you ahead of **every new Y Combinator and a16z
Speedrun company launch** — so you can reach founders early for pipeline and
outreach, before everyone else.

It continuously monitors four sources and posts **real-time alerts to Slack**
whenever a new company is detected. Crucially, it **flags founders who announce
their YC acceptance on X / LinkedIn before YC has officially listed them** — the
highest-value outreach signal.

---

## What it does

| Source | Type | Signal |
|---|---|---|
| **YC Directory** (`ycombinator.com/companies`) | Official | Newly added companies & new batch listings → ✅ **Confirmed** |
| **a16z Speedrun** (`speedrun.a16z.com`) | Official | Newly added Speedrun companies → ✅ **Confirmed** |
| **X (Twitter)** | Social | Founder posts mentioning YC/Speedrun → ⚡ **Early** (if not yet officially listed) |
| **LinkedIn** | Social | Founder posts referencing YC/Speedrun → ⚡ **Early** (if not yet officially listed) |

> **Note on "Speedrun":** Speedrun is the **a16z accelerator** (speedrun.a16z.com),
> a distinct program from Y Combinator. This bot monitors it separately and tags
> alerts with its own source + cohort, exactly as requested.

### Two alert types
- **⚡ EARLY SIGNAL** — a founder announced their acceptance on social media, but
  the company is **not yet in the official YC/Speedrun directory**. This is the
  "get ahead of everyone" signal.
- **✅ CONFIRMED** — the company is now officially listed in the YC directory or
  Speedrun program.

Each alert includes: **company, founder, batch/cohort, source, status, a
description, and links** (original post + website + YC/Speedrun profile).

---

## Architecture

```
yc-launch-monitor/
├── yc_monitor/
│   ├── main.py            # orchestrator + scheduler (--once / --loop) + CLI
│   ├── config.py          # config.yaml + env-var loading
│   ├── models.py          # Alert model (status: early | confirmed)
│   ├── state.py           # SQLite state + duplicate detection
│   ├── index.py           # known-company index (for matching social posts)
│   ├── detector.py        # ⚡ early-vs-confirmed classifier
│   ├── alerts.py          # Slack delivery (bot token OR webhook)
│   ├── health.py          # Pond verification report + /health server
│   ├── demo.py            # generates demo alerts + payloads
│   ├── preview.py         # renders Slack-message HTML preview
│   └── sources/
│       ├── yc_directory.py  # YC directory (free, no key)
│       ├── speedrun.py      # a16z Speedrun (free, no key)
│       ├── x_twitter.py     # X API v2 (needs bearer token)
│       └── linkedin.py      # pluggable adapter (no free API)
├── slack/manifest.yaml    # installable Slack app (one workspace)
├── pond/manifest.yaml     # Pond agent manifest
├── deploy/com.yclaunchmonitor.plist  # persistent macOS runner (every 8h)
├── config.example.yaml
├── run.sh
└── tests/
```

**State & dedup:** everything is stored in a local SQLite database (`state.db`).
Each event has a stable dedup key, so you **never get duplicate alerts**, even
across restarts. Snapshots of each source let the bot only push **incremental**
updates.

**Early-detection logic:** social posts are matched against the official company
index. If a post references a company that is **already officially listed**, it's
**Confirmed**. If not (or the company can't be matched), it's flagged **⚡ Early**
— the founder announced before the official listing.

---

## 1. Setup (5 minutes)

### Prerequisites
- Python 3.9+ (macOS ships with it)
- A Slack workspace where you can install apps

### Install
```bash
git clone <your-repo-url> yc-launch-monitor
cd yc-launch-monitor
./run.sh --once --dry-run      # first run creates .venv, installs deps, tests sources
```

This runs a single pass in **dry-run mode** (prints alerts to the console, sends
nothing to Slack) — a great way to confirm it works before wiring up Slack.

---

## 2. Create the Slack app (one-time)

The bot is a **personal Slack app** installed into your single workspace:

1. Open **https://api.slack.com/apps** → **Create New App** → **From an app manifest**.
2. Pick your workspace, then paste the contents of **`slack/manifest.yaml`**.
3. Click **Create**, then **Install to Workspace** → **Allow**.
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`) from
   **OAuth & Permissions**.

Now put it in the config:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:
```yaml
slack:
  bot_token: "xoxb-..."              # your bot token
  channel: "#yc-launch-monitor"      # channel name/ID, OR your user ID for a DM
```

> **Tip:** To receive alerts in a DM, create a channel (e.g. `#yc-launch-monitor`),
> add the bot to it, and set `channel` to that channel. Or set `channel` to your
> **Slack user ID** (right-click your avatar → Copy member ID) to DM the bot's
> messages directly.

Test delivery:
```bash
./run.sh --once            # sends any pending alerts to Slack
```

---

## 3. Enable the early-signal social sources

The YC Directory + Speedrun sources work **out of the box with no keys**. The
**early-detection** sources need credentials:

### X (Twitter) — the key early signal
1. Create an app at **https://developer.x.com** (Basic tier, ~$100/mo).
2. Generate a **Bearer token**.
3. Add it to `config.yaml`:
   ```yaml
   sources:
     x_twitter: true
   x_twitter:
     bearer_token: "your-bearer-token"
   ```
   (Or set the env var `YC_X_BEARER_TOKEN`.)
4. The default keyword query already covers phrasings like
   *"got into YC"*, *"accepted into Y Combinator"*, *"YC S26"*, *"a16z Speedrun
   cohort"*, etc. Edit `x_twitter.query` to tune it.

### LinkedIn
LinkedIn has no free public API, so this uses a **pluggable adapter**. Point
`linkedin.endpoint` at any service that accepts `POST {"query":..., "freshness_minutes":N}`
and returns `{"results":[{"author","text","url","published_at"}]}`. See
`config.example.yaml`.

---

## 4. Run it persistently

### Option A — macOS (launchd, recommended)
```bash
cp deploy/com.yclaunchmonitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.yclaunchmonitor.plist
launchctl start com.yclaunchmonitor
```
Runs every **8 hours**, survives reboots, logs to `/tmp/yclaunchmonitor.log`.

### Option B — any machine (cron)
```cron
0 */8 * * * cd /Users/shk/yc-launch-monitor && ./run.sh --once >> /tmp/yclm.log 2>&1
```

### Option C — always-on process
```bash
./run.sh --loop      # polls every interval_minutes (default 480 = 8h)
```

---

## 5. Pond integration (for review & verification)

Register your agent at **https://joinpond.ai/agent/create** using
**`pond/manifest.yaml`**. Each run writes a machine-readable **`pond_report.json`**
(see `yc_monitor/health.py`) with `sources_enabled`, `state`, and
`alerts_this_run` — so reviewers can verify the work.

To expose a live health endpoint for ongoing monitoring:
```yaml
pond:
  agent_id: "your-agent-id"
  health_port: 8080
```
Then `curl http://localhost:8080/health` returns `{"status":"ok", ...}`.

---

## 6. Test & verify

```bash
./run.sh --once --dry-run          # console preview of any new alerts
./run.sh --once --dry-run --reset  # clear state and re-baseline
.venv/bin/python -m unittest discover -s tests   # run the test suite
```

Generate the demo alerts + Slack preview:
```bash
.venv/bin/python -m yc_monitor.demo
.venv/bin/python -m yc_monitor.preview   # -> demo/slack_preview.html / .png
```

---

## 7. Future upgradability

The source layer is **pluggable**: add a new platform by dropping a module into
`yc_monitor/sources/` that returns `Post` objects, then wiring it in `main.py`.
To add Reddit, Bluesky, Hacker News, etc., copy `x_twitter.py` as a template —
the classifier, dedup, and Slack delivery all work unchanged.

---

## Configuration reference (environment variables)

| Env var | Purpose |
|---|---|
| `YC_SLACK_BOT_TOKEN` | Slack bot token (overrides config) |
| `YC_SLACK_WEBHOOK` | Slack webhook URL (fallback) |
| `YC_SLACK_CHANNEL` | Channel name/ID or user ID |
| `YC_X_BEARER_TOKEN` | X API v2 bearer token |
| `YC_LINKEDIN_API_KEY` | LinkedIn adapter API key |
| `YC_POND_AGENT_ID` | Pond agent id |

All secrets can live in `config.yaml` or the environment — never commit them.

---

## License
MIT — free to use, modify, and extend.
