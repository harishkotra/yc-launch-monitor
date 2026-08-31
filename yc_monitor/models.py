"""Core data models for the YC Launch Monitor."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

# Alert statuses
STATUS_EARLY = "early"        # ⚡ founder announced before official YC/Speedrun listing
STATUS_CONFIRMED = "confirmed"  # ✅ confirmed by official directory / program

STATUS_EMOJI = {STATUS_EARLY: "⚡", STATUS_CONFIRMED: "✅"}
STATUS_LABEL = {
    STATUS_EARLY: "Early signal — founder announced before official listing",
    STATUS_CONFIRMED: "Confirmed by official directory",
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Alert:
    """One Slack alert = one detected launch / founder announcement."""
    company: str
    source: str                      # "YC Directory" | "Speedrun" | "X (Twitter)" | "LinkedIn"
    status: str = STATUS_EARLY       # early | confirmed
    founder: str = ""
    details: str = ""
    link: str = ""
    dedup_key: str = ""
    detected_at: str = field(default_factory=utcnow_iso)
    extra: dict = field(default_factory=dict)   # batch, cohort, x_url, website, unmatched, ...

    # -- helpers ----------------------------------------------------------
    @property
    def status_emoji(self) -> str:
        return STATUS_EMOJI.get(self.status, "🔔")

    @property
    def status_label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    def to_slack_payload(self, cfg: dict) -> dict:
        """Render as a Slack Block Kit message (chat.postMessage / webhook)."""
        slack = cfg.get("slack") or {}
        mention = (slack.get("mention") or "").strip()

        blocks: list = []
        # Header
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": f"{self.status_emoji} {self.company}"},
        })

        # Status + source context
        src_badge = f"*Source:* {self.source}"
        status_badge = f"*Status:* {self.status_emoji} {self.status_label}"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"{src_badge}\n{status_badge}"}})

        # Batch / cohort line
        meta = []
        if self.extra.get("batch"):
            meta.append(f"*Batch:* {self.extra['batch']}")
        if self.extra.get("cohort"):
            meta.append(f"*Cohort:* {self.extra['cohort']}")
        if self.founder:
            meta.append(f"*Founder:* {self.founder}")
        if self.extra.get("username"):
            meta.append(f"*X:* {self.extra['username']}")
        if meta:
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "   ·   ".join(meta)}]})

        # Description
        if self.details:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": self.details[:3000]}})

        # Links
        links = []
        if self.link:
            links.append({"type": "button", "text": {"type": "plain_text", "text": "Original post ↗"},
                          "url": self.link, "action_id": "original"})
        website = self.extra.get("website") or self.extra.get("website_url")
        if website:
            links.append({"type": "button", "text": {"type": "plain_text", "text": "Website ↗"},
                          "url": website, "action_id": "website"})
        if links:
            blocks.append({"type": "actions", "elements": links})

        # Footer: detected time
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"Detected: {self.detected_at} UTC"}]})

        payload = {"username": slack.get("username", "YC Launch Monitor"), "blocks": blocks}
        channel = (slack.get("channel") or "").strip()
        if channel:
            payload["channel"] = channel
        if mention:
            payload["text"] = f"<{mention}> New launch alert"
        return payload

    def to_dict(self) -> dict:
        return asdict(self)


def make_dedup_key(*parts: Any) -> str:
    """Stable dedup key from parts (lowercased, joined by '|')."""
    clean = []
    for p in parts:
        if p is None:
            continue
        s = str(p).strip().lower()
        if s:
            clean.append(s)
    return "|".join(clean)
