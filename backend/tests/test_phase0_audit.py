"""
Tests for Phase 0 Audit Changes - Data Integrity & Truthfulness.

These tests verify that the system is truthful-by-default:
1. Performance endpoints report readiness status (Phase 3 re-enabled)
2. Market breadth includes estimation disclosure
3. Regime confidence is rounded to 2 decimals
4. Simulated data is clearly flagged
5. Apt Securities provider is removed from chain
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi.testclient import TestClient


class TestPerformanceEndpointsReadiness:
    """Test that performance endpoints report proper readiness status.
    
    Phase 3 Update: Performance endpoints are now re-enabled and use real
    historical OHLCV data. They return readiness status instead of 501.
    """
    
    def test_performance_summary_returns_dict(self):
        """Performance summary should return a dict with status."""
        from app.api.v1.performance import get_performance_summary
        import asyncio
        
        response = asyncio.run(
            get_performance_summary(days=30)
        )
        
        assert isinstance(response, dict)
        assert "status" in response
    
    def test_performance_status_endpoint_returns_readiness(self):
        """Performance status endpoint should return readiness info."""
        from app.api.v1.performance import get_performance_status
        import asyncio
        
        response = asyncio.run(get_performance_status())
        
        # Phase 3: Now returns READY, PARTIALLY_READY, or NOT_READY
        assert response["status"] in ["READY", "PARTIALLY_READY", "NOT_READY"]
        # Should include symbol counts
        assert "symbols_total" in response or "reasons" in response
    
    def test_performance_response_includes_transparency(self):
        """Performance responses should include transparency fields."""
        from app.api.v1.performance import get_performance_summary
        import asyncio
        
        response = asyncio.run(
            get_performance_summary(days=30)
        )
        
        # Should have transparency section
        assert "transparency" in response
        assert "evaluated_signal_count" in response["transparency"]
        assert "unevaluated_signal_count" in response["transparency"]


class TestMarketBreadthDisclosure:
    """Test that market breadth includes proper estimation disclosure."""
    
    def test_market_breadth_dataclass_has_disclosure_fields(self):
        """MarketBreadth should have is_estimated, methodology, warning fields."""
        from app.services.ngnmarket_service import MarketBreadth
        
        breadth = MarketBreadth(
            estimated_advancers=50,
            estimated_decliners=40,
            estimated_unchanged=10,
            breadth_ratio=0.5555,
            market_sentiment="neutral",
            confidence=0.6
        )
        
        assert breadth.is_estimated == True
        assert "Heuristic" in breadth.methodology
        assert "NOT exchange-reported" in breadth.warning
    
    def test_market_breadth_to_dict_includes_disclosure(self):
        """MarketBreadth.to_dict() should include disclosure fields."""
        from app.services.ngnmarket_service import MarketBreadth
        
        breadth = MarketBreadth(
            estimated_advancers=50,
            estimated_decliners=40,
            estimated_unchanged=10,
            breadth_ratio=0.555555,
            market_sentiment="neutral",
            confidence=0.6666
        )
        
        result = breadth.to_dict()
        
        assert result["is_estimated"] == True
        assert "methodology" in result
        assert "warning" in result
        # Check precision limiting
        assert result["ratio"] == 0.5556  # Rounded to 4 decimals
        assert result["confidence"] == 0.67  # Rounded to 2 decimals
    
    def test_market_breadth_response_model_has_disclosure(self):
        """MarketBreadthResponse should have disclosure fields."""
        from app.api.v1.market import MarketBreadthResponse
        
        response = MarketBreadthResponse(
            success=True,
            data={"test": "data"}
        )
        
        assert response.is_estimated == True
        assert "Heuristic" in response.methodology
        assert "NOT exchange-reported" in response.warning
        assert response.source == "ngnmarket.com (derived)"


class TestRegimeConfidencePrecision:
    """Test that regime confidence is rounded to 2 decimals."""
    
    def test_regime_response_model_has_disclosure(self):
        """MarketRegimeResponse should have uses_estimated_inputs field."""
        from app.api.v1.market import MarketRegimeResponse
        
        response = MarketRegimeResponse(
            success=True,
            regime="trending",
            confidence=0.74,
            trend_direction="bullish",
            reasoning="Test reasoning",
            warnings=[]
        )
        
        assert response.uses_estimated_inputs == True
        assert "model-derived" in response.confidence_note


class TestSimulationDisclosure:
    """Test that simulated data is clearly flagged."""
    
    def test_price_snapshot_has_simulation_fields(self):
        """PriceSnapshot should have simulation disclosure fields."""
        from app.market_data.providers.base import PriceSnapshot, DataSource
        
        snapshot = PriceSnapshot(
            symbol="TEST",
            price=100.0,
            open=99.0,
            high=101.0,
            low=98.0,
            close=100.0,
            change=1.0,
            change_percent=1.0,
            volume=1000,
            value=100000.0,
            timestamp=datetime.now(timezone.utc),
            source=DataSource.SIMULATED,
            is_simulated=True,
            simulated_reason="Test reason",
            simulated_inputs={"market_cap": 100}
        )
        
        assert snapshot.is_simulated == True
        assert snapshot.simulated_reason == "Test reason"
        assert snapshot.simulated_inputs == {"market_cap": 100}
    
    def test_simulated_price_snapshot_to_dict_includes_warning(self):
        """Simulated PriceSnapshot.to_dict() should include warning."""
        from app.market_data.providers.base import PriceSnapshot, DataSource
        
        snapshot = PriceSnapshot(
            symbol="TEST",
            price=100.0,
            open=99.0,
            high=101.0,
            low=98.0,
            close=100.0,
            change=1.0,
            change_percent=1.0,
            volume=1000,
            value=100000.0,
            timestamp=datetime.now(timezone.utc),
            source=DataSource.SIMULATED,
            is_simulated=True,
            simulated_reason="Test reason",
            simulated_inputs={"market_cap": 100}
        )
        
        result = snapshot.to_dict()
        
        assert result["is_simulated"] == True
        assert result["data_source"] == "SIMULATED"
        assert "simulation_warning" in result
        assert "NOT real market data" in result["simulation_warning"]
    
    def test_real_price_snapshot_no_simulation_warning(self):
        """Real PriceSnapshot.to_dict() should not include simulation warning."""
        from app.market_data.providers.base import PriceSnapshot, DataSource
        
        snapshot = PriceSnapshot(
            symbol="TEST",
            price=100.0,
            open=99.0,
            high=101.0,
            low=98.0,
            close=100.0,
            change=1.0,
            change_percent=1.0,
            volume=1000,
            value=100000.0,
            timestamp=datetime.now(timezone.utc),
            source=DataSource.NGX_OFFICIAL,
            is_simulated=False
        )
        
        result = snapshot.to_dict()
        
        assert result["is_simulated"] == False
        assert "simulation_warning" not in result
        assert "data_source" not in result


class TestSimulatedProviderDisclosure:
    """Test that SimulatedProvider populates disclosure fields."""
    
    def test_simulated_provider_generates_disclosure(self):
        """SimulatedProvider should populate simulation disclosure fields."""
        from app.market_data.providers.simulated_provider import SimulatedProvider
        
        registry_data = {
            "TEST": {
                "market_cap_billions": 100,
                "shares_outstanding": 1_000_000_000,
                "liquidity_tier": "high"
            }
        }
        
        provider = SimulatedProvider(registry_data)
        snapshot = provider._generate_snapshot("TEST", registry_data["TEST"])
        
        assert snapshot.is_simulated == True
        assert snapshot.simulated_reason is not None
        assert "Real-time data sources unavailable" in snapshot.simulated_reason
        assert snapshot.simulated_inputs is not None
        assert "market_cap_billions" in snapshot.simulated_inputs
        assert "shares_outstanding" in snapshot.simulated_inputs


class TestProviderChainNoAptSecurities:
    """Test that Apt Securities provider is not in the chain."""
    
    def test_market_data_service_excludes_apt_securities(self):
        """MarketDataServiceV2 should not include Apt Securities provider."""
        from app.services.market_data_v2 import MarketDataServiceV2
        
        service = MarketDataServiceV2()
        
        # Check that _apt_provider attribute doesn't exist or is None
        assert not hasattr(service, '_apt_provider') or service._apt_provider is None
        
        # Check provider chain
        provider_names = [p.name for p in service._provider_chain._providers]
        assert "Apt Securities" not in provider_names
    
    def test_provider_chain_has_expected_providers(self):
        """Provider chain should have ngnmarket, NGX, and Simulated only."""
        from app.services.market_data_v2 import MarketDataServiceV2
        
        service = MarketDataServiceV2()
        provider_names = [p.name for p in service._provider_chain._providers]
        
        # Should have exactly 4 providers
        assert len(provider_names) == 4
        
        # Check expected providers exist
        assert any("ngnmarket" in name.lower() or "ngn" in name.lower() for name in provider_names)
        assert any("kwayisi" in name.lower() for name in provider_names)
        assert any("simulated" in name.lower() for name in provider_names)


class TestStockListResponseSimulationFields:
    """Test that StockListResponse has simulation disclosure fields."""
    
    def test_stock_list_response_has_simulation_fields(self):
        """StockListResponse should have contains_simulated and simulated_symbols."""
        from app.api.v1.stocks import StockListResponse
        
        response = StockListResponse(
            success=True,
            count=10,
            data=[],
            source="test",
            contains_simulated=True,
            simulated_symbols=["TEST1", "TEST2"]
        )
        
        assert response.contains_simulated == True
        assert response.simulated_symbols == ["TEST1", "TEST2"]
    
    def test_stock_list_response_defaults(self):
        """StockListResponse should default to no simulation."""
        from app.api.v1.stocks import StockListResponse
        
        response = StockListResponse(
            success=True,
            count=0,
            data=[],
            source="test"
        )
        
        assert response.contains_simulated == False
        assert response.simulated_symbols == []
