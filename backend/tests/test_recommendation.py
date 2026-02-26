"""
Tests for RecommendationService.

Covers:
1. get_recommendation flow
2. Integration with ValidationService (data confidence)
3. Integration with RecommendationEngine (core logic)
4. Integration with SignalLifecycleManager (governance)
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from app.services.recommendation import RecommendationService
from app.core.recommendation_engine import (
    TimeHorizon, Recommendation, RecommendationAction, RiskMetrics, RiskLevel
)
from app.core.market_regime import MarketRegime
from app.core.explanation_generator import UserLevel
from app.services.data_confidence import (
    ValidationStatus, ConfidenceLevel, ValidationResult
)
from app.services.validation_service import (
    ValidationServiceResult, ValidatedSnapshot
)
from app.market_data.providers.base import PriceSnapshot, DataSource

@pytest.fixture
def mock_validation_service():
    service = AsyncMock()
    return service

@pytest.fixture
def mock_market_data_service():
    service = AsyncMock()
    # Mock the registry which is synchronous
    mock_registry = Mock()
    mock_registry.get_stock.return_value = {
        "name": "Guaranty Trust",
        "sector": "Financial Services",
        "liquidity_tier": "high",
        "market_cap_billions": 1000,
        "shares_outstanding": 29000000000,
        "is_active": True
    }
    service.registry = mock_registry
    return service

@pytest.fixture
def mock_engine():
    engine = Mock()
    return engine

@pytest.fixture
def mock_bias_calculator():
    calc = Mock()
    return calc

@pytest.fixture
def mock_lifecycle_manager():
    manager = Mock()
    return manager

@pytest.fixture
def mock_explanation_generator():
    gen = Mock()
    gen.generate.return_value = "Test explanation"
    return gen

@pytest.fixture
def recommendation_service(
    mock_validation_service, 
    mock_market_data_service,
    mock_engine,
    mock_bias_calculator,
    mock_lifecycle_manager,
    mock_explanation_generator
):
    # Patch dependencies
    with patch('app.services.recommendation.get_validation_service', return_value=mock_validation_service), \
         patch('app.services.recommendation.get_market_data_service', return_value=mock_market_data_service), \
         patch('app.services.recommendation.RecommendationEngine', return_value=mock_engine), \
         patch('app.services.recommendation.get_bias_calculator', return_value=mock_bias_calculator), \
         patch('app.services.recommendation.get_lifecycle_manager', return_value=mock_lifecycle_manager), \
         patch('app.services.recommendation.ExplanationGenerator', return_value=mock_explanation_generator):
        
        service = RecommendationService()
        
        # Force replace to be sure
        service.validation_service = mock_validation_service
        service.market_data = mock_market_data_service
        service.engine = mock_engine
        service.bias_calculator = mock_bias_calculator
        service.lifecycle_manager = mock_lifecycle_manager
        service.explanation_generator = mock_explanation_generator
        
        return service

@pytest.mark.asyncio
async def test_get_recommendation_success(recommendation_service, mock_validation_service, mock_engine, mock_bias_calculator, mock_lifecycle_manager):
    """Test successful recommendation generation."""
    symbol = "GTCO"
    
    # 1. Setup Validation Result
    snapshot = PriceSnapshot(
        symbol=symbol, price=50.0, open=49.0, high=51.0, low=49.0, close=50.0,
        change=1.0, change_percent=2.0, volume=1000000, value=50000000,
        timestamp=datetime.now(timezone.utc), source=DataSource.NGX_OFFICIAL
    )
    validation_res = ValidationResult(
        symbol=symbol, primary_price=50.0, secondary_price=50.0,
        status=ValidationStatus.VALIDATED, confidence_level=ConfidenceLevel.HIGH,
        confidence_score=0.95,
        price_difference_percent=0.0 # Explicitly set
    )
    validated_snapshot = ValidatedSnapshot(snapshot=snapshot, validation=validation_res)
    
    mock_validation_service.fetch_validated.return_value = ValidationServiceResult(
        snapshots={symbol: validated_snapshot},
        primary_count=1, secondary_count=1, validated_count=1, divergent_count=0
    )
    
    # 2. Setup Engine Result
    mock_rec = Recommendation(
        symbol=symbol, name="Guaranty Trust", action=RecommendationAction.BUY,
        horizon=TimeHorizon.SWING, confidence=80.0, current_price=50.0,
        signals=[], risk_metrics=RiskMetrics(
            symbol=symbol,
            risk_level=RiskLevel.MODERATE, volatility_20d=15.0, volatility_60d=15.0, volatility_percentile=50.0, current_drawdown=0.0, max_drawdown_90d=10.0, max_drawdown_1y=10.0, avg_drawdown_duration=5, sharpe_ratio=1.5, sortino_ratio=2.0, calmar_ratio=1.5, beta=1.0, correlation_asi=0.8, var_95=2.0, var_99=3.0, cvar_95=2.5, downside_deviation=1.0, downside_capture=90.0, upside_capture=110.0, risk_score=40.0, suggested_max_position_pct=10.0, warnings=[]
        ),
        entry_exit=None, primary_reason="Strong momentum", supporting_reasons=[],
        risk_warnings=[], explanation="Good buy", liquidity_score=0.8,
        liquidity_warning=None, corporate_action_alert=None, sector_context=None,
        market_regime=MarketRegime.BULL, regime_adjustment="None"
    )
    mock_engine.generate_recommendation.return_value = mock_rec
    
    # 3. Setup Bias Result (must be shared between calculate_bias and apply_regime_adjustment)
    bias_result = Mock(
        direction="bullish", probability=75, label="Bullish Bias",
        agreement=0.8, magnitude=0.7, reasoning="Bullish signals",
        is_suppressed=False, suppression_reason=None,
        bias_direction=Mock(value="bullish"), bias_probability=75,
        indicator_agreement=0.8, signal_magnitude=0.7, data_confidence_factor=1.0,
        to_dict=lambda: {}
    )
    mock_bias_calculator.calculate_bias.return_value = bias_result
    mock_bias_calculator.apply_regime_adjustment.return_value = bias_result
    
    # 4. Setup Lifecycle Result
    mock_lifecycle_manager.evaluate_lifecycle.return_value = Mock(
        state=Mock(value="active"), is_active=True, expires_at=datetime.now(timezone.utc),
        is_valid=True, warnings=[], no_trade_decision=None
    )
    
    # Execute
    result = await recommendation_service.get_recommendation(
        symbol=symbol,
        horizon=TimeHorizon.SWING,
        user_level=UserLevel.BEGINNER
    )
    
    # Verify
    assert result is not None
    assert result["symbol"] == symbol
    assert result["status"] == "ACTIVE"
    assert result["confidence_score"] >= 0.9  # From validation
    assert result["bias_direction"] == "bullish"
    assert "ngx_official" in result["data_confidence"]["primary_source"].lower()

@pytest.mark.asyncio
async def test_get_recommendation_suppressed(recommendation_service, mock_validation_service):
    """Test recommendation suppression due to low data confidence."""
    symbol = "UNSTABLE"
    
    # 1. Setup Validation Result with LOW confidence
    snapshot = PriceSnapshot(
        symbol=symbol, price=50.0, open=49.0, high=51.0, low=49.0, close=50.0,
        change=1.0, change_percent=2.0, volume=1000000, value=50000000,
        timestamp=datetime.now(timezone.utc), source=DataSource.NGX_OFFICIAL
    )
    validation_res = ValidationResult(
        symbol=symbol, primary_price=50.0, secondary_price=60.0, # Divergent
        status=ValidationStatus.DIVERGENT, confidence_level=ConfidenceLevel.LOW,
        confidence_score=0.40, # Below threshold
        price_difference_percent=20.0 # Explicitly set float
    )
    validated_snapshot = ValidatedSnapshot(snapshot=snapshot, validation=validation_res)
    
    mock_validation_service.fetch_validated.return_value = ValidationServiceResult(
        snapshots={symbol: validated_snapshot},
        primary_count=1, secondary_count=1, validated_count=0, divergent_count=1
    )
    
    # Execute
    result = await recommendation_service.get_recommendation(symbol)
    
    # Verify
    assert result is not None
    assert result["status"] == "SUPPRESSED"
    assert result["confidence_score"] == 0.40
    assert result["bias_probability"] is None  # Should be None for suppressed

@pytest.mark.asyncio
async def test_get_recommendation_no_data(recommendation_service, mock_validation_service, mock_market_data_service):
    """Test handling when no data is returned."""
    symbol = "UNKNOWN"
    
    mock_validation_service.fetch_validated.return_value = ValidationServiceResult(
        snapshots={}, # Empty
        primary_count=0, secondary_count=0, validated_count=0, divergent_count=0
    )
    
    # Fallback market data also fails
    fallback_result = Mock()
    fallback_result.success = False
    mock_market_data_service.get_stock_async.return_value = fallback_result
    
    result = await recommendation_service.get_recommendation(symbol)
    
    assert result is None
