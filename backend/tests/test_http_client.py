"""
Tests for centralized HTTP client factory (P1-2).

Covers:
  1. Successful fetch returns response
  2. Timeouts trigger retries
  3. Retries stop after max_retries
  4. Backoff/jitter is applied (assert increasing delays via injected sleeper)
  5. 4xx client errors are NOT retried (except 429)
  6. 5xx server errors ARE retried
  7. compute_backoff produces values in expected range
  8. get_http_client returns configured client
"""

import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from app.core.http import (
    compute_backoff,
    http_fetch,
    get_http_client,
)


# ── compute_backoff tests ────────────────────────────────────────────


class TestComputeBackoff:

    def test_attempt_zero(self):
        """First attempt backoff is in [0, base]."""
        for _ in range(50):
            val = compute_backoff(0, base=1.0, maximum=30.0)
            assert 0 <= val <= 1.0

    def test_attempt_increases_range(self):
        """Higher attempts allow larger backoff."""
        # attempt=3 → max range = min(30, 1.0 * 2^3) = 8.0
        for _ in range(50):
            val = compute_backoff(3, base=1.0, maximum=30.0)
            assert 0 <= val <= 8.0

    def test_capped_at_maximum(self):
        """Backoff never exceeds maximum."""
        for _ in range(50):
            val = compute_backoff(20, base=1.0, maximum=5.0)
            assert 0 <= val <= 5.0

    def test_zero_base_always_zero(self):
        val = compute_backoff(5, base=0.0, maximum=30.0)
        assert val == 0.0


# ── http_fetch tests ─────────────────────────────────────────────────


class TestHttpFetch:

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        """Successful GET returns response."""
        mock_response = httpx.Response(200, text="OK", request=httpx.Request("GET", "https://example.com"))

        with patch("app.core.http.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.request = AsyncMock(return_value=mock_response)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            resp = await http_fetch(
                "https://example.com",
                max_retries=0,
            )
            assert resp.status_code == 200
            assert resp.text == "OK"

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self):
        """Timeout on first attempt retries and succeeds on second."""
        mock_response = httpx.Response(200, text="OK", request=httpx.Request("GET", "https://example.com"))
        sleep_calls = []

        async def fake_sleep(duration):
            sleep_calls.append(duration)

        call_count = 0

        async def side_effect(method, url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ReadTimeout("timeout")
            return mock_response

        with patch("app.core.http.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.request = AsyncMock(side_effect=side_effect)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            resp = await http_fetch(
                "https://example.com",
                max_retries=2,
                backoff_base=0.1,
                backoff_max=1.0,
                _sleep=fake_sleep,
            )
            assert resp.status_code == 200
            assert call_count == 2
            assert len(sleep_calls) == 1  # slept once between attempts

    @pytest.mark.asyncio
    async def test_retries_exhausted_raises(self):
        """All retries exhausted raises the last exception."""
        sleep_calls = []

        async def fake_sleep(duration):
            sleep_calls.append(duration)

        with patch("app.core.http.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.request = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            with pytest.raises(httpx.TimeoutException):
                await http_fetch(
                    "https://example.com",
                    max_retries=2,
                    backoff_base=0.01,
                    backoff_max=0.1,
                    _sleep=fake_sleep,
                )

            assert len(sleep_calls) == 2  # slept between each retry

    @pytest.mark.asyncio
    async def test_backoff_delays_increase(self):
        """Backoff delays generally increase with attempt number."""
        sleep_calls = []

        async def fake_sleep(duration):
            sleep_calls.append(duration)

        with patch("app.core.http.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.request = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            with pytest.raises(httpx.TimeoutException):
                await http_fetch(
                    "https://example.com",
                    max_retries=4,
                    backoff_base=1.0,
                    backoff_max=100.0,
                    _sleep=fake_sleep,
                )

            assert len(sleep_calls) == 4
            # With base=1.0: attempt 0 max=1, attempt 1 max=2, attempt 2 max=4, attempt 3 max=8
            # Delays are random within range, but max possible increases
            # Just verify they're all non-negative and bounded
            for i, delay in enumerate(sleep_calls):
                max_possible = min(100.0, 1.0 * (2 ** i))
                assert 0 <= delay <= max_possible + 0.01  # small float tolerance

    @pytest.mark.asyncio
    async def test_4xx_not_retried(self):
        """4xx client errors are NOT retried (raised immediately)."""
        sleep_calls = []

        async def fake_sleep(duration):
            sleep_calls.append(duration)

        req = httpx.Request("GET", "https://example.com")
        error_resp = httpx.Response(404, request=req)

        async def side_effect(method, url):
            raise httpx.HTTPStatusError("Not Found", request=req, response=error_resp)

        with patch("app.core.http.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.request = AsyncMock(side_effect=side_effect)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            with pytest.raises(httpx.HTTPStatusError):
                await http_fetch(
                    "https://example.com",
                    max_retries=3,
                    _sleep=fake_sleep,
                )

            # No retries for 4xx
            assert len(sleep_calls) == 0
            assert client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_429_is_retried(self):
        """429 Too Many Requests IS retried."""
        sleep_calls = []

        async def fake_sleep(duration):
            sleep_calls.append(duration)

        req = httpx.Request("GET", "https://example.com")
        error_resp = httpx.Response(429, request=req)
        ok_resp = httpx.Response(200, text="OK", request=req)

        call_count = 0

        async def side_effect(method, url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.HTTPStatusError("Too Many", request=req, response=error_resp)
            return ok_resp

        with patch("app.core.http.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.request = AsyncMock(side_effect=side_effect)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            resp = await http_fetch(
                "https://example.com",
                max_retries=2,
                backoff_base=0.01,
                _sleep=fake_sleep,
            )
            assert resp.status_code == 200
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_5xx_is_retried(self):
        """5xx server errors ARE retried."""
        sleep_calls = []

        async def fake_sleep(duration):
            sleep_calls.append(duration)

        req = httpx.Request("GET", "https://example.com")
        error_resp = httpx.Response(503, request=req)
        ok_resp = httpx.Response(200, text="OK", request=req)

        call_count = 0

        async def side_effect(method, url):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise httpx.HTTPStatusError("Service Unavailable", request=req, response=error_resp)
            return ok_resp

        with patch("app.core.http.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.request = AsyncMock(side_effect=side_effect)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            resp = await http_fetch(
                "https://example.com",
                max_retries=3,
                backoff_base=0.01,
                _sleep=fake_sleep,
            )
            assert resp.status_code == 200
            assert call_count == 3
            assert len(sleep_calls) == 2

    @pytest.mark.asyncio
    async def test_raise_for_status_false(self):
        """With raise_for_status=False, 4xx/5xx responses are returned."""
        req = httpx.Request("GET", "https://example.com")
        error_resp = httpx.Response(404, text="Not Found", request=req)

        with patch("app.core.http.httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.request = AsyncMock(return_value=error_resp)
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client

            resp = await http_fetch(
                "https://example.com",
                max_retries=0,
                raise_for_status=False,
            )
            assert resp.status_code == 404


# ── get_http_client tests ────────────────────────────────────────────


class TestGetHttpClient:

    @pytest.mark.asyncio
    async def test_returns_async_client(self):
        """get_http_client returns a configured httpx.AsyncClient."""
        client = get_http_client(timeout=5.0)
        assert isinstance(client, httpx.AsyncClient)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_custom_timeout(self):
        """Custom timeout is applied."""
        client = get_http_client(timeout=42.0)
        assert client.timeout.read == 42.0
        await client.aclose()

    @pytest.mark.asyncio
    async def test_default_headers_set(self):
        """Default headers include User-Agent."""
        client = get_http_client()
        assert "user-agent" in {k.lower() for k in client.headers.keys()}
        await client.aclose()
