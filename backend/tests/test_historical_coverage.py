"""
Tests for Historical Coverage and Indicator Gating (Phase 2).

These tests verify:
1. HistoricalCoverage correctly assesses data availability
2. Indicator gating prevents computation with insufficient history
3. NO_TRADE is triggered when required indicators unavailable
4. API disclosure fields are present and correct
5. No indicators computed when sessions_available=0
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.historical_coverage import (
    HistoricalCoverage,
    HistoricalCoverageService,
    IndicatorCoverage,
    IndicatorType,
    INDICATOR_REQUIREMENTS,
    REQUIRED_FOR_RECOMMENDATION,
    MINIMUM_SESSIONS_FOR_RECOMMENDATION,
    get_historical_coverage_service,
    check_indicator_coverage,
    can_compute_indicator,
    get_insufficient_history_reason,
)
from app.services.signal_lifecycle import NoTradeReason


class TestIndicatorRequirements:
    """Test that indicator requirements are properly defined."""
    
    def test_rsi_requires_15_sessions(self):
        """RSI(14) requires 15 sessions (14 + 1)."""
        assert INDICATOR_REQUIREMENTS[IndicatorType.RSI_14] == 15
    
    def test_sma50_requires_50_sessions(self):
        """SMA(50) requires 50 sessions."""
        assert INDICATOR_REQUIREMENTS[IndicatorType.SMA_50] == 50
    
    def test_sma200_requires_200_sessions(self):
        """SMA(200) requires 200 sessions."""
        assert INDICATOR_REQUIREMENTS[IndicatorType.SMA_200] == 200
    
    def test_ema50_requires_50_sessions(self):
        """EMA(50) requires 50 sessions."""
        assert INDICATOR_REQUIREMENTS[IndicatorType.EMA_50] == 50
    
    def test_bollinger_requires_20_sessions(self):
        """Bollinger(20) requires 20 sessions."""
        assert INDICATOR_REQUIREMENTS[IndicatorType.BOLLINGER_20] == 20
    
    def test_macd_requires_26_sessions(self):
        """MACD requires 26 sessions (slow EMA)."""
        assert INDICATOR_REQUIREMENTS[IndicatorType.MACD] == 26
    
    def test_all_indicators_have_requirements(self):
        """All indicator types should have defined requirements."""
        for indicator in IndicatorType:
            assert indicator in INDICATOR_REQUIREMENTS, f"{indicator} missing requirement"
            assert INDICATOR_REQUIREMENTS[indicator] > 0, f"{indicator} has invalid requirement"


class TestHistoricalCoverageDataclass:
    """Test the HistoricalCoverage dataclass."""
    
    def test_coverage_with_zero_sessions(self):
        """Coverage with 0 sessions should mark as insufficient."""
        coverage = HistoricalCoverage(
            symbol="TEST",
            sessions_available=0,
            required_sessions=50,
            is_sufficient=False,
            missing_sessions=50,
            last_updated=datetime.utcnow(),
            source="NO_HISTORICAL_DATA"
        )
        
        assert coverage.sessions_available == 0
        assert coverage.is_sufficient is False
        assert coverage.missing_sessions == 50
    
    def test_coverage_can_compute_with_sufficient_history(self):
        """can_compute should return True when enough sessions."""
        coverage = HistoricalCoverage(
            symbol="TEST",
            sessions_available=60,
            required_sessions=50,
            is_sufficient=True,
            missing_sessions=0,
            last_updated=datetime.utcnow(),
            source="PARTIAL_HISTORY"
        )
        
        assert coverage.can_compute(IndicatorType.RSI_14) is True  # Needs 15
        assert coverage.can_compute(IndicatorType.SMA_50) is True  # Needs 50
        assert coverage.can_compute(IndicatorType.SMA_200) is False  # Needs 200
    
    def test_coverage_cannot_compute_with_zero_sessions(self):
        """No indicators should be computable with 0 sessions."""
        coverage = HistoricalCoverage(
            symbol="TEST",
            sessions_available=0,
            required_sessions=50,
            is_sufficient=False,
            missing_sessions=50,
            last_updated=datetime.utcnow(),
            source="NO_HISTORICAL_DATA"
        )
        
        # All indicators should be non-computable
        for indicator in IndicatorType:
            assert coverage.can_compute(indicator) is False
    
    def test_get_computable_indicators(self):
        """get_computable_indicators should return only computable ones."""
        coverage = HistoricalCoverage(
            symbol="TEST",
            sessions_available=30,
            required_sessions=50,
            is_sufficient=False,
            missing_sessions=20,
            last_updated=datetime.utcnow(),
            source="PARTIAL_HISTORY"
        )
        
        computable = coverage.get_computable_indicators()
        
        # Should include RSI (15), Bollinger (20), MACD (26), etc.
        assert IndicatorType.RSI_14 in computable
        assert IndicatorType.BOLLINGER_20 in computable
        assert IndicatorType.MACD in computable
        
        # Should NOT include SMA_50 (50) or SMA_200 (200)
        assert IndicatorType.SMA_50 not in computable
        assert IndicatorType.SMA_200 not in computable
    
    def test_get_missing_indicators(self):
        """get_missing_indicators should return non-computable ones."""
        coverage = HistoricalCoverage(
            symbol="TEST",
            sessions_available=30,
            required_sessions=50,
            is_sufficient=False,
            missing_sessions=20,
            last_updated=datetime.utcnow(),
            source="PARTIAL_HISTORY"
        )
        
        missing = coverage.get_missing_indicators()
        
        # Should include SMA_50 and SMA_200
        assert IndicatorType.SMA_50 in missing
        assert IndicatorType.SMA_200 in missing
        assert IndicatorType.EMA_50 in missing
    
    def test_has_required_for_recommendation(self):
        """Check if all required indicators can be computed."""
        # With 60 sessions - should have RSI, SMA_50, MACD, Bollinger
        coverage = HistoricalCoverage(
            symbol="TEST",
            sessions_available=60,
            required_sessions=50,
            is_sufficient=True,
            missing_sessions=0,
            last_updated=datetime.utcnow(),
            source="PARTIAL_HISTORY"
        )
        
        assert coverage.has_required_for_recommendation() is True
        
        # With 10 sessions - missing most required
        coverage_low = HistoricalCoverage(
            symbol="TEST",
            sessions_available=10,
            required_sessions=50,
            is_sufficient=False,
            missing_sessions=40,
            last_updated=datetime.utcnow(),
            source="PARTIAL_HISTORY"
        )
        
        assert coverage_low.has_required_for_recommendation() is False
    
    def test_to_dict_includes_all_fields(self):
        """to_dict should include all required API fields."""
        coverage = HistoricalCoverage(
            symbol="TEST",
            sessions_available=30,
            required_sessions=50,
            is_sufficient=False,
            missing_sessions=20,
            last_updated=datetime.utcnow(),
            source="PARTIAL_HISTORY",
            indicator_availability={"RSI_14": True, "SMA_50": False},
            indicator_requirements={"RSI_14": 15, "SMA_50": 50},
            warnings=["Test warning"]
        )
        
        result = coverage.to_dict()
        
        assert "symbol" in result
        assert "sessions_available" in result
        assert "required_sessions" in result
        assert "is_sufficient" in result
        assert "missing_sessions" in result
        assert "last_updated" in result
        assert "source" in result
        assert "indicator_availability" in result
        assert "indicator_requirements" in result
        assert "warnings" in result


class TestHistoricalCoverageService:
    """Test the HistoricalCoverageService."""
    
    def test_get_coverage_default_zero_sessions(self):
        """By default, symbols have 0 sessions available."""
        service = HistoricalCoverageService()
        coverage = service.get_coverage("UNKNOWN_SYMBOL")
        
        assert coverage.sessions_available == 0
        assert coverage.is_sufficient is False
        assert coverage.source == "NO_HISTORICAL_DATA"
    
    def test_get_coverage_includes_warnings(self):
        """Coverage should include warnings for insufficient history."""
        service = HistoricalCoverageService()
        coverage = service.get_coverage("TEST")
        
        assert len(coverage.warnings) > 0
        assert any("Historical" in w for w in coverage.warnings)
    
    def test_set_known_history(self):
        """Should be able to set known history for testing."""
        service = HistoricalCoverageService()
        
        # Set 100 sessions for TEST
        service.set_known_history("TEST", 100)
        coverage = service.get_coverage("TEST")
        
        assert coverage.sessions_available == 100
        assert coverage.is_sufficient is True
    
    def test_can_generate_recommendation_insufficient(self):
        """Should return False when history insufficient."""
        service = HistoricalCoverageService()
        
        can_generate, reason = service.can_generate_recommendation("UNKNOWN")
        
        assert can_generate is False
        assert "INSUFFICIENT_HISTORY" in reason
    
    def test_can_generate_recommendation_sufficient(self):
        """Should return True when history sufficient."""
        service = HistoricalCoverageService()
        service.set_known_history("TEST", 100)
        
        can_generate, reason = service.can_generate_recommendation("TEST")
        
        assert can_generate is True
    
    def test_get_indicator_coverage(self):
        """Should return detailed coverage for specific indicator."""
        service = HistoricalCoverageService()
        service.set_known_history("TEST", 30)
        
        # RSI should be available (needs 15)
        rsi_coverage = service.get_indicator_coverage("TEST", IndicatorType.RSI_14)
        assert rsi_coverage.is_available is True
        assert rsi_coverage.required_sessions == 15
        
        # SMA_50 should not be available (needs 50)
        sma_coverage = service.get_indicator_coverage("TEST", IndicatorType.SMA_50)
        assert sma_coverage.is_available is False
        assert sma_coverage.required_sessions == 50
        assert "Requires 50" in sma_coverage.reason
    
    def test_get_all_indicator_requirements(self):
        """Should return all indicator requirements."""
        service = HistoricalCoverageService()
        requirements = service.get_all_indicator_requirements()
        
        assert "RSI_14" in requirements
        assert "SMA_50" in requirements
        assert "SMA_200" in requirements
        assert requirements["RSI_14"] == 15
        assert requirements["SMA_50"] == 50


class TestNoTradeOnInsufficientHistory:
    """Test that NO_TRADE is triggered for insufficient history."""
    
    def test_no_trade_reason_exists(self):
        """INSUFFICIENT_HISTORY should be a valid NoTradeReason."""
        assert NoTradeReason.INSUFFICIENT_HISTORY == "insufficient_history"
    
    def test_coverage_service_returns_no_trade_reason(self):
        """Service should provide NO_TRADE-compatible reason."""
        service = HistoricalCoverageService()
        
        can_generate, reason = service.can_generate_recommendation("TEST")
        
        assert can_generate is False
        assert "INSUFFICIENT_HISTORY" in reason
        assert "sessions" in reason.lower()


class TestIndicatorGating:
    """Test that indicators are properly gated."""
    
    def test_gated_composite_with_zero_sessions(self):
        """GatedCompositeIndicator should gate all with 0 sessions."""
        from app.indicators.composite import GatedCompositeIndicator
        import pandas as pd
        
        # Create mock DataFrame
        df = pd.DataFrame({
            'Open': [100.0] * 10,
            'High': [101.0] * 10,
            'Low': [99.0] * 10,
            'Close': [100.5] * 10,
            'Volume': [1000] * 10,
        })
        
        indicator = GatedCompositeIndicator()
        
        # Mock the coverage service to return 0 sessions
        with patch.object(indicator, '_coverage_service') as mock_service:
            mock_coverage = HistoricalCoverage(
                symbol="TEST",
                sessions_available=0,
                required_sessions=50,
                is_sufficient=False,
                missing_sessions=50,
                last_updated=datetime.utcnow(),
                source="NO_HISTORICAL_DATA"
            )
            mock_service.get_coverage.return_value = mock_coverage
            
            result = indicator.calculate_gated(df, "TEST")
            
            assert result is not None
            assert result.is_sufficient_for_recommendation is False
            assert len(result.gated_indicators) > 0
            assert result.insufficient_history_reason is not None
            assert "INSUFFICIENT_HISTORY" in result.insufficient_history_reason
    
    def test_gated_composite_with_sufficient_sessions(self):
        """GatedCompositeIndicator should compute with sufficient sessions."""
        from app.indicators.composite import GatedCompositeIndicator
        import pandas as pd
        import numpy as np
        
        # Create more realistic DataFrame with 100 rows
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            'Open': 100 + np.random.randn(n).cumsum(),
            'High': 101 + np.random.randn(n).cumsum(),
            'Low': 99 + np.random.randn(n).cumsum(),
            'Close': 100.5 + np.random.randn(n).cumsum(),
            'Volume': np.random.randint(1000, 10000, n),
        })
        # Ensure High >= Open, Close, Low
        df['High'] = df[['Open', 'High', 'Low', 'Close']].max(axis=1)
        df['Low'] = df[['Open', 'High', 'Low', 'Close']].min(axis=1)
        
        indicator = GatedCompositeIndicator()
        
        # Mock coverage service to return 100 sessions
        with patch.object(indicator, '_coverage_service') as mock_service:
            mock_coverage = HistoricalCoverage(
                symbol="TEST",
                sessions_available=100,
                required_sessions=50,
                is_sufficient=True,
                missing_sessions=0,
                last_updated=datetime.utcnow(),
                source="PARTIAL_HISTORY"
            )
            mock_service.get_coverage.return_value = mock_coverage
            
            result = indicator.calculate_gated(df, "TEST")
            
            assert result is not None
            assert result.is_sufficient_for_recommendation is True
            assert len(result.computed_indicators) > 0
            # Some indicators should be computed
            assert "rsi" in result.computed_indicators or len(result.gated_indicators) < len(indicator.indicators)


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_check_indicator_coverage(self):
        """check_indicator_coverage should return HistoricalCoverage."""
        coverage = check_indicator_coverage("UNIQUE_TEST_SYMBOL_1")
        
        assert isinstance(coverage, HistoricalCoverage)
        assert coverage.symbol == "UNIQUE_TEST_SYMBOL_1"
    
    def test_can_compute_indicator(self):
        """can_compute_indicator should check specific indicator."""
        # With default (0 sessions), nothing should be computable
        # Use unique symbol to avoid singleton state from other tests
        assert can_compute_indicator("UNIQUE_TEST_SYMBOL_2", IndicatorType.RSI_14) is False
        assert can_compute_indicator("UNIQUE_TEST_SYMBOL_2", IndicatorType.SMA_50) is False
    
    def test_get_insufficient_history_reason(self):
        """Should return explanation for insufficient history."""
        reason = get_insufficient_history_reason("UNIQUE_TEST_SYMBOL_3")
        
        assert "Requires" in reason
        assert "sessions" in reason.lower()


class TestAPIDisclosureFields:
    """Test that API disclosure fields are present."""
    
    def test_historical_coverage_to_dict_has_disclosure(self):
        """HistoricalCoverage.to_dict should have all disclosure fields."""
        coverage = HistoricalCoverage(
            symbol="TEST",
            sessions_available=0,
            required_sessions=50,
            is_sufficient=False,
            missing_sessions=50,
            last_updated=datetime.utcnow(),
            source="NO_HISTORICAL_DATA",
            indicator_availability={"RSI_14": False},
            indicator_requirements={"RSI_14": 15},
            warnings=["Test"]
        )
        
        result = coverage.to_dict()
        
        # Required fields for API transparency
        assert "sessions_available" in result
        assert "required_sessions" in result
        assert "is_sufficient" in result
        assert "missing_sessions" in result
        assert "source" in result
        assert "indicator_availability" in result
        assert "indicator_requirements" in result
    
    def test_indicator_coverage_to_dict(self):
        """IndicatorCoverage.to_dict should have per-indicator details."""
        coverage = IndicatorCoverage(
            indicator_name="RSI_14",
            is_available=False,
            required_sessions=15,
            sessions_available=0,
            missing_sessions=15,
            reason="Requires 15 sessions; only 0 available"
        )
        
        result = coverage.to_dict()
        
        assert result["indicator_name"] == "RSI_14"
        assert result["is_available"] is False
        assert result["required_sessions"] == 15
        assert result["missing_sessions"] == 15
        assert "Requires" in result["reason"]


class TestMinimumSessionsConstant:
    """Test the minimum sessions constant."""
    
    def test_minimum_sessions_is_50(self):
        """Minimum sessions for recommendation should be 50."""
        assert MINIMUM_SESSIONS_FOR_RECOMMENDATION == 50
    
    def test_required_indicators_can_be_computed_at_minimum(self):
        """All required indicators should be computable at minimum sessions."""
        for indicator in REQUIRED_FOR_RECOMMENDATION:
            required = INDICATOR_REQUIREMENTS[indicator]
            assert required <= MINIMUM_SESSIONS_FOR_RECOMMENDATION, (
                f"{indicator} requires {required} sessions, "
                f"but minimum is {MINIMUM_SESSIONS_FOR_RECOMMENDATION}"
            )
