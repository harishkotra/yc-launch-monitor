"""Y Combinator Directory collector (official source).

Data source: the community-maintained `yc-oss/api` GitHub Pages mirror of the
YC directory's Algolia index (updated daily, free, no key):
    https://yc-oss.github.io/api/

Signals:
  1. changes/latest.json -> `added` array = companies newly published in the
     directory since the last daily update (primary, clean signal).
  2. newest-batch slug diff -> baseline-aware backstop for backfills.

Alerts from this source are always status=CONFIRMED (officially listed).
"""
from __future__ import annotations

from typing import List

from .http import get_json, SourceError
from ..models import Alert, STATUS_CONFIRMED, make_dedup_key

BASE = "https://yc-oss.github.io/api"


def _company_to_alert(c: dict) -> Alert:
    batch = c.get("batch") or ""
    name = c.get("name") or c.get("slug") or "Unknown"
    link = c.get("url") or f"https://www.ycombinator.com/companies/{c.get('slug', '')}"
    details = c.get("one_liner") or c.get("long_description") or ""
    return Alert(
        company=name,
        source="YC Directory",
        status=STATUS_CONFIRMED,
        founder="",  # not present in directory list data
        details=details,
        link=link,
        dedup_key=make_dedup_key("yc", c.get("slug") or c.get("id") or name),
        extra={"batch": batch, "website": c.get("website", ""), "industries": c.get("industries", [])},
    )


def fetch_all_companies() -> List[dict]:
    return get_json(f"{BASE}/companies/all.json")


def fetch_changes() -> dict:
    return get_json(f"{BASE}/changes/latest.json")


def collect_new(state) -> List[Alert]:
    """Return CONFIRMED alerts for companies newly added to the YC directory."""
    alerts: List[Alert] = []
    try:
        changes = fetch_changes()
        for c in changes.get("added") or []:
            alert = _company_to_alert(c)
            if not state.is_seen(alert.dedup_key):
                alerts.append(alert)
                state.mark_seen(alert.dedup_key, alert.source, alert.company)
    except SourceError as e:
        print(f"[yc_directory] changes feed failed: {e}")

    try:
        _diff_newest_batch(state, alerts)
    except SourceError as e:
        print(f"[yc_directory] newest-batch diff failed: {e}")
    return alerts


def _diff_newest_batch(state, alerts: List[Alert]) -> None:
    """Baseline-aware diff of the newest batch's slugs."""
    all_companies = fetch_all_companies()
    if not all_companies:
        return
    newest = max((c.get("batch") or "") for c in all_companies)
    newest_companies = [c for c in all_companies if (c.get("batch") or "") == newest]
    if not newest_companies:
        return
    slugs = sorted(c.get("slug") or "" for c in newest_companies)
    snap_key = f"yc_newest_batch:{newest}"
    if not _has_snapshot(state, snap_key):
        state.update_snapshot(snap_key, slugs)   # baseline, no alerts
        return
    if state.snapshot_unchanged(snap_key, slugs):
        return
    state.update_snapshot(snap_key, slugs)
    for c in newest_companies:
        alert = _company_to_alert(c)
        if not state.is_seen(alert.dedup_key):
            alerts.append(alert)
            state.mark_seen(alert.dedup_key, alert.source, alert.company)


def _has_snapshot(state, snap_key: str) -> bool:
    return state.conn.execute("SELECT 1 FROM snapshots WHERE source = ?", (snap_key,)).fetchone() is not None
