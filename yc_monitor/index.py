"""Company index — the lookup table used to classify social posts.

Builds a set of *officially known* YC + Speedrun companies (from the directory
and program APIs) so the detector can decide whether a founder announcement is:

  * EARLY     — founder announced on social, but the company is NOT yet in the
                official YC directory / Speedrun listing (the valuable signal).
  * CONFIRMED — the company is already officially listed.

Also indexes X handles and company names for fuzzy matching.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class CompanyIndex:
    yc_slugs: Set[str] = field(default_factory=set)
    yc_names: Set[str] = field(default_factory=set)
    speedrun_slugs: Set[str] = field(default_factory=set)
    speedrun_names: Set[str] = field(default_factory=set)
    x_handles: Dict[str, str] = field(default_factory=dict)   # handle -> company name
    by_name: Dict[str, dict] = field(default_factory=dict)    # name(lower) -> info

    # -- lookups ----------------------------------------------------------
    def company_by_name(self, name_lower: str) -> Optional[dict]:
        return self.by_name.get(name_lower)

    def is_official(self, name_lower: str) -> bool:
        return name_lower in self.yc_names or name_lower in self.speedrun_names

    def is_official_slug(self, slug: str) -> bool:
        return slug in self.yc_slugs or slug in self.speedrun_slugs

    def company_by_handle(self, handle: str) -> Optional[str]:
        return self.x_handles.get(handle.lstrip("@").lower())


def build_index(yc_companies: List[dict], speedrun_records: List[dict]) -> CompanyIndex:
    idx = CompanyIndex()
    for c in yc_companies or []:
        name = (c.get("name") or "").strip()
        slug = (c.get("slug") or "").strip()
        if slug:
            idx.yc_slugs.add(slug)
        if name:
            nl = name.lower()
            idx.yc_names.add(nl)
            idx.by_name[nl] = {"name": name, "slug": slug, "source": "yc", "url": c.get("url", "")}
    for r in speedrun_records or []:
        name = (r.get("name") or "").strip()
        slug = (r.get("slug") or "").strip()
        if slug:
            idx.speedrun_slugs.add(slug)
        if name:
            nl = name.lower()
            idx.speedrun_names.add(nl)
            idx.by_name[nl] = {"name": name, "slug": slug, "source": "speedrun",
                               "url": f"https://speedrun.a16z.com/companies/{slug}" if slug else ""}
        handle = (r.get("x_url") or "").rstrip("/").split("/")[-1].lower()
        if handle and handle not in ("", "x.com", "twitter.com"):
            idx.x_handles[handle] = name
    return idx
