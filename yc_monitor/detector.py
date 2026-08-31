"""Early-detection classifier for social founder announcements.

Turns a raw social post (X/LinkedIn) into a classified Alert:

  * EARLY     -> the founder's company is NOT in the official YC/Speedrun index
                 => "⚡ Founder announced before official listing" (the key signal)
  * CONFIRMED -> the company IS already officially listed.

Company matching order of confidence:
  1. X handle in the company index (exact)
  2. Company name mentioned in the post text (substring, min length)
  3. Company-like token extracted from the post (heuristic) -> no index match => EARLY
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .models import Alert, STATUS_EARLY, STATUS_CONFIRMED, make_dedup_key


@dataclass
class Post:
    source: str                     # "X (Twitter)" | "LinkedIn"
    author: str
    author_handle: str = ""         # @handle (X)
    text: str = ""
    url: str = ""
    published_at: str = ""
    post_id: str = ""               # platform-native id for dedup
    raw: dict = field(default_factory=dict)


def _match_company(post: Post, idx) -> Optional[dict]:
    """Best-effort match of a post to a known company. Returns index record or None.

    Only returns a match on a STRONG signal, to avoid false positives (e.g. a
    founder's bio mentioning "Amazon" is not an Amazon launch):
      1. The author's X handle matches a company's handle (exact), OR
      2. A company name appears as a whole word within a small window of an
         announcement keyword in the post text.
    Excludes the accelerator names themselves ("Y Combinator" / "YC").
    """
    STOP = {"y combinator", "yc", "ycombinator", "y-combinator"}
    ANNOUNCE = ["y combinator", "ycombinator", " yc ", "yc,", "yc.", "yc batch",
                "speedrun", "accepted", "got into", "backed by", "batch"]

    # 1) X handle match (strongest)
    if post.author_handle:
        name = idx.company_by_handle(post.author_handle)
        if name:
            rec = idx.company_by_name(name.lower())
            if rec:
                return rec

    # 2) word-boundary company name near an announcement keyword.
    #    Name matching is CASE-SENSITIVE against the original text: founders
    #    capitalize their company name in launch posts, so "solo founder" does
    #    NOT match a company named "Solo". Keywords are matched case-insensitively.
    t_low = post.text.lower()
    t_orig = post.text
    kw_positions = []
    for kw in ANNOUNCE:
        start = 0
        while True:
            i = t_low.find(kw, start)
            if i < 0:
                break
            kw_positions.append(i)
            start = i + len(kw)
    if not kw_positions:
        return None

    import re as _re
    for nl, rec in idx.by_name.items():
        if nl in STOP:
            continue
        name = rec.get("name") or ""
        if len(name) < 3:
            continue
        # word-boundary match of the exact company name in the ORIGINAL text
        for m in _re.finditer(rf"\b{_re.escape(name)}\b", t_orig):
            for kp in kw_positions:
                if abs(m.start() - kp) <= 40:
                    return rec
    return None


def _extract_company_hint(text: str) -> str:
    """Heuristic: the token immediately before 'YC' / 'Y Combinator', skipping
    filler words. Returns '' when no plausible company token is found."""
    FILLERS = {"i", "we", "we're", "got", "get", "accepted", "into", "in", "at",
               "the", "to", "and", "a", "an", "of", "for", "is", "am", "my",
               "big", "news", "great", "so", "super", "very", "finally", "new",
               "excited", "thrilled", "proud", "announce", "announcing", "now"}
    low = text.lower()
    for marker in ["y combinator", "ycombinator", " yc ", "yc,"]:
        idx = low.find(marker)
        if idx >= 0:
            before = [w.strip(".,:;!?\"'()") for w in text[:idx].split()]
            for w in reversed(before):
                if w and w.lower() not in FILLERS:
                    return w
    return ""


def classify_post(post: Post, idx) -> Alert:
    matched = _match_company(post, idx)
    if matched:
        company = matched.get("name") or post.author
        source = matched.get("source")
        status = STATUS_CONFIRMED
        link = matched.get("url") or post.url
        extra = {"batch": "", "cohort": "", "website": "", "x_url": post.url,
                 "unmatched": False, "official_source": source}
    else:
        company = _extract_company_hint(post.text) or "Unknown company"
        status = STATUS_EARLY
        link = post.url
        extra = {"unmatched": True}

    extra["author_handle"] = post.author_handle
    return Alert(
        company=company,
        founder=post.author,
        source=post.source,
        status=status,
        details=post.text,
        link=link,
        dedup_key=make_dedup_key(post.source.lower(), post.post_id or post.url),
        extra=extra,
    )


def classify_many(posts: List[Post], idx) -> List[Alert]:
    return [classify_post(p, idx) for p in posts]
