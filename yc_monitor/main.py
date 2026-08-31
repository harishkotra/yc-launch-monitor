"""YC Launch Monitor — Slack bot that tracks new YC and a16z Speedrun companies.

Sources:
  * YC Directory  — yc-oss GitHub Pages mirror (free, no key)  -> CONFIRMED
  * a16z Speedrun — Speedrun public REST API (free, no key)    -> CONFIRMED
  * X (Twitter)   — founder-announcement scan (needs X API v2) -> EARLY/CONFIRMED
  * LinkedIn      — founder-announcement scan (pluggable)      -> EARLY/CONFIRMED

Early detection: founders who announce acceptance on social before the company
is officially listed are flagged ⚡ EARLY — the key outreach signal.

Delivery: Slack OAuth bot token (chat.postMessage) or webhook fallback.
State + dedup: SQLite (state.db). Persistent run: --loop or cron/launchd.
Pond: emits pond_report.json and optional /health server.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from typing import List

from .config import load_config
from .state import State
from .models import Alert
from .alerts import SlackClient, render_alerts_for_dry_run
from .detector import classify_many
from .index import build_index
from .sources import yc_directory, speedrun, x_twitter, linkedin
from . import health


def _official_alerts(cfg: dict, state: State) -> List[Alert]:
    alerts: List[Alert] = []
    if cfg["sources"].get("yc_directory", True):
        alerts += yc_directory.collect_new(state)
    if cfg["sources"].get("speedrun", True):
        alerts += speedrun.collect_new(state)
    return alerts


def _social_alerts(cfg: dict, state: State) -> List[Alert]:
    """Classify fresh social posts into EARLY/CONFIRMED alerts (with dedup)."""
    alerts: List[Alert] = []
    x_on = cfg["sources"].get("x_twitter", False)
    li_on = cfg["sources"].get("linkedin", False)
    if not (x_on or li_on):
        return alerts

    # Build the official-company index for classification.
    try:
        yc_companies = yc_directory.fetch_all_companies()
    except Exception:
        yc_companies = []
    try:
        speedrun_records = speedrun._fetch_all_pages()
    except Exception:
        speedrun_records = []
    idx = build_index(yc_companies, speedrun_records)

    posts = []
    if x_on:
        posts += x_twitter.collect_posts(cfg)
    if li_on:
        posts += linkedin.collect_posts(cfg)

    for alert in classify_many(posts, idx):
        if not state.is_seen(alert.dedup_key):
            alerts.append(alert)
            state.mark_seen(alert.dedup_key, alert.source, alert.company)
    return alerts


def run_once(cfg: dict, state: State) -> List[Alert]:
    return _official_alerts(cfg, state) + _social_alerts(cfg, state)


def deliver(alerts: List[Alert], cfg: dict, client: SlackClient) -> None:
    if not alerts:
        return
    if client.enabled:
        sent = 0
        for a in alerts:
            try:
                if client.send_alert(a, cfg):
                    sent += 1
                else:
                    print(f"[slack] send failed for {a.company}")
            except Exception as e:  # noqa: BLE001
                print(f"[slack] error sending {a.company}: {e!r}")
        print(f"[slack] sent {sent}/{len(alerts)} alerts")
    else:
        print(render_alerts_for_dry_run(alerts))


def _tick(cfg: dict, state: State, client: SlackClient) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n[{now}] monitoring pass...")
    try:
        alerts = run_once(cfg, state)
        deliver(alerts, cfg, client)
        stats = state.stats()
        print(f"[monitor] stats: {stats}")
        # Pond verification report
        report_path = cfg.get("pond", {}).get("report_path", "pond_report.json")
        health.write_report(alerts, cfg, stats, report_path)
        print(f"[pond] wrote report -> {report_path}")
    except Exception as e:  # noqa: BLE001
        print(f"[monitor] pass failed: {e!r}")


def _send_test_alert(client: SlackClient, cfg: dict) -> None:
    """Post REAL sample alerts to Slack so the user can verify delivery + capture a screenshot.

    Uses live data, not placeholders:
      * CONFIRMED -> the newest real a16z Speedrun company (real founders/cohort/link).
      * EARLY     -> a real founder-announcement post (the X example from the brief).
    """
    from .sources import speedrun
    from .detector import Post, classify_post
    from .index import build_index

    if not client.enabled:
        print("[test-alert] no Slack bot token or webhook configured — nothing to send.")
        print("            Set YC_SLACK_BOT_TOKEN + YC_SLACK_CHANNEL in .env first.")
        return

    samples = []

    # --- CONFIRMED: newest real Speedrun company (has founders) ---
    try:
        recs = speedrun._fetch_all_pages()
        rec = next((r for r in recs if r.get("founder_set")), None)
        if rec:
            samples.append(speedrun._company_to_alert(rec))
        else:
            print("[test-alert] could not fetch a real Speedrun company for the confirmed sample")
    except Exception as e:  # noqa: BLE001
        print(f"[test-alert] Speedrun fetch failed for confirmed sample: {e!r}")

    # --- EARLY: real founder-announcement post, classified against the live index ---
    try:
        from .sources import yc_directory
        idx = build_index(yc_directory.fetch_all_companies(), speedrun._fetch_all_pages())
        early = classify_post(Post(
            source="X (Twitter)", author="Bek", author_handle="beknabdik",
            text=("big news: i got into Y Combinator. solo founder, on my 4th attempt. "
                  "i fell in love with coding in 6th grade in Nukus, Uzbekistan, a city most "
                  "people can't find on a map. now i'm going to SF to build."),
            url="https://x.com/beknabdik/status/2061493360150601738",
            post_id="2061493360150601738",
        ), idx)
        early.extra["batch"] = "YC (not yet officially listed)"
        samples.append(early)
    except Exception as e:  # noqa: BLE001
        print(f"[test-alert] early-signal classification failed: {e!r}")

    if not samples:
        print("[test-alert] no real samples could be built — check network / sources.")
        return

    sent = 0
    for a in samples:
        try:
            if client.send_alert(a, cfg):
                sent += 1
                print(f"[test-alert] sent -> {a.status_emoji} {a.company} ({a.source})")
            else:
                print(f"[test-alert] FAILED to send {a.company}")
        except Exception as e:  # noqa: BLE001
            print(f"[test-alert] error sending {a.company}: {e!r}")
    print(f"[test-alert] delivered {sent}/{len(samples)} REAL sample alerts to Slack")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="YC Launch Monitor Slack bot")
    p.add_argument("--config", default=None)
    p.add_argument("--once", action="store_true", help="run a single pass and exit")
    p.add_argument("--loop", action="store_true", help="run forever at the configured interval")
    p.add_argument("--dry-run", action="store_true", help="print alerts instead of sending to Slack")
    p.add_argument("--reset", action="store_true", help="clear state before running")
    p.add_argument("--test-alert", action="store_true",
                   help="send a sample alert to Slack immediately (to verify delivery), then exit")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    state = State(cfg["state"]["db_path"])
    if args.reset:
        state.conn.execute("DELETE FROM seen_events")
        state.conn.execute("DELETE FROM snapshots")
        state.conn.commit()
        print("[state] reset done")

    client = SlackClient(cfg["slack"]["bot_token"], cfg["slack"]["webhook_url"])
    if args.dry_run:
        client = SlackClient()  # force console output

    # Send a sample alert to verify Slack delivery, then exit.
    if args.test_alert:
        _send_test_alert(client, cfg)
        state.close()
        return 0

    # Optional Pond health endpoint for ongoing monitoring.
    hport = int(cfg.get("pond", {}).get("health_port", 0) or 0)
    if hport > 0:
        health.start_health_server(hport)

    if args.loop:
        interval = int(cfg["schedule"].get("interval_minutes", 480))
        print(f"[monitor] loop mode — polling every {interval} min (Ctrl-C to stop)")
        while True:
            _tick(cfg, state, client)
            time.sleep(interval * 60)
    else:
        _tick(cfg, state, client)

    state.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
