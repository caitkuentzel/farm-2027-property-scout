"""Small bounded-retry helpers for public government data services."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def _retryable(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return error.code == 429 or error.code >= 500
    return isinstance(error, (URLError, TimeoutError, ConnectionResetError))


def load_json_with_retries(
    url: str,
    *,
    timeout_seconds: int = 120,
    attempts: int = 3,
    opener: Callable[..., Any] = urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Load JSON with limited backoff for resets, timeouts, rate limits, and 5xx errors."""
    if attempts < 1:
        raise ValueError("attempts must be at least one")
    for attempt in range(1, attempts + 1):
        try:
            with opener(url, timeout=timeout_seconds) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, ConnectionResetError) as error:
            if attempt == attempts or not _retryable(error):
                raise
            sleep(float(2 ** (attempt - 1)))
    raise AssertionError("retry loop exited unexpectedly")
