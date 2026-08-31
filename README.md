# YC Launch Monitor — Slack Bot

A personal Slack bot that keeps you ahead of **every new Y Combinator and a16z Speedrun company launch** — so you can reach founders early for pipeline and outreach, before everyone else.

It continuously monitors four sources and posts **real-time alerts to Slack**
whenever a new company is detected. Crucially, it **flags founders who announce
their YC acceptance on X / LinkedIn before YC has officially listed them** — the
highest-value outreach signal.

---

## Quick start on a new machine

```bash
# 1. Clone the repo
git clone https://github.com/harishkotra/yc-launch-monitor.git
cd yc-launch-monitor

# 2. Create your config from the .env template
cp .env.example .env
#    then edit .env and fill in your secrets (Slack bot token, channel, X token...)

# 3. Install & do a test run (dry-run prints alerts, sends nothing)
./run.sh --once --dry-run

# 4. Send real alerts to Slack
./run.sh --once

# 5. Run persistently (every 8h) — pick one:
./run.sh --loop                      # foreground process
# or install the macOS launchd agent:
cp deploy/com.yclaunchmonitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.yclaunchmonitor.plist
```

Configuration lives in **`.env`** (recommended) or **`config.yaml`** — see
[Configuration reference](#configuration-reference-environment-variables) below.
Secrets are never committed (both `.env` and `config.yaml` are gitignored).

---

## What it does

| Source | Type | Signal |
|---|---|---|
| **YC Directory** (`ycombinator.com/companies`) | Official | Newly added companies & new batch listings → ✅ **Confirmed** |
| **a16z Speedrun** (`speedrun.a16z.com`) | Official | Newly added Speedrun companies → ✅ **Confirmed** |
| **X (Twitter)** | Social | Founder posts mentioning YC/Speedrun → ⚡ **Early** (if not yet officially listed) |
| **LinkedIn** | Social | Founder posts referencing YC/Speedrun → ⚡ **Early** (if not yet officially listed) |

> **Note on "Speedrun":** Speedrun is the **a16z accelerator** (speedrun.a16z.com), a distinct program from Y Combinator. This bot monitors it separately and tags alerts with its own source + cohort, exactly as requested.

### Two alert types
- **⚡ EARLY SIGNAL** — a founder announced their acceptance on social media, but the company is **not yet in the official YC/Speedrun directory**. This is the "get ahead of everyone" signal.
- **✅ CONFIRMED** — the company is now officially listed in the YC directory or Speedrun program.

Each alert includes: **company, founder, batch/cohort, source, status, a description, and links** (original post + website + YC/Speedrun profile).

---

## Technologies

| Layer | Tech | Why |
|---|---|---|
| Language | **Python 3.9+** | Batteries included, easy for non-experts to run & extend |
| HTTP | **`requests`** | Simple, synchronous source polling |
| Config | **PyYAML + python-dotenv** | `config.yaml` for humans, `.env` for secrets (never committed) |
| State & dedup | **SQLite** (stdlib `sqlite3`) | Zero-setup persistent storage, no external DB server |
| Scheduler | **`--loop` (threaded sleep)** + **launchd plist** + **cron** | Persistent monitoring on macOS or any machine |
| Slack | **Block Kit** via `chat.postMessage` (OAuth bot token) or Incoming Webhook | Rich, actionable alert cards |
| Data sources | **yc-oss GitHub Pages API** (YC), **Speedrun REST API** (a16z) | Free, no API keys required |
| Social detection | **X API v2** + **pluggable LinkedIn adapter** | Founder-announcement early signal |
| Testing | **`unittest`** (stdlib) | No extra test framework to install |
| Ops | **Pond** (`pond_report.json` + `/health`) | Machine-readable verification for reviewers |

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

### Data flow

```
                 ┌─────────────────────────────────────────────────────────┐
                 │                       main.py  (orchestrator)           │
                 │   --once / --loop  →  run_once() → deliver()            │
                 └───────┬──────────────────────────────┬──────────────────┘
                         │                              │
         OFFICIAL sources│                              │SOCIAL sources (optional)
                         ▼                              ▼
   ┌──────────────────────────┐          ┌───────────────────────────────────┐
   │ yc_directory.py          │          │ x_twitter.py / linkedin.py        │
   │  yc-oss GitHub Pages API │          │  X API v2 / pluggable endpoint    │
   │  → changes feed + diff   │          │  → raw Post objects               │
   └───────────┬──────────────┘          └───────────────┬───────────────────┘
               │  ✅ CONFIRMED                           │
               │                                         ▼
   ┌───────────▼──────────────┐          ┌───────────────────────────────────┐
   │ speedrun.py              │          │ detector.classify_post(post, idx) │
   │  speedrun-api.a16z.com   │          │  match vs CompanyIndex            │
   │  → slug-list diff        │          │  → ⚡ EARLY  or  ✅ CONFIRMED      │
   └───────────┬──────────────┘          └───────────────┬───────────────────┘
               │  ✅ CONFIRMED                           │
               └───────────────┬─────────────────────────┘
                               ▼
                  ┌────────────────────────────┐
                  │ state.py  (SQLite state.db)│   dedup via seen_events
                  │  mark_seen / is_seen       │   incremental via snapshots
                  └────────────┬───────────────┘
                               ▼
                  ┌────────────────────────────┐
                  │ alerts.py  (SlackClient)   │   Block Kit payload
                  │  chat.postMessage / webhook│
                  └────────────┬───────────────┘
                               ▼
                        ┌─────────────┐
                        │  Slack DM / │   ⚡/✅ company · founder · batch ·
                        │  channel    │   source · details · links
                        └─────────────┘
```

---

## How it works — key code

### 1. The alert model (`models.py`)
Every detection becomes an `Alert` — either **⚡ early** or **✅ confirmed** — and
knows how to render itself as a Slack Block Kit payload:

```python
@dataclass
class Alert:
    company: str
    source: str            # "YC Directory" | "Speedrun" | "X (Twitter)" | "LinkedIn"
    status: str = STATUS_EARLY   # early | confirmed
    founder: str = ""
    details: str = ""
    link: str = ""
    dedup_key: str = ""
    detected_at: str = field(default_factory=utcnow_iso)
    extra: dict = field(default_factory=dict)

    @property
    def status_emoji(self) -> str:
        return STATUS_EMOJI.get(self.status, "🔔")

    def to_slack_payload(self, cfg: dict) -> dict:
        # ... builds header / status / batch / details / buttons blocks ...
```

### 2. State + dedup (`state.py`)
SQLite-backed, so you never get a duplicate alert — even across restarts. Two
tables: `seen_events` (dedup) and `snapshots` (incremental source diffing):

```python
def mark_seen(self, dedup_key, source, company):
    now = datetime.now(timezone.utc).isoformat()
    self.conn.execute(
        "INSERT OR IGNORE INTO seen_events (dedup_key, source, company, alerted_at) "
        "VALUES (?,?,?,?)", (dedup_key, source, company, now))
    self.conn.commit()

def snapshot_unchanged(self, source, payload) -> bool:
    h = hashlib.sha256(str(payload).encode("utf-8")).hexdigest()
    row = self.conn.execute("SELECT payload_hash FROM snapshots WHERE source = ?",
                            (source,)).fetchone()
    return bool(row and row["payload_hash"] == h)
```

### 3. Early-detection classifier (`detector.py`)
The heart of the "beat everyone to the founder" feature. A raw social post is
matched against the official company index. Strong matches only — to avoid false
positives like a bio mentioning "Amazon":

```python
def classify_post(post: Post, idx) -> Alert:
    matched = _match_company(post, idx)          # handle match → name near keyword
    if matched:
        status = STATUS_CONFIRMED                 # already officially listed
    else:
        company = _extract_company_hint(post.text) or "Unknown company"
        status = STATUS_EARLY                     # announced before official listing
    return Alert(company=company, founder=post.author, source=post.source,
                 status=status, details=post.text, link=post.url,
                 dedup_key=make_dedup_key(post.source.lower(), post.post_id or post.url),
                 extra={...})
```

### 4. A collector (`sources/yc_directory.py`)
Official sources are "pluggable" too — a collector just returns new `Alert`s and
the state layer handles dedup:

```python
def collect_new(state) -> List[Alert]:
    alerts = []
    changes = fetch_changes()                     # yc-oss changes/latest.json
    for c in changes.get("added") or []:
        alert = _company_to_alert(c)              # ✅ CONFIRMED
        if not state.is_seen(alert.dedup_key):
            alerts.append(alert)
            state.mark_seen(alert.dedup_key, alert.source, alert.company)
    return alerts
```

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
| `YC_SLACK_MENTION` | Slack user/group to @mention on alerts |
| `YC_X_BEARER_TOKEN` | X API v2 bearer token |
| `YC_LINKEDIN_API_KEY` | LinkedIn adapter API key |
| `YC_LINKEDIN_ENDPOINT` | LinkedIn adapter endpoint |
| `YC_POND_AGENT_ID` | Pond agent id |
| `YC_SCHEDULE_INTERVAL_MINUTES` | Poll interval in minutes (default 480) |

Secrets can live in `.env`, `config.yaml`, or the environment — never commit them.

---

## Contributing & forking

This project is designed to be **forked, extended, and reused** — for your own
outreach pipeline, a different accelerator, or a totally different alert use-case.

### Fork it
1. Click **Fork** on GitHub (or `git clone https://github.com/harishkotra/yc-launch-monitor.git`).
2. `cd yc-launch-monitor && cp .env.example .env && ./run.sh --once --dry-run`.
3. Make your change, add a test in `tests/`, run `./run.sh --once --dry-run` and
   `.venv/bin/python -m unittest discover -s tests`.
4. Open a Pull Request with a clear description of what and why.

### Project conventions
- **Sources are pluggable** — add a module to `yc_monitor/sources/` that returns
  `Alert`s (official) or `Post`s (social); wire it in `main.py`.
- **State/dedup is handled for you** — a new collector just calls
  `state.is_seen` / `state.mark_seen` and it's automatically deduped.
- **Config is centralized** — add new keys to `config.py` `DEFAULTS`, the
  `.env.example` template, and the env-var override block.
- **Keep secrets out** — anything you add must not require committing a key.

### New features you could add (great first PRs)
- **More social sources** — Reddit, Bluesky, Hacker News, Telegram. Copy
  `x_twitter.py` as a template; the classifier, dedup, and Slack delivery all
  work unchanged. *(The source layer was built for exactly this.)*
- **Webhook/API mode** — expose a small HTTP endpoint (beyond Pond's `/health`)
  so other tools can query recent alerts as JSON.
- **Slack interactive buttons** — "Open website", "Add to CRM", "Snooze" via
  Block Kit `action_id` callbacks (needs a Socket Mode / Events listener).
- **CRM export** — auto-append confirmed/early companies to a Google Sheet,
  Airtable, or Notion database.
- **Scoring / prioritisation** — rank alerts by industry fit, founder
  following-count, or keyword relevance to your ICP.
- **Dedup TTL** — expire old `seen_events` rows so re-added companies can
  re-alert after N days.
- **Richer LinkedIn** — wire a real LinkedIn API / scraping adapter (the
  pluggable endpoint contract is already defined).
- **CLI report** — `--report` flag that renders today's alerts to Markdown/HTML
  for a daily digest email or newsletter.

---

## Built by

**[Harish Kotra](https://harishkotra.me)** — Senior GTM professional building
tools that find pipeline before everyone else does.

Check out my other builds: **[DailyBuild.xyz](https://dailybuild.xyz)** — a new
AI-powered build every day.

