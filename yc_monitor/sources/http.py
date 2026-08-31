"""Shared HTTP helpers for source collectors."""
from __future__ import annotations

import time
from typing import Any, Optional

import requests

DEFAULT_TIMEOUT = 30
HEADERS = {"User-Agent": "yc-launch-monitor/1.0 (Slack bot)"}


class SourceError(Exception):
    """Raised when a data source is unreachable or returns garbage."""


def get_json(url: str, headers: Optional[dict] = None, params: Optional[dict] = None,
             timeout: int = DEFAULT_TIMEOUT, retries: int = 2) -> Any:
    """GET a URL and return parsed JSON, with simple retry/backoff."""
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers={**HEADERS, **(headers or {})},
                             params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise SourceError(f"GET {url} failed: {last_err!r}")


def get_text(url: str, headers: Optional[dict] = None, timeout: int = DEFAULT_TIMEOUT) -> str:
    r = requests.get(url, headers={**HEADERS, **(headers or {})}, timeout=timeout)
    r.raise_for_status()
    return r.text
