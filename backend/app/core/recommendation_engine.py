"""
Multi-layer Recommendation Engine for NSE Trader.

Produces comprehensive, explainable recommendations that consider:
1. Market regime (bull, bear, range-bound, etc.)
2. Technical signals (multiple indicators)
3. Risk metrics (volatility, drawdown)
4. Liquidity constraints (critical for NGX)
5. Time horizon (short-term, swing, long-term)
6. Fundamental factors (when available)
"""
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import pandas as pd
import numpy as np

from app.core.market_regime import MarketRegimeDetector, MarketRegime, RegimeAnalysis
from app.core.risk_calculator import RiskCalculator, RiskMetrics, RiskLevel
from app.indicators.composite import CompositeIndicator, TechnicalScore
from app.indicators.volume import LiquidityScoreIndicator
from app.indicators.base import SignalDirection, IndicatorResult


class RecommendationAction(str, Enum):
    """Final recommendation action."""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    AVOID = "AVOID"


class TimeHorizon(str, Enum):
    """Investment time horizon."""
    SHORT_TERM = "short_term"    # 1-5 days
    SWING = "swing"              # 1-4 weeks
    LONG_TERM = "long_term"      # 3+ months


@dataclass
class Signal:
    """Individual signal from the engine."""
    name: str
    type: str  # technical, fundamental, liquidity, regime, risk
    direction: str  # bullish, bearish, neutral
    strength: float  # -1 to 1
    confidence: float  # 0 to 1
    plain_english: str
    raw_value: Optional[float] = None


@dataclass
class EntryExitPoints:
    """Suggested entry and exit points."""
    entry_price: float
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    stop_loss_percent: float
    target_1: float
    target_2: Optional[float]
    target_3: Optional[float]
    risk_reward_ratio: float


@dataclass
class Recommendation:
    """Complete recommendation for a stock."""
    symbol: str
    name: str
    action: RecommendationAction
    horizon: TimeHorizon
    confidence: float  # 0-100
    
    # Core data
    current_price: float
    signals: List[Signal]
    risk_metrics: RiskMetrics
    entry_exit: Optional[EntryExitPoints]
    
    # Explanations
    primary_reason: str
    supporting_reasons: List[str]
    risk_warnings: List[str]
    explanation: str
    
    # Nigerian market specifics
    liquidity_score: float
    liquidity_warning: Optional[str]
    corporate_action_alert: Optional[str]
    sector_context: Optional[str]
    
    # Market context
    market_regime: MarketRegime
    regime_adjustment: str
    
    # Scores (for diagnostics and threshold tuning)
    score: float = 0.0           # adjusted composite score used for action determination
    raw_score: float = 0.0       # pre-adjustment composite score
    
    # Metadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: Optional[datetime] = None
    historical_accuracy: Optional[float] = None


class RecommendationEngine:
    """
    Multi-layer recommendation engine that produces comprehensive,
    explainable stock recommendations.
    
    Architecture:
    1. Layer 1: Market Regime Detection
    2. Layer 2: Technical Signal Analysis
    3. Layer 3: Risk Assessment
    4. Layer 4: Liquidity Filtering
    5. Layer 5: Time-Horizon Mapping
    6. Layer 6: Confidence & Explanation Generation
    """
    
    def __init__(self):
        self.regime_detector = MarketRegimeDetector()
        self.risk_calculator = RiskCalculator()
        self.composite_indicator = CompositeIndicator()
        self.technical_score = TechnicalScore()
        self.liquidity_indicator = LiquidityScoreIndicator()
        
        # Weights for different signal types by horizon
        self.horizon_weights = {
            TimeHorizon.SHORT_TERM: {
                'technical': 0.80,
                'fundamental': 0.05,
                'momentum': 0.15
            },
            TimeHorizon.SWING: {
                'technical': 0.60,
                'fundamental': 0.25,
                'momentum': 0.15
            },
            TimeHorizon.LONG_TERM: {
                'technical': 0.25,
                'fundamental': 0.65,
                'momentum': 0.10
            }
        }
    
    def generate_recommendation(
        self,
        symbol: str,
        name: str,
        price_data: pd.DataFrame,
        horizon: TimeHorizon = TimeHorizon.SWING,
        market_data: Optional[pd.DataFrame] = None,
        fundamental_data: Optional[Dict] = None,
        corporate_actions: Optional[List[Dict]] = None
    ) -> Optional[Recommendation]:
        """
        Generate a comprehensive recommendation for a stock.
        
        Args:
            symbol: Stock ticker symbol
            name: Company name
            price_data: DataFrame with OHLCV data
            horizon: Investment time horizon
            market_data: ASI/market OHLCV data for regime detection
            fundamental_data: Optional fundamental metrics
            corporate_actions: Optional upcoming corporate actions
        
        Returns:
            Complete Recommendation or None if insufficient data
        """
        if price_data is None or len(price_data) < 50:
            return None
        
        current_price = float(price_data['Close'].iloc[-1])
        
        # Layer 1: Market Regime Detection
        regime_analysis = self._analyze_market_regime(market_data, price_data)
        
        # Layer 2: Technical Signal Analysis
        technical_signals, technical_score = self._analyze_technicals(price_data)
        
        # Layer 3: Risk Assessment
        liquidity_result = self.liquidity_indicator.calculate(price_data)
        liquidity_score = liquidity_result.raw_values['liquidity_score'] if liquidity_result else 0.5
        
        self.risk_calculator.set_market_data(market_data)
        risk_metrics = self.risk_calculator.calculate(price_data, symbol, liquidity_score)
        
        if risk_metrics is None:
            return None
        
        # Layer 4: Fundamental Integration (if available)
        fundamental_signals = self._analyze_fundamentals(fundamental_data, horizon)
        
        # Layer 5: Combine all signals with horizon-appropriate weights
        all_signals = technical_signals + fundamental_signals
        raw_score, confidence = self._combine_signals(all_signals, horizon)
        
        # Layer 6: Apply regime and risk adjustments
        adjusted_score = self._apply_adjustments(
            raw_score, regime_analysis, risk_metrics, liquidity_score
        )
        
        # Determine action
        action = self._determine_action(adjusted_score, liquidity_score, risk_metrics.risk_level)
        
        # Calculate entry/exit points
        entry_exit = self._calculate_entry_exit(
            current_price, price_data, risk_metrics, action
        )
        
        # Generate explanations
        primary_reason, supporting_reasons = self._generate_reasons(
            all_signals, action, regime_analysis, risk_metrics
        )
        explanation = self._generate_explanation(
            symbol, action, primary_reason, supporting_reasons,
            regime_analysis, risk_metrics, liquidity_score
        )
        
        # Generate warnings
        risk_warnings = self._generate_risk_warnings(
            risk_metrics, liquidity_score, regime_analysis
        )
        
        # Liquidity warning
        liquidity_warning = self._generate_liquidity_warning(liquidity_score)
        
        # Corporate action alert
        corporate_alert = self._check_corporate_actions(corporate_actions)
        
        # Sector context
        sector_context = self._get_sector_context(regime_analysis)
        
        # Validity period based on horizon
        valid_until = self._calculate_validity(horizon)
        
        # Calculate historical accuracy (backtest)
        historical_accuracy = self._calculate_historical_accuracy(price_data)
        
        return Recommendation(
            symbol=symbol,
            name=name,
            action=action,
            horizon=horizon,
            confidence=confidence,
            current_price=current_price,
            signals=all_signals,
            risk_metrics=risk_metrics,
            entry_exit=entry_exit,
            primary_reason=primary_reason,
            supporting_reasons=supporting_reasons,
            risk_warnings=risk_warnings,
            explanation=explanation,
            liquidity_score=liquidity_score,
            liquidity_warning=liquidity_warning,
            corporate_action_alert=corporate_alert,
            sector_context=sector_context,
            market_regime=regime_analysis.regime if regime_analysis else MarketRegime.RANGE_BOUND,
            regime_adjustment=regime_analysis.recommended_strategy if regime_analysis else "Normal trading",
            score=adjusted_score,
            raw_score=raw_score,
            valid_until=valid_until,
            historical_accuracy=historical_accuracy
        )
    
    def _calculate_historical_accuracy(self, df: pd.DataFrame, backtest_days: int = 90) -> float:
        """
        Calculate historical accuracy of predictions based on simplified backtesting.
        Returns percentage accuracy (0-100).
        """
        if df is None or len(df) < 30:
            return 65.0  # Default baseline
            
        prices = df['Close'].values
        if len(prices) < 30:
            return 65.0
            
        # Limit the number of days to backtest
        days_to_test = min(backtest_days, len(prices) - 20)
        if days_to_test <= 0:
            return 65.0
            
        successful_signals = 0
        total_signals = 0
        
        # Simple moving average and RSI helper functions for backtest
        def get_rsi(p, period=14):
            if len(p) < period + 1: return 50
            delta = np.diff(p)
            gain = np.where(delta > 0, delta, 0)
            loss = np.where(delta < 0, -delta, 0)
            avg_gain = np.mean(gain[-period:])
            avg_loss = np.mean(loss[-period:])
            if avg_loss == 0: return 100
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))
            
        # Backtest loop
        # We start from (end - days_to_test) up to (end - 5) to allow outcome check
        start_idx = len(prices) - days_to_test
        end_idx = len(prices) - 5
        
        for i in range(start_idx, end_idx):
            # Window of data up to current point i
            # Need enough history for indicators (at least 20 days)
            if i < 20: continue
            
            window = prices[i-20:i+1]
            current_price = prices[i]
            
            # Simple Strategy: RSI Reversal + Trend Follow
            rsi = get_rsi(window)
            sma_short = np.mean(window[-5:])
            sma_long = np.mean(window)
            
            signal = 'hold'
            if rsi < 30 and current_price > sma_short:
                signal = 'buy'
            elif rsi > 70 and current_price < sma_short:
                signal = 'sell'
            elif sma_short > sma_long and rsi < 60:
                signal = 'buy'
            elif sma_short < sma_long and rsi > 40:
                signal = 'sell'
                
            if signal == 'hold':
                continue
                
            # Outcome (5 day return)
            future_price = prices[i+5]
            ret = (future_price - current_price) / current_price
            
            if (signal == 'buy' and ret > 0) or (signal == 'sell' and ret < 0):
                successful_signals += 1
            total_signals += 1
            
        if total_signals == 0:
            return 65.0
            
        accuracy = (successful_signals / total_signals) * 100
        # Dampen extreme values
        return max(40.0, min(90.0, accuracy))

    def _analyze_market_regime(
        self, market_data: Optional[pd.DataFrame], stock_data: pd.DataFrame
    ) -> Optional[RegimeAnalysis]:
        """Analyze current market regime."""
        if market_data is not None and len(market_data) >= 200:
            return self.regime_detector.detect(market_data)
        
        # Fallback: Use stock data as proxy (less accurate)
        if len(stock_data) >= 200:
            return self.regime_detector.detect(stock_data)
        
        return None
    
    def _analyze_technicals(
        self, df: pd.DataFrame
    ) -> Tuple[List[Signal], float]:
        """Analyze technical indicators and convert to signals."""
        signals = []
        
        # Get composite indicator results
        composite_result = self.composite_indicator.calculate(df)
        if composite_result and composite_result.raw_values:
            individual_results = composite_result.raw_values.get('individual_results', {})
            
            for name, result_dict in individual_results.items():
                direction = result_dict.get('signal', 'neutral')
                strength = result_dict.get('strength', 0)
                
                signals.append(Signal(
                    name=name,
                    type='technical',
                    direction=direction,
                    strength=strength,
                    confidence=abs(strength),
                    plain_english=result_dict.get('description', ''),
                    raw_value=result_dict.get('value')
                ))
        
        # Get overall technical score
        tech_score_result = self.technical_score.calculate(df)
        score = tech_score_result.value if tech_score_result else 0
        
        return signals, score
    
    def _analyze_fundamentals(
        self, data: Optional[Dict], horizon: TimeHorizon
    ) -> List[Signal]:
        """
        Analyze fundamental data and convert to signals.

        When enriched with growth profile data (revenue_growth, earnings_growth,
        quality_score, sector_macro_alignment, etc.), produces comprehensive
        fundamental signals.  Falls back to basic P/E / dividend / ROE analysis
        when only market-data fields are available.
        """
        if data is None:
            return []
        
        signals = []
        
        # ── Revenue growth ──────────────────────────────────────────────
        rev_growth = data.get('revenue_growth')
        if rev_growth is not None:
            if rev_growth > 0.25:
                signals.append(Signal(
                    name='revenue_growth', type='fundamental',
                    direction='bullish', strength=0.8, confidence=0.8,
                    plain_english=f'Strong revenue growth of {rev_growth:.0%} YoY',
                    raw_value=rev_growth))
            elif rev_growth > 0.10:
                signals.append(Signal(
                    name='revenue_growth', type='fundamental',
                    direction='bullish', strength=0.5, confidence=0.7,
                    plain_english=f'Solid revenue growth of {rev_growth:.0%} YoY',
                    raw_value=rev_growth))
            elif rev_growth < -0.05:
                signals.append(Signal(
                    name='revenue_growth', type='fundamental',
                    direction='bearish', strength=-0.6, confidence=0.7,
                    plain_english=f'Revenue declining {rev_growth:.0%} YoY',
                    raw_value=rev_growth))

        # ── Earnings growth ─────────────────────────────────────────────
        earn_growth = data.get('earnings_growth')
        if earn_growth is not None:
            if earn_growth > 0.30:
                signals.append(Signal(
                    name='earnings_growth', type='fundamental',
                    direction='bullish', strength=0.85, confidence=0.8,
                    plain_english=f'Rapid earnings growth of {earn_growth:.0%} YoY',
                    raw_value=earn_growth))
            elif earn_growth > 0.10:
                signals.append(Signal(
                    name='earnings_growth', type='fundamental',
                    direction='bullish', strength=0.5, confidence=0.7,
                    plain_english=f'Healthy earnings growth of {earn_growth:.0%} YoY',
                    raw_value=earn_growth))
            elif earn_growth < -0.10:
                signals.append(Signal(
                    name='earnings_growth', type='fundamental',
                    direction='bearish', strength=-0.65, confidence=0.7,
                    plain_english=f'Earnings declining {earn_growth:.0%} YoY',
                    raw_value=earn_growth))

        # ── ROE (Return on Equity) ──────────────────────────────────────
        roe = data.get('roe')
        if roe is not None:
            # roe comes as fraction from growth profile, or percentage from registry
            roe_frac = roe if roe < 1 else roe / 100
            if roe_frac > 0.20:
                signals.append(Signal(
                    name='roe', type='fundamental',
                    direction='bullish', strength=0.7, confidence=0.8,
                    plain_english=f'Excellent ROE of {roe_frac:.0%} — efficient capital use',
                    raw_value=roe_frac))
            elif roe_frac > 0.12:
                signals.append(Signal(
                    name='roe', type='fundamental',
                    direction='bullish', strength=0.45, confidence=0.7,
                    plain_english=f'Good ROE of {roe_frac:.0%}',
                    raw_value=roe_frac))
            elif roe_frac < 0.03 and roe_frac >= 0:
                signals.append(Signal(
                    name='roe', type='fundamental',
                    direction='bearish', strength=-0.3, confidence=0.6,
                    plain_english=f'Weak ROE of {roe_frac:.0%} — poor capital efficiency',
                    raw_value=roe_frac))

        # ── Operating margin ────────────────────────────────────────────
        op_margin = data.get('op_margin')
        if op_margin is not None:
            if op_margin > 0.25:
                signals.append(Signal(
                    name='op_margin', type='fundamental',
                    direction='bullish', strength=0.55, confidence=0.75,
                    plain_english=f'Strong operating margin of {op_margin:.0%} — pricing power',
                    raw_value=op_margin))
            elif op_margin < 0.05 and op_margin >= 0:
                signals.append(Signal(
                    name='op_margin', type='fundamental',
                    direction='bearish', strength=-0.35, confidence=0.65,
                    plain_english=f'Thin operating margin of {op_margin:.0%}',
                    raw_value=op_margin))

        # ── Balance sheet strength (Debt/Equity) ────────────────────────
        de = data.get('debt_to_equity')
        if de is not None:
            if de < 0.3:
                signals.append(Signal(
                    name='balance_sheet', type='fundamental',
                    direction='bullish', strength=0.45, confidence=0.7,
                    plain_english=f'Conservative leverage (D/E {de:.2f})',
                    raw_value=de))
            elif de > 2.5:
                signals.append(Signal(
                    name='balance_sheet', type='fundamental',
                    direction='bearish', strength=-0.5, confidence=0.7,
                    plain_english=f'High leverage concern (D/E {de:.1f})',
                    raw_value=de))

        # ── Cash quality (FCF) ──────────────────────────────────────────
        fcf = data.get('fcf')
        if fcf is not None:
            if fcf > 0:
                signals.append(Signal(
                    name='cash_quality', type='fundamental',
                    direction='bullish', strength=0.4, confidence=0.75,
                    plain_english=f'Positive free cash flow (₦{fcf:,.0f})',
                    raw_value=fcf))
            elif fcf < 0:
                signals.append(Signal(
                    name='cash_quality', type='fundamental',
                    direction='bearish', strength=-0.35, confidence=0.65,
                    plain_english='Negative free cash flow — cash burn',
                    raw_value=fcf))

        # ── Earnings stability ──────────────────────────────────────────
        stability = data.get('earnings_stability')
        if stability is not None:
            if stability > 0.80:
                signals.append(Signal(
                    name='earnings_stability', type='fundamental',
                    direction='bullish', strength=0.4, confidence=0.7,
                    plain_english='Highly stable earnings across periods',
                    raw_value=stability))
            elif stability < 0.30:
                signals.append(Signal(
                    name='earnings_stability', type='fundamental',
                    direction='bearish', strength=-0.3, confidence=0.6,
                    plain_english='Volatile earnings — unpredictable profitability',
                    raw_value=stability))

        # ── Quality score ───────────────────────────────────────────────
        quality = data.get('quality_score')
        if quality is not None:
            if quality >= 60:
                signals.append(Signal(
                    name='quality_score', type='fundamental',
                    direction='bullish', strength=0.6, confidence=0.8,
                    plain_english=f'High business quality (score {quality:.0f}/100)',
                    raw_value=quality))
            elif quality < 30:
                signals.append(Signal(
                    name='quality_score', type='fundamental',
                    direction='bearish', strength=-0.5, confidence=0.7,
                    plain_english=f'Low business quality (score {quality:.0f}/100)',
                    raw_value=quality))

        # ── Sector macro alignment (Nigeria growth thesis) ──────────────
        sector_align = data.get('sector_macro_alignment')
        if sector_align is not None and sector_align >= 0.75:
            sector = data.get('sector', 'sector')
            signals.append(Signal(
                name='sector_alignment', type='fundamental',
                direction='bullish', strength=0.5 * sector_align,
                confidence=0.75,
                plain_english=f'{sector} sector well-positioned for Nigeria economic growth',
                raw_value=sector_align))

        # ── Growth potential composite ──────────────────────────────────
        growth_potential = data.get('growth_potential')
        if growth_potential is not None and growth_potential >= 60:
            signals.append(Signal(
                name='growth_potential', type='fundamental',
                direction='bullish', strength=0.7, confidence=0.75,
                plain_english=f'High growth potential score ({growth_potential:.0f}/100)',
                raw_value=growth_potential))

        # ── P/E Ratio (fallback if no growth data) ──────────────────────
        pe = data.get('pe_ratio')
        if pe is not None and rev_growth is None:
            # Only use simple P/E when no growth data to compute PEG
            if pe < 5:
                signals.append(Signal(
                    name='pe_ratio', type='fundamental',
                    direction='bullish', strength=0.7, confidence=0.7,
                    plain_english=f'Low P/E ratio of {pe:.1f} suggests undervaluation',
                    raw_value=pe))
            elif pe > 20:
                signals.append(Signal(
                    name='pe_ratio', type='fundamental',
                    direction='bearish', strength=-0.5, confidence=0.6,
                    plain_english=f'High P/E ratio of {pe:.1f} suggests overvaluation',
                    raw_value=pe))

        # ── Dividend yield ──────────────────────────────────────────────
        div_yield = data.get('dividend_yield')
        if div_yield is not None and div_yield > 5:
            signals.append(Signal(
                name='dividend_yield', type='fundamental',
                direction='bullish', strength=0.5, confidence=0.8,
                plain_english=f'Attractive dividend yield of {div_yield:.1f}%',
                raw_value=div_yield))
        
        return signals
    
    def _combine_signals(
        self, signals: List[Signal], horizon: TimeHorizon
    ) -> Tuple[float, float]:
        """Combine signals with horizon-appropriate weighting."""
        if not signals:
            return 0.0, 0.0
        
        weights = self.horizon_weights[horizon]
        
        weighted_score = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        
        for signal in signals:
            signal_type = signal.type
            if signal_type in weights:
                weight = weights[signal_type]
            else:
                weight = 0.1  # Default weight for unknown types
            
            weighted_score += signal.strength * weight * signal.confidence
            total_weight += weight
            total_confidence += signal.confidence
        
        if total_weight > 0:
            normalized_score = weighted_score / total_weight
        else:
            normalized_score = 0.0
        
        # Confidence based on signal agreement
        bullish = sum(1 for s in signals if s.strength > 0.2)
        bearish = sum(1 for s in signals if s.strength < -0.2)
        neutral = len(signals) - bullish - bearish
        
        max_agreement = max(bullish, bearish, neutral)
        agreement_confidence = max_agreement / len(signals) if signals else 0
        
        # Combine with individual signal confidence
        avg_signal_confidence = total_confidence / len(signals) if signals else 0
        final_confidence = (agreement_confidence * 0.6 + avg_signal_confidence * 0.4) * 100
        
        return normalized_score, min(95, final_confidence)
    
    def _apply_adjustments(
        self, raw_score: float, regime: Optional[RegimeAnalysis],
        risk: RiskMetrics, liquidity: float
    ) -> float:
        """Apply regime, risk, and liquidity adjustments to score."""
        adjusted = raw_score
        
        # Regime adjustment
        if regime:
            adjusted = self.regime_detector.get_regime_adjustment(adjusted, regime.regime)
        
        # Risk adjustment (penalize high-risk stocks)
        if risk.risk_level == RiskLevel.VERY_HIGH:
            adjusted *= 0.7
        elif risk.risk_level == RiskLevel.HIGH:
            adjusted *= 0.85
        
        # Liquidity adjustment (penalize illiquid stocks)
        if liquidity < 0.3:
            adjusted *= 0.6
        elif liquidity < 0.5:
            adjusted *= 0.8
        
        return max(-1.0, min(1.0, adjusted))
    
    def _determine_action(
        self, score: float, liquidity: float, risk_level: RiskLevel
    ) -> RecommendationAction:
        """Determine final recommendation action.
        
        Thresholds calibrated to actual score distribution (~-0.15 to +0.16
        for Nigerian equities with 150 sessions of history). Scores are
        compressed by multi-layer normalization and risk/regime adjustments.
        """
        
        # Very low liquidity = AVOID regardless of score
        if liquidity < 0.2:
            return RecommendationAction.AVOID
        
        # Very high risk reduces bullish recommendations
        if risk_level == RiskLevel.VERY_HIGH:
            if score > 0.08:
                return RecommendationAction.BUY  # Cap at BUY, not STRONG_BUY
            elif score > 0.00:
                return RecommendationAction.HOLD
            elif score > -0.08:
                return RecommendationAction.HOLD
            elif score > -0.12:
                return RecommendationAction.SELL
            else:
                return RecommendationAction.STRONG_SELL
        
        # Normal action mapping
        if score >= 0.12:
            return RecommendationAction.STRONG_BUY
        elif score >= 0.04:
            return RecommendationAction.BUY
        elif score >= -0.04:
            return RecommendationAction.HOLD
        elif score >= -0.12:
            return RecommendationAction.SELL
        else:
            return RecommendationAction.STRONG_SELL
    
    def _calculate_entry_exit(
        self, price: float, df: pd.DataFrame,
        risk: RiskMetrics, action: RecommendationAction
    ) -> Optional[EntryExitPoints]:
        """Calculate entry and exit points."""
        if action in [RecommendationAction.AVOID, RecommendationAction.HOLD]:
            return None
        
        # Get ATR for stop calculation
        from app.indicators.base import calculate_atr
        atr_series = calculate_atr(df)
        atr = float(atr_series.iloc[-1]) if len(atr_series) > 0 else price * 0.03
        
        if action in [RecommendationAction.BUY, RecommendationAction.STRONG_BUY]:
            # Buy setup
            entry_zone_low = price * 0.98
            entry_zone_high = price * 1.01
            stop_loss = price - (2 * atr)
            stop_loss_pct = ((price - stop_loss) / price) * 100
            
            # Targets based on risk-reward
            risk_amount = price - stop_loss
            target_1 = price + (risk_amount * 1.5)
            target_2 = price + (risk_amount * 2.5)
            target_3 = price + (risk_amount * 4.0)
            
            rr_ratio = 1.5
        else:
            # Sell setup (exit points for existing positions)
            entry_zone_low = price * 0.99
            entry_zone_high = price * 1.02
            stop_loss = price + (2 * atr)  # Stop above for shorts
            stop_loss_pct = ((stop_loss - price) / price) * 100
            
            target_1 = price * 0.95
            target_2 = price * 0.90
            target_3 = price * 0.85
            
            rr_ratio = 1.5
        
        return EntryExitPoints(
            entry_price=round(price, 2),
            entry_zone_low=round(entry_zone_low, 2),
            entry_zone_high=round(entry_zone_high, 2),
            stop_loss=round(stop_loss, 2),
            stop_loss_percent=round(stop_loss_pct, 2),
            target_1=round(target_1, 2),
            target_2=round(target_2, 2),
            target_3=round(target_3, 2),
            risk_reward_ratio=round(rr_ratio, 2)
        )
    
    def _generate_reasons(
        self, signals: List[Signal], action: RecommendationAction,
        regime: Optional[RegimeAnalysis], risk: RiskMetrics
    ) -> Tuple[str, List[str]]:
        """Generate primary and supporting reasons."""
        # Sort signals by strength
        sorted_signals = sorted(signals, key=lambda s: abs(s.strength), reverse=True)
        
        # Primary reason - strongest signal aligned with action
        primary = "Mixed technical signals"
        if sorted_signals:
            if action in [RecommendationAction.BUY, RecommendationAction.STRONG_BUY]:
                bullish = [s for s in sorted_signals if s.strength > 0.2]
                if bullish:
                    primary = bullish[0].plain_english
            elif action in [RecommendationAction.SELL, RecommendationAction.STRONG_SELL]:
                bearish = [s for s in sorted_signals if s.strength < -0.2]
                if bearish:
                    primary = bearish[0].plain_english
            else:
                primary = "No clear directional signal - maintain current position"
        
        # Supporting reasons
        supporting = []
        for signal in sorted_signals[1:4]:  # Top 3 additional signals
            if signal.plain_english and signal.plain_english != primary:
                supporting.append(signal.plain_english)
        
        # Add regime context
        if regime:
            supporting.append(f"Market regime: {regime.regime.value} - {regime.recommended_strategy}")
        
        # Add risk context
        supporting.append(f"Risk level: {risk.risk_level.value} (volatility {risk.volatility_20d:.1f}%)")
        
        return primary, supporting[:5]
    
    def _generate_explanation(
        self, symbol: str, action: RecommendationAction,
        primary: str, supporting: List[str],
        regime: Optional[RegimeAnalysis], risk: RiskMetrics,
        liquidity: float
    ) -> str:
        """Generate complete human-readable explanation."""
        action_text = {
            RecommendationAction.STRONG_BUY: "a STRONG BUY",
            RecommendationAction.BUY: "a BUY",
            RecommendationAction.HOLD: "a HOLD",
            RecommendationAction.SELL: "a SELL",
            RecommendationAction.STRONG_SELL: "a STRONG SELL",
            RecommendationAction.AVOID: "AVOID"
        }
        
        parts = [f"{symbol} is rated {action_text[action]}."]
        parts.append(f"The main reason: {primary}.")
        
        if supporting:
            parts.append(f"This is supported by: {'; '.join(supporting[:2])}.")
        
        if risk.risk_level in [RiskLevel.HIGH, RiskLevel.VERY_HIGH]:
            parts.append(f"⚠️ Note: This stock has {risk.risk_level.value} volatility.")
        
        if liquidity < 0.5:
            parts.append("⚠️ Caution: Low liquidity may affect your ability to buy/sell.")
        
        return " ".join(parts)
    
    def _generate_risk_warnings(
        self, risk: RiskMetrics, liquidity: float,
        regime: Optional[RegimeAnalysis]
    ) -> List[str]:
        """Generate risk warnings."""
        warnings = list(risk.warnings)  # Start with risk-calculated warnings
        
        if liquidity < 0.3:
            warnings.append("⚠️ Very low liquidity - significant execution risk")
        elif liquidity < 0.5:
            warnings.append("⚠️ Low liquidity - may impact trade execution")
        
        if regime and regime.regime == MarketRegime.CRISIS:
            warnings.append("⚠️ Market in crisis mode - all positions carry elevated risk")
        elif regime and regime.regime == MarketRegime.HIGH_VOLATILITY:
            warnings.append("⚠️ High market volatility - consider smaller positions")
        
        return warnings
    
    def _generate_liquidity_warning(self, liquidity: float) -> Optional[str]:
        """Generate liquidity-specific warning."""
        if liquidity < 0.2:
            return "CRITICAL: This stock is nearly illiquid. Avoid new positions."
        elif liquidity < 0.4:
            return "WARNING: Low trading volume. Your order may move the price significantly."
        elif liquidity < 0.6:
            return "Note: Moderate liquidity. Consider splitting large orders over multiple days."
        return None
    
    def _check_corporate_actions(self, actions: Optional[List[Dict]]) -> Optional[str]:
        """Check for upcoming corporate actions."""
        if not actions:
            return None
        
        upcoming = [a for a in actions if a.get('is_upcoming', True)]
        if upcoming:
            action = upcoming[0]
            return f"Upcoming: {action.get('action_type', 'corporate action')} - {action.get('description', '')}"
        return None
    
    def _get_sector_context(self, regime: Optional[RegimeAnalysis]) -> Optional[str]:
        """Get sector-specific context based on regime."""
        if regime and regime.sectors_to_favor:
            favored = ", ".join(regime.sectors_to_favor[:3])
            return f"Current environment favors: {favored}"
        return None
    
    def _calculate_validity(self, horizon: TimeHorizon) -> datetime:
        """Calculate when recommendation expires."""
        now = datetime.now(timezone.utc)
        
        if horizon == TimeHorizon.SHORT_TERM:
            return now + timedelta(days=1)
        elif horizon == TimeHorizon.SWING:
            return now + timedelta(days=7)
        else:
            return now + timedelta(days=30)
