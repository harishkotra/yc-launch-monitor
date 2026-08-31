"""Pond integration — verification report + health monitoring.

Pond (joinpond.ai) is the agentic task marketplace where this bot is submitted.
To let Pond reviewers verify the work and support ongoing health monitoring, we
emit a machine-readable report each run and can expose a tiny /health endpoint.

Register your agent at https://joinpond.ai/agent/create and set pond.agent_id.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import List

from .models import Alert


def write_report(alerts: List[Alert], cfg: dict, stats: dict, path: str = "pond_report.json") -> str:
    """Write a verification report for Pond reviewers."""
    report = {
        "agent": (cfg.get("pond") or {}).get("agent_id", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources_enabled": {
            "yc_directory": cfg["sources"].get("yc_directory", True),
            "speedrun": cfg["sources"].get("speedrun", True),
            "x_twitter": cfg["sources"].get("x_twitter", False),
            "linkedin": cfg["sources"].get("linkedin", False),
        },
        "state": stats,
        "alerts_this_run": [a.to_dict() for a in alerts],
        "total_alerts_seen": stats.get("seen_events", 0),
    }
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    return path


# ---------------------------------------------------------------------------
# Optional /health HTTP server for external monitoring (uptime checks).
# ---------------------------------------------------------------------------
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps({"status": "ok", "service": "yc-launch-monitor",
                           "time": datetime.now(timezone.utc).isoformat()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        pass


def start_health_server(port: int) -> threading.Thread:
    srv = HTTPServer(("0.0.0.0", port), _HealthHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    print(f"[pond] /health listening on :{port}")
    return t
