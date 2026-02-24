"""
Centralized HTTP Client Factory (P1-2).

Every outbound HTTP call in the system MUST use this module.
Provides:
  - Configurable timeout, retries, exponential backoff + jitter
  - Consistent User-Agent and headers
  - Structured logging for every request attempt
  - Injectable sleep function for testing

Usage::

    from app.core.http import http_fetch, http_fetch_bytes, get_http_client

    # Simple fetch (text)
    text = await http_fetch("https://example.com/data")

    # Binary fetch (e.g. PDF)
    pdf_bytes = await http_fetch_bytes("https://doclib.ngxgroup.com/...")

    # Low-level: get a configured client for custom usage
    async with get_http_client() as client:
        resp = await client.get(url)
"""

import asyncio
import logging
import random
from typing import Any, Callable, Coroutine, Dict, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Type alias for injectable sleep (for testing)
SleepFunc = Callable[[float], Coroutine[Any, Any, None]]


def _default_timeout() -> float:
    return get_settings().HTTP_TIMEOUT_SECONDS


def _default_max_retries() -> int:
    return get_settings().HTTP_MAX_RETRIES


def _default_backoff_base() -> float:
    return get_settings().HTTP_BACKOFF_BASE


def _default_backoff_max() -> float:
    return get_settings().HTTP_BACKOFF_MAX


def _default_user_agent() -> str:
    return get_settings().HTTP_USER_AGENT


def _default_headers() -> Dict[str, str]:
    return {
        "User-Agent": _default_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def compute_backoff(attempt: int, base: float, maximum: float) -> float:
    """
    Compute exponential backoff with full jitter.

    delay = random(0, min(max, base * 2^attempt))
    """
    exp = min(maximum, base * (2 ** attempt))
    return random.uniform(0, exp)


def get_http_client(
    timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
) -> httpx.AsyncClient:
    """
    Create a configured httpx.AsyncClient.

    Use as an async context manager::

        async with get_http_client() as client:
            resp = await client.get(url)
    """
    t = timeout or _default_timeout()
    h = headers or _default_headers()
    return httpx.AsyncClient(
        timeout=t,
        headers=h,
        follow_redirects=follow_redirects,
    )


async def http_fetch(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
    backoff_base: Optional[float] = None,
    backoff_max: Optional[float] = None,
    raise_for_status: bool = True,
    _sleep: Optional[SleepFunc] = None,
) -> httpx.Response:
    """
    Fetch a URL with retry + backoff + jitter.

    Returns the httpx.Response on success.
    Raises httpx.HTTPStatusError or httpx.TimeoutException after
    all retries are exhausted.

    Args:
        url: Target URL
        method: HTTP method (default GET)
        headers: Extra headers (merged with defaults)
        timeout: Override timeout in seconds
        max_retries: Override max retry count
        backoff_base: Override backoff base
        backoff_max: Override backoff max
        raise_for_status: If True, raise on 4xx/5xx after retries
        _sleep: Injectable sleep for testing (default asyncio.sleep)
    """
    _timeout = timeout or _default_timeout()
    _retries = max_retries if max_retries is not None else _default_max_retries()
    _base = backoff_base or _default_backoff_base()
    _max = backoff_max or _default_backoff_max()
    _sleeper = _sleep or asyncio.sleep

    merged_headers = _default_headers()
    if headers:
        merged_headers.update(headers)

    last_exc: Optional[Exception] = None

    for attempt in range(_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=_timeout,
                headers=merged_headers,
                follow_redirects=True,
            ) as client:
                resp = await client.request(method, url)

                if raise_for_status:
                    resp.raise_for_status()

                logger.debug(
                    "HTTP %s %s → %d (%d bytes) [attempt %d]",
                    method, url, resp.status_code, len(resp.content), attempt + 1,
                )
                return resp

        except httpx.TimeoutException as exc:
            last_exc = exc
            logger.warning(
                "HTTP timeout %s %s (attempt %d/%d)",
                method, url, attempt + 1, _retries + 1,
            )
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            status = exc.response.status_code
            # Don't retry 4xx (except 429 Too Many Requests)
            if 400 <= status < 500 and status != 429:
                logger.warning(
                    "HTTP %d %s %s — not retrying client error",
                    status, method, url,
                )
                raise
            logger.warning(
                "HTTP %d %s %s (attempt %d/%d)",
                status, method, url, attempt + 1, _retries + 1,
            )
        except httpx.RequestError as exc:
            last_exc = exc
            logger.warning(
                "HTTP request error %s %s: %s (attempt %d/%d)",
                method, url, exc, attempt + 1, _retries + 1,
            )

        # Backoff before next retry (skip on last attempt)
        if attempt < _retries:
            delay = compute_backoff(attempt, _base, _max)
            logger.debug("Backing off %.2fs before retry", delay)
            await _sleeper(delay)

    # All retries exhausted
    logger.error(
        "HTTP %s %s failed after %d attempts: %s",
        method, url, _retries + 1, last_exc,
    )
    raise last_exc  # type: ignore[misc]


async def http_fetch_text(url: str, **kwargs: Any) -> str:
    """Fetch URL and return response text."""
    resp = await http_fetch(url, **kwargs)
    return resp.text


async def http_fetch_bytes(url: str, **kwargs: Any) -> bytes:
    """Fetch URL and return response bytes."""
    resp = await http_fetch(url, **kwargs)
    return resp.content
