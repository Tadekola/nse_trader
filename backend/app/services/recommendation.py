"""
Recommendation Service for NSE Trader.

Provides recommendation generation and management.
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import asdict
import pandas as pd

from app.core.recommendation_engine import (
    RecommendationEngine, Recommendation, TimeHorizon, RecommendationAction
)
from app.core.market_regime import MarketRegimeDetector, MarketRegime
from app.core.risk_calculator import RiskCalculator, RiskLevel
from app.core.explanation_generator import ExplanationGenerator, UserLevel
from app.services.market_data_v2 import get_market_data_service

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
    """
    
    def __init__(self):
        self.engine = RecommendationEngine()
        self.regime_detector = MarketRegimeDetector()
        self.risk_calculator = RiskCalculator()
        self.explanation_generator = ExplanationGenerator()
        self.market_data = get_market_data_service()
        
        # Cache
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._cache_ttl = timedelta(minutes=15)
    
    def get_recommendation(
        self,
        symbol: str,
        horizon: TimeHorizon = TimeHorizon.SWING,
        user_level: UserLevel = UserLevel.BEGINNER
    ) -> Optional[Dict[str, Any]]:
        """
        Get recommendation for a single stock.
        
        Args:
            symbol: Stock symbol
            horizon: Investment time horizon
            user_level: User experience level for explanation customization
        
        Returns:
            Recommendation dict or None
        """
        symbol = symbol.upper()
        cache_key = f"rec:{symbol}:{horizon.value}"
        
        # Check cache
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Get stock data
        stock_result = self.market_data.get_stock(symbol)
        if not stock_result.success:
            logger.warning(f"Failed to get data for {symbol}")
            return None
        
        stock_data = stock_result.data
        
        # Build price DataFrame (would need historical data in production)
        # For now, create a minimal DataFrame from current data
        df = self._build_price_dataframe(stock_data)
        if df is None or len(df) < 20:
            logger.warning(f"Insufficient data for {symbol}")
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
        
        # Customize explanation for user level
        self.explanation_generator.user_level = user_level
        result['user_explanation'] = self.explanation_generator.explain_recommendation(
            action=recommendation.action.value,
            confidence=recommendation.confidence,
            primary_reason=recommendation.primary_reason,
            supporting_reasons=recommendation.supporting_reasons,
            risk_level=recommendation.risk_metrics.risk_level,
            liquidity_score=recommendation.liquidity_score,
            regime=recommendation.market_regime
        )
        
        # Cache result
        self._set_cache(cache_key, result)
        
        return result
    
    def get_top_recommendations(
        self,
        horizon: TimeHorizon = TimeHorizon.SWING,
        action_filter: Optional[str] = None,
        sector_filter: Optional[str] = None,
        min_liquidity: str = "medium",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top recommendations across all stocks.
        
        Args:
            horizon: Investment time horizon
            action_filter: Filter by action (BUY, SELL, etc.)
            sector_filter: Filter by sector
            min_liquidity: Minimum liquidity tier
            limit: Maximum number of recommendations
        
        Returns:
            List of recommendation dicts
        """
        # Get appropriate stock list based on liquidity
        if min_liquidity == "high":
            stocks_result = self.market_data.get_high_liquidity_stocks()
        elif sector_filter:
            stocks_result = self.market_data.get_stocks_by_sector(sector_filter)
        else:
            stocks_result = self.market_data.get_all_stocks()
        
        if not stocks_result.success:
            return []
        
        stocks = stocks_result.data
        
        # Filter by liquidity
        liquidity_order = ['high', 'medium', 'low', 'very_low']
        min_index = liquidity_order.index(min_liquidity) if min_liquidity in liquidity_order else 2
        stocks = [
            s for s in stocks
            if liquidity_order.index(s.get('liquidity_tier', 'low')) <= min_index
        ]
        
        # Build lookup dict for fast access (avoids re-fetching each stock)
        stocks_lookup = {s['symbol']: s for s in stocks}
        
        # Generate recommendations using already-fetched data
        recommendations = []
        for stock in stocks:
            try:
                rec = self._generate_recommendation_from_data(
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
    
    def _generate_recommendation_from_data(
        self,
        stock_data: Dict[str, Any],
        horizon: TimeHorizon = TimeHorizon.SWING,
        user_level: UserLevel = UserLevel.BEGINNER
    ) -> Optional[Dict[str, Any]]:
        """
        Generate recommendation from already-fetched stock data.
        Avoids redundant API calls by reusing data.
        """
        symbol = stock_data.get('symbol', '').upper()
        cache_key = f"rec:{symbol}:{horizon.value}"
        
        # Check cache first
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Build price DataFrame from existing data
        df = self._build_price_dataframe(stock_data)
        if df is None or len(df) < 20:
            return None
        
        # Get market data for regime detection (cached internally)
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
        
        # Customize explanation for user level
        self.explanation_generator.user_level = user_level
        result['user_explanation'] = self.explanation_generator.explain_recommendation(
            action=recommendation.action.value,
            confidence=recommendation.confidence,
            primary_reason=recommendation.primary_reason,
            supporting_reasons=recommendation.supporting_reasons,
            risk_level=recommendation.risk_metrics.risk_level,
            liquidity_score=recommendation.liquidity_score,
            regime=recommendation.market_regime
        )
        
        # Cache result
        self._set_cache(cache_key, result)
        
        return result
    
    def get_buy_recommendations(
        self,
        horizon: TimeHorizon = TimeHorizon.SWING,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top buy recommendations."""
        recs = self.get_top_recommendations(
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
    
    def get_sell_recommendations(
        self,
        horizon: TimeHorizon = TimeHorizon.SWING,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top sell recommendations."""
        recs = self.get_top_recommendations(
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
    
    def _build_price_dataframe(self, stock_data: Dict) -> Optional[pd.DataFrame]:
        """Build price DataFrame from stock data."""
        # In production, this would fetch historical data
        # For now, create minimal DataFrame
        try:
            df = pd.DataFrame([{
                'Open': stock_data.get('open', stock_data.get('price', 0)),
                'High': stock_data.get('high', stock_data.get('price', 0)),
                'Low': stock_data.get('low', stock_data.get('price', 0)),
                'Close': stock_data.get('close', stock_data.get('price', 0)),
                'Volume': stock_data.get('volume', 0)
            }] * 50, index=pd.date_range(end=datetime.utcnow(), periods=50, freq='D'))
            
            # Add some variation for indicator calculation
            import numpy as np
            noise = np.random.normal(1, 0.02, len(df))
            df['Close'] = df['Close'] * noise
            df['High'] = df['Close'] * 1.02
            df['Low'] = df['Close'] * 0.98
            df['Open'] = df['Close'].shift(1).fillna(df['Close'])
            
            return df
        except Exception as e:
            logger.error(f"Error building DataFrame: {e}")
            return None
    
    def _get_market_dataframe(self) -> Optional[pd.DataFrame]:
        """Get market (ASI) DataFrame."""
        # Would fetch ASI historical data in production
        try:
            df = pd.DataFrame({
                'Open': [50000] * 250,
                'High': [51000] * 250,
                'Low': [49000] * 250,
                'Close': [50500] * 250,
                'Volume': [1000000000] * 250
            }, index=pd.date_range(end=datetime.utcnow(), periods=250, freq='D'))
            
            # Add some variation
            import numpy as np
            trend = np.linspace(0.95, 1.05, len(df))
            noise = np.random.normal(1, 0.01, len(df))
            df['Close'] = df['Close'] * trend * noise
            
            return df
        except Exception:
            return None
    
    def _extract_fundamentals(self, stock_data: Dict) -> Dict[str, Any]:
        """Extract fundamental data from stock data."""
        return {
            'pe_ratio': stock_data.get('pe_ratio'),
            'eps': stock_data.get('eps'),
            'dividend_yield': stock_data.get('dividend_yield'),
            'market_cap': stock_data.get('market_cap')
        }
    
    def _recommendation_to_dict(self, rec: Recommendation) -> Dict[str, Any]:
        """Convert Recommendation to dict."""
        return {
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
        }
    
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
