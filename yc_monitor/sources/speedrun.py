"""a16z Speedrun collector (official source).

Data source: Speedrun's public paginated REST API (free, no key):
    https://speedrun-api.a16z.com/api/companies/companies/

NOTE: "Speedrun" is the a16z accelerator (speedrun.a16z.com), a distinct program
from Y Combinator. It is monitored separately and tagged as its own source.

Each record includes founder names, X/LinkedIn/website URLs, cohort, industries
and a one-line preamble — everything needed for a rich Slack alert.

Detection: diff the full paginated slug list against state. New slugs = newly
published Speedrun companies (status=CONFIRMED).
"""
from __future__ import annotations

from typing import List

from .http import get_json, SourceError
from ..models import Alert, STATUS_CONFIRMED, make_dedup_key

API = "https://speedrun-api.a16z.com/api/companies/companies/"


def _founder_names(record: dict) -> str:
    names = []
    for f in record.get("founder_set") or []:
        fn = (f.get("first_name") or "").strip()
        ln = (f.get("last_name") or "").strip()
        if fn or ln:
            names.append(f"{fn} {ln}".strip())
    return ", ".join(names)


def _company_to_alert(record: dict) -> Alert:
    name = record.get("name") or record.get("slug") or "Unknown"
    slug = record.get("slug") or ""
    link = f"https://speedrun.a16z.com/companies/{slug}" if slug else "https://speedrun.a16z.com/companies"
    preamble = record.get("preamble") or record.get("description") or ""
    return Alert(
        company=name,
        source="Speedrun",
        status=STATUS_CONFIRMED,
        founder=_founder_names(record),
        details=preamble,
        link=link,
        dedup_key=make_dedup_key("speedrun", record.get("id") or slug or name),
        extra={
            "cohort": record.get("cohort", ""),
            "website": record.get("website_url", ""),
            "x_url": record.get("x_url", ""),
            "linkedin_url": record.get("linkedin_url", ""),
            "industries": record.get("industries", []),
        },
    )


def _fetch_all_pages() -> List[dict]:
    records: List[dict] = []
    url = f"{API}?limit=50&ordering=name"
    seen_urls = set()
    while url and url not in seen_urls:
        seen_urls.add(url)
        data = get_json(url)
        records.extend(data.get("results") or [])
        url = data.get("next")
    return records


def collect_new(state) -> List[Alert]:
    alerts: List[Alert] = []
    try:
        records = _fetch_all_pages()
    except SourceError as e:
        print(f"[speedrun] fetch failed: {e}")
        return alerts

    slugs = sorted((r.get("slug") or r.get("id") or "") for r in records)
    if state.snapshot_unchanged("speedrun_all", slugs):
        return alerts
    had_snapshot = _has_snapshot(state, "speedrun_all")
    state.update_snapshot("speedrun_all", slugs)
    if not had_snapshot:
        return alerts  # first baseline run

    for rec in records:
        alert = _company_to_alert(rec)
        if not state.is_seen(alert.dedup_key):
            alerts.append(alert)
            state.mark_seen(alert.dedup_key, alert.source, alert.company)
    return alerts


def _has_snapshot(state, snap_key: str) -> bool:
    return state.conn.execute("SELECT 1 FROM snapshots WHERE source = ?", (snap_key,)).fetchone() is not None
