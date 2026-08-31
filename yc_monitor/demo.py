"""Demo / verification: simulate the two key alert scenarios and render the
exact Slack Block Kit payloads to files for review and screenshots.

Scenario 1 — EARLY signal (the example): a founder announces YC acceptance on
X before the company is officially listed.
Scenario 2 — CONFIRMED: a real Speedrun company from the official API.

Run:  python -m yc_monitor.demo
Outputs payload JSON to demo/out/*.json and prints a console preview.
"""
from __future__ import annotations

import json
import os

from .detector import Post, classify_post
from .index import build_index
from .sources import yc_directory, speedrun
from .config import load_config

OUT = os.path.join(os.path.dirname(__file__), "..", "demo", "out")


def _load_index():
    yc = yc_directory.fetch_all_companies()
    sr = speedrun._fetch_all_pages()
    return build_index(yc, sr)


def main():
    os.makedirs(OUT, exist_ok=True)
    cfg = load_config()
    idx = _load_index()
    print(f"[demo] index: {len(idx.yc_slugs)} YC slugs, {len(idx.speedrun_slugs)} Speedrun slugs")

    # --- Scenario 1: early founder signal (the example tweet) ---
    early = classify_post(Post(
        source="X (Twitter)",
        author="Bek",
        author_handle="beknabdik",
        text=("big news: i got into Y Combinator. solo founder, on my 4th attempt. "
              "i fell in love with coding in 6th grade in Nukus, Uzbekistan, a city most "
              "people can't find on a map. since then it's been building, failing, learning, "
              "starting again: Amazon, founding engineer at a Korean startup, then building "
              "my own thing. now i'm going to SF."),
        url="https://x.com/beknabdik/status/2061493360150601738",
        post_id="2061493360150601738",
    ), idx)
    early.extra["batch"] = "YC (not yet officially listed)"

    # --- Scenario 2: confirmed Speedrun company (real record) ---
    recs = speedrun._fetch_all_pages()
    rec = next(r for r in recs if r.get("founder_set"))
    confirmed = speedrun._company_to_alert(rec)

    for name, alert in (("early_signal", early), ("confirmed", confirmed)):
        payload = alert.to_slack_payload(cfg)
        path = os.path.join(OUT, f"{name}.json")
        with open(path, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\n[demo] wrote {path}")
        print(f"  {alert.status_emoji} {alert.company}  ({alert.source})")
        print(f"  status: {alert.status_label}")
        print(f"  founder: {alert.founder or '—'}")
        print(f"  link: {alert.link}")


if __name__ == "__main__":
    main()
