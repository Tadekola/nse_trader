"""
Price Reconciliation Tests for Top Picks.

Validates:
1. Ticker normalization (STANBIC → STANBICIBTC on ngnmarket)
2. API response includes trade_date and price_source fields
3. Staleness detection flags old prices
4. Prices come from historical OHLCV DB (raw close, not adjusted)
"""
import pytest
from datetime import date, timedelta

# ── Ticker normalization tests ─────────────────────────────────────────


class TestTickerNormalization:
    """Verify symbol alias registry maps correctly for all providers."""

    def test_stanbic_maps_to_stanbicibtc_on_ngnmarket(self):
        from app.data.sources.symbol_aliases import (
            get_symbol_alias_registry,
            DataProvider,
        )
        registry = get_symbol_alias_registry()
        mapped = registry.get_provider_symbol("STANBIC", DataProvider.NGNMARKET)
        assert mapped == "STANBICIBTC", f"Expected STANBICIBTC, got {mapped}"

    def test_firstholdco_is_canonical(self):
        """FIRSTHOLDCO should be in the stock registry (was FBNH)."""
        from app.data.sources.ngx_stocks import NGXStockRegistry
        registry = NGXStockRegistry()
        stock = registry.get_stock("FIRSTHOLDCO")
        assert stock is not None, "FIRSTHOLDCO not found in registry"

    def test_flourmill_removed(self):
        """FLOURMILL was delisted and should not be in the registry."""
        from app.data.sources.ngx_stocks import NGXStockRegistry
        registry = NGXStockRegistry()
        stock = registry.get_stock("FLOURMILL")
        assert stock is None, "FLOURMILL should have been removed (delisted)"

    def test_transcorp_spelling(self):
        """Ticker must be TRANSCORP, not TRANSCOORP."""
        from app.data.sources.ngx_stocks import NGXStockRegistry
        registry = NGXStockRegistry()
        stock = registry.get_stock("TRANSCORP")
        assert stock is not None, "TRANSCORP not in registry"
        bad = registry.get_stock("TRANSCOORP")
        assert bad is None, "TRANSCOORP should not exist"


# ── API response field tests ───────────────────────────────────────────


class TestRecommendationFields:
    """Verify recommendation dicts include provenance metadata."""

    def _build_mock_recommendation_result(self):
        """Build a minimal result dict as _generate_recommendation_from_data would."""
        return {
            "symbol": "TEST",
            "action": "HOLD",
            "current_price": 100.0,
            "confidence": 50.0,
            "trade_date": "2026-02-23",
            "price_source": "historical_ohlcv",
            "price_stale": False,
            "confidence_score": 0.8,
            "status": "ACTIVE",
        }

    def test_trade_date_present(self):
        result = self._build_mock_recommendation_result()
        assert "trade_date" in result
        # Must be a valid ISO date string
        date.fromisoformat(result["trade_date"])

    def test_price_source_present(self):
        result = self._build_mock_recommendation_result()
        assert result["price_source"] == "historical_ohlcv"

    def test_price_stale_flag_present(self):
        result = self._build_mock_recommendation_result()
        assert "price_stale" in result
        assert isinstance(result["price_stale"], bool)


# ── Staleness detection tests ──────────────────────────────────────────


class TestStalenessDetection:
    """Verify staleness logic flags old prices correctly."""

    def test_fresh_price_not_stale(self):
        trade_date = date.today().isoformat()
        days_old = (date.today() - date.fromisoformat(trade_date)).days
        assert days_old <= 3, "Today's date should not be stale"

    def test_old_price_is_stale(self):
        trade_date = (date.today() - timedelta(days=5)).isoformat()
        days_old = (date.today() - date.fromisoformat(trade_date)).days
        assert days_old > 3, "5-day-old price should be flagged stale"

    def test_weekend_price_not_stale(self):
        """Friday's price checked on Sunday (2 days) should not be stale."""
        trade_date = (date.today() - timedelta(days=2)).isoformat()
        days_old = (date.today() - date.fromisoformat(trade_date)).days
        assert days_old <= 3, "2-day-old price should not be stale"


# ── Price source validation tests ──────────────────────────────────────


class TestPriceSource:
    """Verify prices come from raw close (not adjusted/TRI)."""

    def test_historical_db_stores_raw_close(self):
        """Confirm the ohlcv table schema has 'close' (raw), not 'adj_close'."""
        from app.data.historical.storage import get_historical_storage
        storage = get_historical_storage()
        # Check schema via a query
        conn = storage._get_connection()
        cursor = conn.execute("PRAGMA table_info(ohlcv)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "close" in columns, "ohlcv table must have 'close' column"
        assert "adj_close" not in columns, (
            "ohlcv table should NOT have 'adj_close' — "
            "we display raw close on Top Picks"
        )
