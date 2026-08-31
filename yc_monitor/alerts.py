"""Slack delivery — supports BOTH an OAuth bot token (recommended) and a
legacy Incoming Webhook (fallback).

Bot token path uses the Slack Web API `chat.postMessage`, which can post to a
channel or open a DM with a user. Webhook path POSTs the same Block Kit payload
to the webhook URL.
"""
from __future__ import annotations

from typing import List

import requests

from .models import Alert

API = "https://slack.com/api/chat.postMessage"


class SlackClient:
    def __init__(self, bot_token: str = "", webhook_url: str = ""):
        self.bot_token = bot_token
        self.webhook_url = webhook_url

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token or self.webhook_url)

    def send_payload(self, payload: dict) -> bool:
        if self.bot_token:
            # chat.postMessage: payload already carries channel + blocks.
            r = requests.post(API, json=payload,
                              headers={"Authorization": f"Bearer {self.bot_token}"}, timeout=20)
            data = r.json()
            return r.status_code == 200 and data.get("ok") is True
        if self.webhook_url:
            r = requests.post(self.webhook_url, json=payload, timeout=20)
            return r.status_code == 200
        return False

    def send_alert(self, alert: Alert, cfg: dict) -> bool:
        payload = alert.to_slack_payload(cfg)
        return self.send_payload(payload)


def render_alerts_for_dry_run(alerts: List[Alert]) -> str:
    """Human-readable rendering for --dry-run / console output."""
    lines = []
    for a in alerts:
        lines.append("=" * 60)
        lines.append(f"{a.status_emoji} {a.company}   ({a.source})")
        lines.append(f"   Status: {a.status_label}")
        if a.extra.get("batch"):
            lines.append(f"   Batch: {a.extra['batch']}")
        if a.extra.get("cohort"):
            lines.append(f"   Cohort: {a.extra['cohort']}")
        if a.founder:
            lines.append(f"   Founder: {a.founder}")
        if a.extra.get("author_handle"):
            lines.append(f"   Handle: @{a.extra['author_handle']}")
        if a.details:
            lines.append(f"   Details: {a.details[:220]}")
        if a.link:
            lines.append(f"   Link: {a.link}")
        lines.append(f"   Detected: {a.detected_at}")
    if not lines:
        lines.append("(no new alerts)")
    return "\n".join(lines)
