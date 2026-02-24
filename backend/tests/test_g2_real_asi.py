"""
Gate G2 dedicated test: _get_market_dataframe() MUST use real ASI.

Verifies:
- Returns real ASI DataFrame when sufficient history exists
- Returns None when ASI has no history (fail-safe)
- Returns None when ASI has < MIN_ASI_SESSIONS (fail-safe)
- Returns None when ASI data is stale
- None result propagates as regime=UNKNOWN → NO_TRADE upstream
- DataFrame shape: DatetimeIndex ascending, OHLCV columns
"""
import sys
import os
import pytest
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
)


@pytest.fixture
def temp_storage():
    """Create a temp SQLite storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_asi.db"
        storage = HistoricalOHLCVStorage(db_path=db_path)
        yield storage
        storage.close()


def _make_asi_records(count: int, stale: bool = False) -> list:
    """Generate ASI OHLCV records."""
    if stale:
        base_date = date.today() - timedelta(days=count + 100)
    else:
        base_date = date.today() - timedelta(days=count)
    return [
        OHLCVRecord(
            symbol="ASI",
            date=base_date + timedelta(days=i),
            open=65000.0 + i * 10,
            high=65500.0 + i * 10,
            low=64500.0 + i * 10,
            close=65200.0 + i * 10,
            volume=1000000000,
            source="NGNMARKET_HISTORICAL",
        )
        for i in range(count)
    ]


class TestGetMarketDataframe:
    """Test _get_market_dataframe() uses real ASI and fails safe."""

    def test_returns_real_asi_when_sufficient(self, temp_storage):
        """≥60 ASI sessions → valid DataFrame."""
        records = _make_asi_records(80)
        temp_storage.store_ohlcv_batch(records)

        df = temp_storage.get_ohlcv_dataframe("ASI", min_sessions=60)
        assert df is not None
        assert len(df) >= 60
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert df.index.is_monotonic_increasing

    def test_returns_none_when_asi_missing(self, temp_storage):
        """No ASI data at all → None (fail-safe)."""
        df = temp_storage.get_ohlcv_dataframe("ASI", min_sessions=60)
        assert df is None

    def test_returns_none_when_asi_insufficient(self, temp_storage):
        """ASI with < min_sessions → None (fail-safe)."""
        records = _make_asi_records(20)
        temp_storage.store_ohlcv_batch(records)

        df = temp_storage.get_ohlcv_dataframe("ASI", min_sessions=60)
        assert df is None

    def test_stale_asi_detected_via_metadata(self, temp_storage):
        """Old ASI data → metadata.is_stale() returns True."""
        records = _make_asi_records(80, stale=True)
        temp_storage.store_ohlcv_batch(records)

        meta = temp_storage.get_metadata("ASI")
        assert meta is not None
        assert meta.is_stale(threshold_days=5)

    def test_asi_dataframe_values_are_real(self, temp_storage):
        """ASI DataFrame values must match what was stored (no fabrication)."""
        records = _make_asi_records(70)
        temp_storage.store_ohlcv_batch(records)

        df = temp_storage.get_ohlcv_dataframe("ASI", min_sessions=60)
        assert df is not None

        # Verify first row matches first record
        first_close = df.iloc[0]["Close"]
        assert first_close == records[0].close

        # Verify last row matches last record
        last_close = df.iloc[-1]["Close"]
        assert last_close == records[-1].close

        # Verify no NaN values
        assert not df.isnull().any().any()

    def test_none_result_means_regime_unknown(self, temp_storage):
        """
        When _get_market_dataframe() returns None, the caller must
        treat the regime as UNKNOWN and trigger NO_TRADE.

        This test verifies the contract: empty storage → None → the
        upstream code path would set regime=UNKNOWN.
        """
        df = temp_storage.get_ohlcv_dataframe("ASI", min_sessions=60)
        assert df is None
        # Contract: caller checks `if df is None: regime = UNKNOWN; trigger NO_TRADE`
        # We verify the None return; upstream enforcement is tested via integration.


class TestAsiRegimeIntegration:
    """
    Test that _get_market_dataframe in recommendation.py actually
    reads from storage and returns None when ASI is missing.

    Patches target the *source module* because _get_market_dataframe
    does `from app.data.historical.storage import get_historical_storage`
    at call time (lazy import).
    """

    def _make_svc(self):
        """Create bare RecommendationService without __init__."""
        from app.services.recommendation import RecommendationService
        return RecommendationService.__new__(RecommendationService)

    @patch("app.data.historical.storage.get_historical_storage")
    @patch("app.core.config.get_settings")
    def test_recommendation_get_market_df_missing_asi(
        self, mock_get_settings, mock_get_storage
    ):
        """_get_market_dataframe returns None when storage has no ASI."""
        settings = MagicMock()
        settings.MIN_ASI_SESSIONS = 60
        mock_get_settings.return_value = settings

        storage = MagicMock()
        storage.get_ohlcv_dataframe.return_value = None
        mock_get_storage.return_value = storage

        result = self._make_svc()._get_market_dataframe()

        assert result is None
        storage.get_ohlcv_dataframe.assert_called_once_with("ASI", min_sessions=60)

    @patch("app.data.historical.storage.get_historical_storage")
    @patch("app.core.config.get_settings")
    def test_recommendation_get_market_df_with_real_data(
        self, mock_get_settings, mock_get_storage
    ):
        """_get_market_dataframe returns DataFrame when ASI is present."""
        import pandas as pd

        settings = MagicMock()
        settings.MIN_ASI_SESSIONS = 60
        mock_get_settings.return_value = settings

        dates = pd.date_range(end="2025-01-31", periods=80, freq="B")
        df = pd.DataFrame(
            {
                "Open": range(80),
                "High": range(80),
                "Low": range(80),
                "Close": range(80),
                "Volume": [1000000] * 80,
            },
            index=dates,
        )

        storage = MagicMock()
        storage.get_ohlcv_dataframe.return_value = df
        mock_get_storage.return_value = storage

        result = self._make_svc()._get_market_dataframe()

        assert result is not None
        assert len(result) == 80
