"""
Recommendation Service for NSE Trader.

Provides recommendation generation and management with:
- Data confidence scoring (suppression when quality insufficient)
- Probabilistic bias signals (not deterministic recommendations)
- Market regime integration (adjusts confidence based on regime compatibility)
- Signal lifecycle governance (TTL enforcement, NO_TRADE state)
"""
import logging
import numpy as np
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import asdict
import pandas as pd


def _sanitize_numpy(obj: Any) -> Any:
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _sanitize_numpy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_numpy(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

from app.core.recommendation_engine import (
    RecommendationEngine, Recommendation, TimeHorizon, RecommendationAction
)
from app.core.market_regime import MarketRegimeDetector, MarketRegime
from app.core.risk_calculator import RiskCalculator, RiskLevel
from app.core.explanation_generator import ExplanationGenerator, UserLevel
from app.services.market_data_v2 import get_market_data_service
from app.services.validation_service import get_validation_service
from app.services.confidence import (
    DataConfidenceScorer,
    ConfidenceScore,
    ConfidenceConfig,
    ConfidenceLevel,
    ReasonCode,
    get_confidence_scorer,
)
from app.services.probabilistic_bias import (
    BiasDirection,
    convert_action_to_bias_label,
    get_bias_calculator
)
from app.services.market_regime_engine import (
    MarketRegimeEngine,
    SessionRegime,
    SessionRegimeAnalysis,
    get_regime_engine
)
from app.services.signal_lifecycle import (
    SignalLifecycleManager,
    SignalState,
    NoTradeReason,
    LifecycleConfig,
    get_lifecycle_manager
)

logger = logging.getLogger(__name__)


class RecommendationService:
    """
    Service for generating and managing stock recommendations.
    
    Features:
    - Multi-horizon recommendations
    - Market regime awareness
    - Risk-adjusted signals
    - Explainable outputs
    - Caching for performance
    - Data confidence scoring with suppression
    """
    
    def __init__(self, confidence_config: Optional[ConfidenceConfig] = None):
        self.engine = RecommendationEngine()
        self.regime_detector = MarketRegimeDetector()
        self.risk_calculator = RiskCalculator()
        self.explanation_generator = ExplanationGenerator()
        self.market_data = get_market_data_service()
        
        # Initialize confidence scorer with optional custom config
        self.confidence_scorer = get_confidence_scorer(confidence_config)
        
        # Initialize validation service for multi-source verification
        self.validation_service = get_validation_service()
        
        # Initialize probabilistic bias calculator
        self.bias_calculator = get_bias_calculator()
        
        # Initialize market regime engine
        self.regime_engine = get_regime_engine()
        self._session_regime: Optional[SessionRegimeAnalysis] = None
        
        # Initialize signal lifecycle manager
        self.lifecycle_manager = get_lifecycle_manager()
        
        # Cache
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._cache_ttl = timedelta(minutes=15)
    
    async def get_recommendation(
        self,
        symbol: str,
        horizon: TimeHorizon = TimeHorizon.SWING,
        user_level: UserLevel = UserLevel.BEGINNER
    ) -> Optional[Dict[str, Any]]:
        """
        Get recommendation for a single stock.
        
        Includes data confidence scoring via multi-source validation.
        If confidence is below threshold, the recommendation is suppressed.
        """
        symbol = symbol.upper()
        cache_key = f"rec:{symbol}:{horizon.value}"
        
        # Check cache
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Get validated data
        try:
            validation_result = await self.validation_service.fetch_validated([symbol])
            validated_snapshot = validation_result.snapshots.get(symbol)
            
            if not validated_snapshot:
                logger.warning(f"Failed to get data for {symbol}")
                return None
                
            # Convert validation result to ConfidenceScore
            confidence_score = self._convert_validation_to_confidence(validated_snapshot)
            
            # Enrich snapshot to stock_data dict
            stock_data = self._enrich_snapshot_to_dict(validated_snapshot.snapshot)
            
        except Exception as e:
            logger.error(f"Error fetching validated data for {symbol}: {e}")
            # Fallback to direct market data fetch if validation fails
            stock_result = await self.market_data.get_stock_async(symbol)
            if not stock_result.success:
                return None
            stock_data = stock_result.data
            confidence_score = self._calculate_confidence_score(symbol, stock_data, stock_result)
        
        # Check if recommendation should be suppressed due to low confidence
        if confidence_score.is_suppressed:
            result = self._create_suppressed_recommendation(
                symbol=symbol,
                stock_data=stock_data,
                confidence_score=confidence_score,
                horizon=horizon
            )
            # Cache suppressed result (shorter TTL)
            self._set_cache(cache_key, result)
            return result
        
        # Build price DataFrame
        df = self._build_price_dataframe(stock_data)
        if df is None or len(df) < 20:
            logger.warning("Insufficient data for %s", symbol)
            return None
        
        # Get market data for regime detection
        market_df = self._get_market_dataframe()
        
        # Generate recommendation
        recommendation = self.engine.generate_recommendation(
            symbol=symbol,
            name=stock_data.get('name', symbol),
            price_data=df,
            horizon=horizon,
            market_data=market_df,
            fundamental_data=self._extract_fundamentals(stock_data)
        )
        
        if recommendation is None:
            return None
        
        # Convert to dict and add user-level explanation
        result = self._recommendation_to_dict(recommendation)
        
        # Add confidence score information to result
        result['confidence_score'] = confidence_score.overall_score
        result['data_confidence'] = confidence_score.to_dict()
        result['suppression_reason'] = None  # Not suppressed
        result['status'] = 'ACTIVE'
        
        # Calculate probabilistic bias signal
        signals_for_bias = [
            {"direction": s.direction, "strength": s.strength}
            for s in recommendation.signals
        ]
        bias_signal = self.bias_calculator.calculate_bias(
            internal_action=recommendation.action.value,
            signals=signals_for_bias,
            recommendation_confidence=recommendation.confidence,
            data_confidence_score=confidence_score.overall_score,
            is_suppressed=False
        )
        
        # Get session regime and apply adjustments
        session_regime = self._get_session_regime()
        if session_regime:
            bias_signal = self.bias_calculator.apply_regime_adjustment(
                bias_signal=bias_signal,
                regime_analysis=session_regime
            )
            result['market_regime'] = session_regime.to_dict()
        
        # Add probabilistic bias fields to result (external-facing)
        result['bias_direction'] = bias_signal.bias_direction.value
        result['bias_probability'] = bias_signal.bias_probability
        result['bias_label'] = convert_action_to_bias_label(recommendation.action.value)
        result['bias_signal'] = bias_signal.to_dict()
        result['probabilistic_reasoning'] = bias_signal.reasoning
        
        # Update status if regime suppressed the signal
        if bias_signal.is_suppressed and result['status'] == 'ACTIVE':
            result['status'] = 'SUPPRESSED'
            result['suppression_reason'] = bias_signal.suppression_reason
        
        # Evaluate signal lifecycle (TTL and NO_TRADE check)
        lifecycle_result = self.lifecycle_manager.evaluate_lifecycle(
            symbol=symbol,
            horizon=horizon.value,
            data_confidence=confidence_score.overall_score,
            indicator_agreement=bias_signal.indicator_agreement,
            regime=session_regime.regime.value if session_regime else "unknown",
            regime_confidence=session_regime.confidence if session_regime else 0.5,
            bias_probability=bias_signal.bias_probability or 0,
            is_suppressed=bias_signal.is_suppressed,
            suppression_reason=bias_signal.suppression_reason,
            generated_at=datetime.utcnow()
        )
        
        # Apply lifecycle state
        result['lifecycle_state'] = lifecycle_result.state.value
        result['expires_at'] = lifecycle_result.expires_at.isoformat()
        result['is_valid'] = lifecycle_result.is_valid
        
        # Handle NO_TRADE state
        if lifecycle_result.state == SignalState.NO_TRADE:
            result['status'] = 'NO_TRADE'
            result['bias_probability'] = None  # No probability for NO_TRADE
            result['no_trade_decision'] = lifecycle_result.no_trade_decision.to_dict()
            result['probabilistic_reasoning'] = lifecycle_result.reasoning
        elif lifecycle_result.state == SignalState.SUPPRESSED:
            result['status'] = 'SUPPRESSED'
        
        # Add lifecycle warnings
        if lifecycle_result.warnings:
            result['lifecycle_warnings'] = lifecycle_result.warnings
        
        # Customize explanation for user level with uncertainty-aware language
        self.explanation_generator.user_level = user_level
        result['user_explanation'] = self._generate_uncertainty_aware_explanation(
            recommendation=recommendation,
            bias_signal=bias_signal,
            user_level=user_level
        )
        
        # Cache result
        self._set_cache(cache_key, result)
        
        return result
    
    async def _generate_recommendation_from_data(
        self,
        stock_data: Dict[str, Any],
        horizon: TimeHorizon = TimeHorizon.SWING
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a recommendation from already-fetched stock data.
        
        Batch-friendly: skips validation service (data already fetched),
        uses a default confidence score, and builds price data from
        historical storage.
        """
        symbol = stock_data.get('symbol', '').upper()
        if not symbol:
            return None

        # Build price DataFrame from historical storage
        df = self._build_price_dataframe(stock_data)
        if df is None or len(df) < 20:
            return None

        # Extract trade_date (last date in the price DataFrame)
        trade_date = str(df.index[-1].date()) if hasattr(df.index[-1], 'date') else str(df.index[-1])

        # Get market data for regime detection
        market_df = self._get_market_dataframe()

        # Generate recommendation via engine
        recommendation = self.engine.generate_recommendation(
            symbol=symbol,
            name=stock_data.get('name', symbol),
            price_data=df,
            horizon=horizon,
            market_data=market_df,
            fundamental_data=self._extract_fundamentals(stock_data)
        )

        if recommendation is None:
            return None

        # Convert to dict
        result = self._recommendation_to_dict(recommendation)

        # Default confidence score (no multi-source validation in batch)
        result['confidence_score'] = 0.8
        result['suppression_reason'] = None
        result['status'] = 'ACTIVE'
        result['trade_date'] = trade_date
        result['price_source'] = 'historical_ohlcv'

        # Staleness warning: flag if price data is >2 trading days old
        from datetime import date as date_type, timedelta
        try:
            last_date = date_type.fromisoformat(trade_date)
            days_old = (date_type.today() - last_date).days
            if days_old > 3:  # >3 calendar days ≈ >2 trading days
                result.setdefault('risk_warnings', []).append(
                    f"Price data is {days_old} days old (as of {trade_date})"
                )
                result['price_stale'] = True
            else:
                result['price_stale'] = False
        except (ValueError, TypeError):
            result['price_stale'] = None

        # Calculate probabilistic bias signal
        signals_for_bias = [
            {"direction": s.direction, "strength": s.strength}
            for s in recommendation.signals
        ]
        bias_signal = self.bias_calculator.calculate_bias(
            internal_action=recommendation.action.value,
            signals=signals_for_bias,
            recommendation_confidence=recommendation.confidence,
            data_confidence_score=0.8,
            is_suppressed=False
        )

        # Get session regime and apply adjustments
        session_regime = self._get_session_regime()
        if session_regime:
            bias_signal = self.bias_calculator.apply_regime_adjustment(
                bias_signal=bias_signal,
                regime_analysis=session_regime
            )
            result['market_regime'] = session_regime.to_dict()

        # Add probabilistic bias fields
        result['bias_direction'] = bias_signal.bias_direction.value
        result['bias_probability'] = bias_signal.bias_probability
        result['bias_label'] = convert_action_to_bias_label(recommendation.action.value)
        result['bias_signal'] = bias_signal.to_dict()
        result['probabilistic_reasoning'] = bias_signal.reasoning

        # Track signal for paper trading performance evaluation
        try:
            from app.services.signal_history import get_signal_history_store
            store = get_signal_history_store()
            regime_name = session_regime.regime.value if session_regime else "unknown"
            regime_conf = session_regime.confidence if session_regime else 0.5
            store.store_signal(
                symbol=symbol,
                bias_direction=bias_signal.bias_direction.value,
                bias_probability=bias_signal.bias_probability or 50,
                regime=regime_name,
                regime_confidence=regime_conf,
                data_confidence_score=0.8,
                price_at_signal=recommendation.current_price,
                horizon=horizon.value,
                indicator_agreement=bias_signal.indicator_agreement,
            )
        except Exception as e:
            logger.debug("Signal tracking skipped for %s: %s", symbol, e)

        return _sanitize_numpy(result)

    async def get_top_recommendations(
        self,
        horizon: TimeHorizon = TimeHorizon.SWING,
        action_filter: Optional[str] = None,
        sector_filter: Optional[str] = None,
        min_liquidity: str = "medium",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top recommendations across all stocks.
        
        Optimisation: only fetch live prices for symbols that have
        historical OHLCV data, skipping the slow network round-trip
        for symbols that would be rejected by _build_price_dataframe.
        """
        from app.data.historical.storage import get_historical_storage
        from app.core.config import get_settings

        settings = get_settings()
        storage = get_historical_storage()

        # Pre-filter: only symbols with enough historical data
        all_metadata = storage.get_all_metadata()
        symbols_with_history = {
            m.symbol for m in all_metadata
            if m.total_sessions >= settings.MIN_OHLCV_SESSIONS
            and not m.is_stale(settings.OHLCV_STALENESS_DAYS)
        }
        if not symbols_with_history:
            logger.warning("No symbols with sufficient historical data")
            return []

        # Build stock dicts from registry (NO live fetch — the engine uses
        # historical DB data, live prices only add latency here)
        eligible_symbols = list(symbols_with_history - {"ASI"})
        stocks = []
        for symbol in eligible_symbols:
            registry_info = self.market_data.registry.get_stock(symbol)
            if registry_info:
                stocks.append({**registry_info, 'symbol': symbol})
            else:
                stocks.append({'symbol': symbol, 'name': symbol, 'liquidity_tier': 'low'})

        # Filter by sector if needed
        if sector_filter:
             stocks = [s for s in stocks if s.get('sector') == sector_filter]

        # Filter by liquidity
        liquidity_order = ['high', 'medium', 'low', 'very_low']
        min_index = liquidity_order.index(min_liquidity) if min_liquidity in liquidity_order else 2
        stocks = [
            s for s in stocks
            if liquidity_order.index(s.get('liquidity_tier', 'low')) <= min_index
        ]
        
        stocks_lookup = {s['symbol']: s for s in stocks}
        
        # Generate recommendations using already-fetched data
        recommendations = []
        for stock in stocks:
            try:
                rec = await self._generate_recommendation_from_data(
                    stock_data=stock,
                    horizon=horizon
                )
                if rec:
                    # Apply action filter
                    if action_filter and rec['action'] != action_filter:
                        continue
                    recommendations.append(rec)
            except Exception as e:
                logger.warning(f"Error generating rec for {stock['symbol']}: {e}")
                continue
        
        # Sort by confidence
        recommendations.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        return recommendations[:limit]

    async def get_buy_recommendations(
        self,
        horizon: TimeHorizon = TimeHorizon.SWING,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top buy recommendations."""
        recs = await self.get_top_recommendations(
            horizon=horizon,
            action_filter=None,
            min_liquidity="medium",
            limit=50
        )
        
        # Filter for buys only
        buys = [
            r for r in recs
            if r['action'] in ['STRONG_BUY', 'BUY']
        ]
        
        return buys[:limit]
    
    async def get_sell_recommendations(
        self,
        horizon: TimeHorizon = TimeHorizon.SWING,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top sell recommendations."""
        recs = await self.get_top_recommendations(
            horizon=horizon,
            action_filter=None,
            min_liquidity="low",
            limit=50
        )
        
        # Filter for sells only
        sells = [
            r for r in recs
            if r['action'] in ['STRONG_SELL', 'SELL']
        ]
        
        return sells[:limit]
    
    def get_market_regime(self) -> Dict[str, Any]:
        """Get current market regime analysis."""
        cache_key = "market_regime"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        market_df = self._get_market_dataframe()
        if market_df is None:
            return {
                'regime': 'unknown',
                'confidence': 0,
                'error': 'Insufficient market data'
            }
        
        # Get breadth data
        summary_result = self.market_data.get_market_summary()
        breadth_data = None
        if summary_result.success:
            breadth = summary_result.data.get('breadth', {})
            breadth_data = {
                'advancing': breadth.get('advancing', 0),
                'declining': breadth.get('declining', 0),
                'unchanged': breadth.get('unchanged', 0)
            }
        
        # Detect regime
        regime_analysis = self.regime_detector.detect(market_df, breadth_data)
        
        result = {
            'regime': regime_analysis.regime.value,
            'trend': regime_analysis.trend.value,
            'confidence': regime_analysis.confidence,
            'duration_days': regime_analysis.duration_days,
            'recommended_strategy': regime_analysis.recommended_strategy,
            'position_size_modifier': regime_analysis.position_size_modifier,
            'risk_adjustment': regime_analysis.risk_adjustment,
            'sectors_to_favor': regime_analysis.sectors_to_favor,
            'sectors_to_avoid': regime_analysis.sectors_to_avoid,
            'warnings': regime_analysis.warnings,
            'metrics': {
                'asi_vs_sma_50': regime_analysis.asi_vs_sma_50,
                'asi_vs_sma_200': regime_analysis.asi_vs_sma_200,
                'volatility_percentile': regime_analysis.volatility_percentile,
                'breadth_ratio': regime_analysis.breadth_ratio
            }
        }
        
        self._set_cache(cache_key, result)
        return result
    
    def _calculate_confidence_score(
        self,
        symbol: str,
        stock_data: Dict[str, Any],
        market_data_result: Any
    ) -> ConfidenceScore:
        """
        Calculate confidence score for stock data from market data result.
        
        Builds source data list from the market data result and stock data,
        then delegates to the confidence scorer.
        
        Args:
            symbol: Stock symbol
            stock_data: Stock data dictionary
            market_data_result: MarketDataResult from market data service
        
        Returns:
            ConfidenceScore with suppression decision
        """
        # Build source data list from available information
        source_data = []
        
        # Primary source from market data result
        primary_source = {
            "source": market_data_result.source if market_data_result else "unknown",
            "price": stock_data.get("price", 0),
            "volume": stock_data.get("volume", 0),
            "timestamp": stock_data.get("timestamp", datetime.utcnow().isoformat())
        }
        source_data.append(primary_source)
        
        # Check for validation/discrepancy data indicating multiple sources
        if "discrepancies" in stock_data:
            for disc in stock_data["discrepancies"]:
                if isinstance(disc, dict) and "values" in disc:
                    for src_name, val in disc["values"].items():
                        if src_name != primary_source["source"]:
                            source_data.append({
                                "source": src_name,
                                "price": val if disc.get("field") == "price" else primary_source["price"],
                                "volume": val if disc.get("field") == "volume" else primary_source["volume"],
                                "timestamp": primary_source["timestamp"]
                            })
        
        # Check if circuit breaker might be active (from validation_status)
        circuit_breaker_active = stock_data.get("validation_status") == "circuit_breaker"
        
        return self.confidence_scorer.calculate_confidence(
            symbol=symbol,
            source_data=source_data,
            circuit_breaker_active=circuit_breaker_active
        )
    
    def _create_suppressed_recommendation(
        self,
        symbol: str,
        stock_data: Dict[str, Any],
        confidence_score: ConfidenceScore,
        horizon: TimeHorizon
    ) -> Dict[str, Any]:
        """
        Create a suppressed recommendation response when data confidence is insufficient.
        
        Returns a recommendation dict with status="SUPPRESSED" and no actionable signals.
        
        Args:
            symbol: Stock symbol
            stock_data: Stock data dictionary
            confidence_score: The calculated confidence score
            horizon: Investment time horizon
        
        Returns:
            Dictionary with suppressed recommendation data
        """
        return {
            "symbol": symbol,
            "name": stock_data.get("name", symbol),
            "action": "HOLD",  # Default to HOLD when suppressed
            "horizon": horizon.value,
            "confidence": 0.0,  # No confidence in recommendation
            "current_price": stock_data.get("price", 0),
            "primary_reason": "Recommendation suppressed due to insufficient data quality",
            "supporting_reasons": [
                reason.value for reason in confidence_score.suppression_reasons
            ],
            "risk_warnings": [
                "Data quality insufficient for reliable recommendation",
                confidence_score.human_readable_reason or "Multiple data quality issues detected"
            ],
            "explanation": (
                f"The recommendation for {symbol} has been suppressed because "
                f"data confidence ({confidence_score.overall_score:.1%}) is below the required threshold. "
                f"Reason: {confidence_score.human_readable_reason}"
            ),
            "liquidity_score": stock_data.get("liquidity_tier", "unknown"),
            "liquidity_warning": None,
            "market_regime": "unknown",
            "risk_level": "unknown",
            "volatility": None,
            "entry_exit": None,
            "signals": [],
            "timestamp": datetime.utcnow().isoformat(),
            "valid_until": None,
            # Confidence scoring fields
            "status": "SUPPRESSED",
            "confidence_score": confidence_score.overall_score,
            "data_confidence": confidence_score.to_dict(),
            "suppression_reason": confidence_score.human_readable_reason,
            # Probabilistic bias fields - NO probability for suppressed signals
            "bias_direction": BiasDirection.NEUTRAL.value,
            "bias_probability": None,  # Never include probability when suppressed
            "bias_label": "Neutral Bias",
            "bias_signal": {
                "bias_direction": BiasDirection.NEUTRAL.value,
                "is_suppressed": True,
                "suppression_reason": confidence_score.human_readable_reason,
                "reasoning": (
                    "Signal analysis is currently suppressed due to insufficient data quality. "
                    f"Reason: {confidence_score.human_readable_reason}"
                )
            },
            "probabilistic_reasoning": (
                "Unable to compute directional bias due to insufficient data quality. "
                "No probability assessment is available when data confidence is below threshold."
            ),
            "user_explanation": (
                f"We cannot provide a reliable directional bias for {symbol} at this time. "
                f"The data quality score is {confidence_score.overall_score:.0%}, which is below our "
                f"minimum threshold for generating probabilistic signals. "
                f"This is typically caused by: {confidence_score.human_readable_reason}. "
                f"Please check back later when more reliable data is available."
            )
        }
    
    def _build_price_dataframe(self, stock_data: Dict) -> Optional[pd.DataFrame]:
        """
        Build price DataFrame from REAL historical OHLCV storage.

        Hard governance:
        - Returns None if symbol has < MIN_OHLCV_SESSIONS sessions.
        - Returns None if data is stale (> OHLCV_STALENESS_DAYS).
        - NEVER fabricates data. Missing data → None → NO_TRADE upstream.
        """
        from app.data.historical.storage import get_historical_storage
        from app.core.config import get_settings

        symbol = stock_data.get("symbol", "").upper()
        if not symbol:
            logger.warning("_build_price_dataframe called without symbol")
            return None

        settings = get_settings()
        storage = get_historical_storage()

        # Check metadata first (fast path)
        metadata = storage.get_metadata(symbol)
        if metadata is None:
            logger.warning(
                "NO_TRADE[%s]: No historical data — symbol never ingested", symbol
            )
            return None

        if metadata.total_sessions < settings.MIN_OHLCV_SESSIONS:
            logger.warning(
                "NO_TRADE[%s]: Insufficient history — %d sessions (need %d)",
                symbol, metadata.total_sessions, settings.MIN_OHLCV_SESSIONS,
            )
            return None

        if metadata.is_stale(settings.OHLCV_STALENESS_DAYS):
            reason = metadata.get_stale_reason(settings.OHLCV_STALENESS_DAYS)
            logger.warning("NO_TRADE[%s]: Stale data — %s", symbol, reason)
            return None

        # Fetch real OHLCV as DataFrame
        try:
            df = storage.get_ohlcv_dataframe(
                symbol, min_sessions=settings.MIN_OHLCV_SESSIONS
            )
            if df is None or df.empty:
                logger.warning(
                    "NO_TRADE[%s]: Storage returned empty DataFrame", symbol
                )
                return None

            logger.info(
                "Real OHLCV loaded for %s: %d sessions [%s → %s]",
                symbol, len(df), df.index[0].date(), df.index[-1].date(),
            )
            return df

        except Exception as e:
            logger.error("Error loading OHLCV for %s: %s", symbol, e)
            return None

    def _get_market_dataframe(self) -> Optional[pd.DataFrame]:
        """
        Get market (ASI) DataFrame from REAL historical storage.

        Fail-safe: returns None if ASI data is missing or insufficient.
        Callers must treat None as regime=UNKNOWN → NO_TRADE.
        """
        from app.data.historical.storage import get_historical_storage
        from app.core.config import get_settings

        settings = get_settings()
        storage = get_historical_storage()

        try:
            df = storage.get_ohlcv_dataframe(
                "ASI", min_sessions=settings.MIN_ASI_SESSIONS
            )
            if df is None or df.empty:
                logger.warning(
                    "NO_TRADE[ASI]: Insufficient ASI history (need %d sessions)",
                    settings.MIN_ASI_SESSIONS,
                )
                return None

            logger.info(
                "Real ASI loaded: %d sessions [%s → %s]",
                len(df), df.index[0].date(), df.index[-1].date(),
            )
            return df

        except Exception as e:
            logger.error("Error loading ASI data: %s", e)
            return None
    
    def _extract_fundamentals(self, stock_data: Dict) -> Dict[str, Any]:
        """Extract fundamental data from stock data."""
        return {
            'pe_ratio': stock_data.get('pe_ratio'),
            'eps': stock_data.get('eps'),
            'dividend_yield': stock_data.get('dividend_yield'),
            'market_cap': stock_data.get('market_cap')
        }
    
    def _get_session_regime(self) -> Optional[SessionRegimeAnalysis]:
        """
        Get the current session's market regime classification.
        
        Runs once per session and caches the result.
        Uses ASI price and volume data for classification.
        
        Returns:
            SessionRegimeAnalysis or None if insufficient data
        """
        # Return cached regime if available
        if self._session_regime is not None:
            return self._session_regime
        
        try:
            # Get market dataframe for regime classification
            market_df = self._get_market_dataframe()
            if market_df is None or len(market_df) < 60:
                logger.warning("Insufficient market data for regime classification")
                return None
            
            # Extract prices and volumes for regime engine
            asi_prices = market_df['Close'].tolist()
            asi_volumes = market_df['Volume'].tolist()
            current_volume = asi_volumes[-1] if asi_volumes else None
            
            # Classify session regime
            self._session_regime = self.regime_engine.classify_session(
                asi_prices=asi_prices,
                asi_volumes=asi_volumes,
                current_volume=current_volume
            )
            
            logger.info(
                "Session regime classified: %s (confidence: %.1f%%)",
                self._session_regime.regime.value,
                self._session_regime.confidence * 100
            )
            
            return self._session_regime
            
        except Exception as e:
            logger.warning("Failed to classify market regime: %s", e)
            return None
    
    def _convert_validation_to_confidence(self, validated_snapshot: Any) -> ConfidenceScore:
        """Convert ValidatedSnapshot to ConfidenceScore."""
        # Determine sources
        sources_used = [validated_snapshot.snapshot.source.value]
        primary_source = validated_snapshot.snapshot.source.value
        secondary_source = None
        
        if validated_snapshot.validation and validated_snapshot.validation.secondary_price:
            sources_used.append("kwayisi")
            secondary_source = "kwayisi"

        is_suppressed = validated_snapshot.confidence_score < 0.75
            
        return ConfidenceScore(
            symbol=validated_snapshot.snapshot.symbol,
            overall_score=validated_snapshot.confidence_score,
            confidence_level=ConfidenceLevel.SUPPRESSED if is_suppressed else ConfidenceLevel.HIGH,
            price_agreement_score=1.0 if validated_snapshot.is_validated else 0.5,
            volume_agreement_score=0.8,
            freshness_score=0.9,
            source_availability_score=1.0 if len(sources_used) > 1 else 0.5,
            is_suppressed=is_suppressed,
            reason_codes=[ReasonCode.LOW_OVERALL_CONFIDENCE] if is_suppressed else [],
            human_readable_reason="Insufficient data confidence" if is_suppressed else None,
            sources_used=sources_used,
            primary_source=primary_source,
            secondary_source=secondary_source,
            price_variance_percent=validated_snapshot.validation.price_difference_percent if validated_snapshot.validation and validated_snapshot.validation.price_difference_percent is not None else 0.0,
            volume_variance_percent=0.0,
            data_age_seconds=0.0,
        )

    def _enrich_snapshot_to_dict(self, snapshot: Any) -> Dict[str, Any]:
        """Enrich price snapshot with registry data."""
        registry_info = self.market_data.registry.get_stock(snapshot.symbol) or {}
        
        enriched = snapshot.to_dict()
        enriched['name'] = registry_info.get('name', snapshot.symbol)
        enriched['sector'] = registry_info.get('sector', {})
        if hasattr(enriched['sector'], 'value'):
            enriched['sector'] = enriched['sector'].value
        enriched['liquidity_tier'] = registry_info.get('liquidity_tier', 'unknown')
        enriched['market_cap_billions'] = registry_info.get('market_cap_billions')
        enriched['shares_outstanding'] = registry_info.get('shares_outstanding')
        enriched['is_active'] = registry_info.get('is_active', True)
        
        # Calculate market cap if not present
        if enriched.get('market_cap_billions') and not enriched.get('market_cap'):
            enriched['market_cap'] = enriched['market_cap_billions'] * 1e9
            
        return enriched

    def _generate_uncertainty_aware_explanation(
        self,
        recommendation: Recommendation,
        bias_signal,
        user_level: UserLevel
    ) -> str:
        """
        Generate user explanation with uncertainty-aware language.
        
        Replaces deterministic language like "strong buy" with probabilistic
        language like "suggests bullish bias".
        
        Args:
            recommendation: The recommendation object
            bias_signal: Calculated bias signal
            user_level: User experience level
        
        Returns:
            Uncertainty-aware explanation string
        """
        symbol = recommendation.symbol
        bias_dir = bias_signal.bias_direction.value
        prob = bias_signal.bias_probability
        
        # Probability-based confidence descriptor
        if prob >= 80:
            confidence_text = "high confidence"
            verb = "strongly suggests"
        elif prob >= 65:
            confidence_text = "moderate confidence"
            verb = "suggests"
        elif prob >= 50:
            confidence_text = "modest confidence"
            verb = "leans toward"
        else:
            confidence_text = "low confidence"
            verb = "shows slight indication of"
        
        # Bias direction text
        direction_text = {
            "bullish": "bullish bias with potential upside",
            "neutral": "neutral positioning with no clear directional edge",
            "bearish": "bearish bias with potential downside"
        }.get(bias_dir, "neutral stance")
        
        # Build explanation based on user level
        if user_level == UserLevel.BEGINNER:
            explanation = (
                f"Our analysis of {symbol} {verb} a {direction_text}. "
                f"The probability assessment is {prob}% ({confidence_text}). "
                f"This means the technical and fundamental indicators lean "
                f"{'positively' if bias_dir == 'bullish' else 'negatively' if bias_dir == 'bearish' else 'neither strongly positive nor negative'}. "
                f"Remember: This is not financial advice. Market conditions can change rapidly."
            )
        elif user_level == UserLevel.INTERMEDIATE:
            explanation = (
                f"{symbol}: {verb.capitalize()} {direction_text}. "
                f"Probability: {prob}% | Agreement: {bias_signal.indicator_agreement:.0%} of indicators aligned. "
                f"Data confidence factor: {bias_signal.data_confidence_factor:.2f}. "
                f"Primary driver: {recommendation.primary_reason}"
            )
        else:  # ADVANCED
            explanation = (
                f"{symbol} | Bias: {bias_dir.upper()} @ {prob}% probability | "
                f"Indicator agreement: {bias_signal.indicator_agreement:.1%} | "
                f"Signal magnitude: {bias_signal.signal_magnitude:.2f} | "
                f"Confidence penalty: {1-bias_signal.data_confidence_factor:.1%} | "
                f"Regime: {recommendation.market_regime.value}"
            )
        
        return explanation
    
    def _recommendation_to_dict(self, rec: Recommendation) -> Dict[str, Any]:
        """Convert Recommendation to dict (numpy-safe)."""
        return _sanitize_numpy({
            'symbol': rec.symbol,
            'name': rec.name,
            'action': rec.action.value,
            'horizon': rec.horizon.value,
            'confidence': rec.confidence,
            'current_price': rec.current_price,
            'primary_reason': rec.primary_reason,
            'supporting_reasons': rec.supporting_reasons,
            'risk_warnings': rec.risk_warnings,
            'explanation': rec.explanation,
            'liquidity_score': rec.liquidity_score,
            'liquidity_warning': rec.liquidity_warning,
            'market_regime': rec.market_regime.value,
            'risk_level': rec.risk_metrics.risk_level.value,
            'volatility': rec.risk_metrics.volatility_20d,
            'entry_exit': {
                'entry_price': rec.entry_exit.entry_price,
                'stop_loss': rec.entry_exit.stop_loss,
                'target_1': rec.entry_exit.target_1,
                'risk_reward': rec.entry_exit.risk_reward_ratio
            } if rec.entry_exit else None,
            'signals': [
                {
                    'name': s.name,
                    'type': s.type,
                    'direction': s.direction,
                    'strength': s.strength,
                    'description': s.plain_english
                }
                for s in rec.signals[:5]
            ],
            'timestamp': rec.timestamp.isoformat(),
            'valid_until': rec.valid_until.isoformat() if rec.valid_until else None
        })
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get from cache if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.utcnow() - timestamp < self._cache_ttl:
                return value
            del self._cache[key]
        return None
    
    def _set_cache(self, key: str, value: Any):
        """Set cache value."""
        self._cache[key] = (value, datetime.utcnow())
    
    def clear_cache(self):
        """Clear recommendation cache."""
        self._cache.clear()
