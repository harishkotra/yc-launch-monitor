"""YC Launch Monitor — configuration loading."""
from __future__ import annotations

import os
from typing import Optional

import yaml


DEFAULTS = {
    "slack": {
        # Either provide an OAuth bot token (recommended, posts to channel/DM)
        # OR a legacy Incoming Webhook URL (simplest).
        "bot_token": "",        # xoxb-...  (Slack app bot token)
        "webhook_url": "",      # https://hooks.slack.com/services/... (fallback)
        "channel": "",          # channel name/ID, or a user ID for a DM
        "username": "YC Launch Monitor",
        "mention": "",
    },
    "schedule": {"interval_minutes": 480},   # default = every 8 hours
    "sources": {"yc_directory": True, "speedrun": True, "x_twitter": False, "linkedin": False},
    "x_twitter": {
        "bearer_token": "",
        "query": "",
        "max_results": 50,
        "freshness_minutes": 60,
    },
    "linkedin": {"endpoint": "", "api_key": "", "query": "", "freshness_minutes": 60},
    "detection": {"min_batch": "", "lookback_batches": 3},
    "state": {"db_path": "state.db"},
    "pond": {
        "agent_id": "",          # your Pond agent id (joinpond.ai/agent/create)
        "report_path": "pond_report.json",   # machine-readable verification report
        "health_port": 0,        # >0 to run a /health HTTP server for monitoring
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Optional[str] = None) -> dict:
    cfg = deep_merge(DEFAULTS, {})
    candidates = [path] if path else ["config.yaml", "config.example.yaml"]
    for c in candidates:
        if c and os.path.exists(c):
            with open(c, "r") as fh:
                user_cfg = yaml.safe_load(fh) or {}
            cfg = deep_merge(cfg, user_cfg)
            break
    # Environment overrides for secrets (never commit keys).
    if os.environ.get("YC_SLACK_BOT_TOKEN"):
        cfg["slack"]["bot_token"] = os.environ["YC_SLACK_BOT_TOKEN"]
    if os.environ.get("YC_SLACK_WEBHOOK"):
        cfg["slack"]["webhook_url"] = os.environ["YC_SLACK_WEBHOOK"]
    if os.environ.get("YC_SLACK_CHANNEL"):
        cfg["slack"]["channel"] = os.environ["YC_SLACK_CHANNEL"]
    if os.environ.get("YC_X_BEARER_TOKEN"):
        cfg["x_twitter"]["bearer_token"] = os.environ["YC_X_BEARER_TOKEN"]
    if os.environ.get("YC_LINKEDIN_API_KEY"):
        cfg["linkedin"]["api_key"] = os.environ["YC_LINKEDIN_API_KEY"]
    if os.environ.get("YC_POND_AGENT_ID"):
        cfg["pond"]["agent_id"] = os.environ["YC_POND_AGENT_ID"]
    return cfg
