"""LinkedIn founder-announcement collector.

LinkedIn has no free public API, so this is a pluggable adapter. Point
`linkedin.endpoint` at any service (scraping API, internal search adapter,
browser-automation worker) that accepts a POST:
    {"query": "<keywords>", "freshness_minutes": N}
and returns:
    {"results": [{"author","text","url","published_at"}]}

Returns raw :class:`Post` objects for the detector to classify.
Skipped gracefully when no endpoint is configured.
"""
from __future__ import annotations

from typing import List

import requests

from ..detector import Post


def _is_configured(cfg: dict) -> bool:
    return bool((cfg.get("linkedin") or {}).get("endpoint"))


def _call_adapter(cfg: dict) -> List[dict]:
    li = cfg["linkedin"]
    headers = {"Content-Type": "application/json"}
    if li.get("api_key"):
        headers["Authorization"] = f"Bearer {li['api_key']}"
    body = {"query": li.get("query", ""), "freshness_minutes": int(li.get("freshness_minutes", 60))}
    r = requests.post(li["endpoint"], json=body, headers=headers, timeout=40)
    r.raise_for_status()
    return (r.json().get("results") or [])


def collect_posts(cfg: dict) -> List[Post]:
    if not _is_configured(cfg):
        print("[linkedin] no endpoint configured — skipping (see config.example.yaml)")
        return []
    try:
        results = _call_adapter(cfg)
    except Exception as e:  # noqa: BLE001
        print(f"[linkedin] adapter call failed: {e}")
        return []

    posts: List[Post] = []
    for item in results:
        url = item.get("url") or ""
        posts.append(Post(
            source="LinkedIn",
            author=item.get("author") or "Unknown",
            text=(item.get("text") or "").strip(),
            url=url,
            published_at=item.get("published_at") or "",
            post_id=url or item.get("id") or "",
            raw=item,
        ))
    return posts
