"""X (Twitter) founder-announcement collector.

Scans X for founders announcing YC / Speedrun acceptance *before* (or around)
the official listing — the early-warning signal. Returns raw :class:`Post`
objects; the detector classifies each as EARLY or CONFIRMED.

Requires an X API v2 Bearer token (developer.x.com, Basic tier ~$100/mo);
`recent` search covers ~7 days. Skipped gracefully when no token is set.
"""
from __future__ import annotations

from typing import List

from .http import get_json, SourceError
from ..detector import Post

RECENT_SEARCH = "https://api.x.com/2/tweets/search/recent"


def _is_configured(cfg: dict) -> bool:
    return bool((cfg.get("x_twitter") or {}).get("bearer_token"))


def _fetch_tweets(bearer: str, query: str, max_results: int) -> dict:
    params = {
        "query": query,
        "max_results": min(max_results, 100),
        "tweet.fields": "author_id,created_at,text",
        "expansions": "author_id",
        "user.fields": "name,username",
    }
    headers = {"Authorization": f"Bearer {bearer}"}
    return get_json(RECENT_SEARCH, headers=headers, params=params)


def _authors(data: dict) -> dict:
    out = {}
    for u in data.get("includes", {}).get("users", []):
        out[u["id"]] = {"name": u.get("name", ""), "username": u.get("username", "")}
    return out


def collect_posts(cfg: dict) -> List[Post]:
    """Return fresh X posts matching the configured YC/Speedrun keywords."""
    if not _is_configured(cfg):
        print("[x_twitter] no bearer_token configured — skipping (set x_twitter.bearer_token or YC_X_BEARER_TOKEN)")
        return []
    xt = cfg["x_twitter"]
    query = (xt.get("query") or "").strip()
    if not query:
        print("[x_twitter] empty query — skipping")
        return []
    try:
        data = _fetch_tweets(xt["bearer_token"], query, int(xt.get("max_results", 50)))
    except SourceError as e:
        print(f"[x_twitter] search failed: {e}")
        return []

    authors = _authors(data)
    posts: List[Post] = []
    for tw in data.get("data") or []:
        author = authors.get(tw.get("author_id") or "", {})
        username = author.get("username") or ""
        tweet_id = tw.get("id")
        posts.append(Post(
            source="X (Twitter)",
            author=author.get("name") or "Unknown",
            author_handle=username,
            text=(tw.get("text") or "").strip(),
            url=f"https://x.com/{username}/status/{tweet_id}" if username else f"https://x.com/i/web/status/{tweet_id}",
            published_at=tw.get("created_at") or "",
            post_id=tweet_id,
            raw=tw,
        ))
    return posts
