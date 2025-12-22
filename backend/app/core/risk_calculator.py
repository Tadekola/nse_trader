"""
Risk metrics calculation for NSE Trader.

Provides comprehensive risk assessment for stocks including:
- Volatility metrics
- Drawdown analysis
- Risk-adjusted returns
- Position sizing guidance
"""
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np
from datetime import datetime


class RiskLevel(str, Enum):
    """Risk level categories."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass
class RiskMetrics:
    """Complete risk metrics for a stock."""
    symbol: str
    
    # Volatility metrics
    volatility_20d: float       # 20-day annualized volatility
    volatility_60d: float       # 60-day annualized volatility
    volatility_percentile: float  # Current vol vs historical
    
    # Drawdown metrics
    current_drawdown: float     # Current drawdown from peak
    max_drawdown_90d: float     # Max drawdown in last 90 days
    max_drawdown_1y: float      # Max drawdown in last year
    avg_drawdown_duration: int  # Average days to recover
    
    # Risk-adjusted metrics
    sharpe_ratio: Optional[float]    # Risk-adjusted return
    sortino_ratio: Optional[float]   # Downside risk-adjusted return
    calmar_ratio: Optional[float]    # Return / max drawdown
    
    # Beta and correlation
    beta: Optional[float]            # Beta to ASI
    correlation_asi: Optional[float] # Correlation to ASI
    
    # Value at Risk
    var_95: float               # 95% VaR (daily)
    var_99: float               # 99% VaR (daily)
    cvar_95: float              # Conditional VaR (Expected Shortfall)
    
    # Downside metrics
    downside_deviation: float
    downside_capture: Optional[float]  # % of market downside captured
    upside_capture: Optional[float]    # % of market upside captured
    
    # Risk level
    risk_level: RiskLevel
    risk_score: float           # 0-100 risk score
    
    # Position sizing
    suggested_max_position_pct: float  # Suggested max % of portfolio
    
    # Warnings
    warnings: List[str]
    
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class RiskCalculator:
    """
    Calculates comprehensive risk metrics for stocks.
    
    Designed for Nigerian market considerations:
    - Higher baseline volatility expected
    - Liquidity-adjusted risk
    - Price limit impact
    """
    
    # Nigerian market baseline volatility (higher than developed markets)
    BASELINE_VOLATILITY = 0.30  # 30% annualized
    
    # Risk-free rate (Nigerian T-bill rate approximation)
    RISK_FREE_RATE = 0.12  # 12% annual
    
    def __init__(self):
        self._asi_data: Optional[pd.DataFrame] = None
    
    def set_market_data(self, asi_data: pd.DataFrame):
        """Set ASI data for beta/correlation calculations."""
        self._asi_data = asi_data
    
    def calculate(
        self,
        df: pd.DataFrame,
        symbol: str,
        liquidity_score: float = 1.0
    ) -> Optional[RiskMetrics]:
        """
        Calculate comprehensive risk metrics for a stock.
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Stock symbol
            liquidity_score: Liquidity score 0-1 for adjustment
        
        Returns:
            RiskMetrics dataclass
        """
        if df is None or len(df) < 30:
            return None
        
        close = df['Close']
        returns = close.pct_change().dropna()
        
        if len(returns) < 20:
            return None
        
        # Calculate volatility metrics
        vol_20d = self._calculate_volatility(returns, 20)
        vol_60d = self._calculate_volatility(returns, 60) if len(returns) >= 60 else vol_20d
        vol_percentile = self._calculate_volatility_percentile(returns)
        
        # Calculate drawdown metrics
        current_dd, max_dd_90d, max_dd_1y, avg_dd_duration = self._calculate_drawdowns(close)
        
        # Calculate risk-adjusted metrics
        sharpe = self._calculate_sharpe_ratio(returns)
        sortino = self._calculate_sortino_ratio(returns)
        calmar = self._calculate_calmar_ratio(returns, max_dd_1y)
        
        # Calculate beta and correlation
        beta, corr = self._calculate_beta_correlation(returns)
        
        # Calculate VaR
        var_95, var_99, cvar_95 = self._calculate_var(returns)
        
        # Calculate downside metrics
        downside_dev = self._calculate_downside_deviation(returns)
        up_capture, down_capture = self._calculate_capture_ratios(returns)
        
        # Determine risk level and score
        risk_level, risk_score = self._determine_risk_level(
            vol_20d, max_dd_90d, beta, var_95, liquidity_score
        )
        
        # Calculate suggested position size
        max_position = self._calculate_max_position(risk_score, liquidity_score)
        
        # Generate warnings
        warnings = self._generate_warnings(
            vol_20d, vol_percentile, current_dd, max_dd_90d, 
            beta, liquidity_score
        )
        
        return RiskMetrics(
            symbol=symbol,
            volatility_20d=vol_20d,
            volatility_60d=vol_60d,
            volatility_percentile=vol_percentile,
            current_drawdown=current_dd,
            max_drawdown_90d=max_dd_90d,
            max_drawdown_1y=max_dd_1y,
            avg_drawdown_duration=avg_dd_duration,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            beta=beta,
            correlation_asi=corr,
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            downside_deviation=downside_dev,
            downside_capture=down_capture,
            upside_capture=up_capture,
            risk_level=risk_level,
            risk_score=risk_score,
            suggested_max_position_pct=max_position,
            warnings=warnings
        )
    
    def _calculate_volatility(self, returns: pd.Series, period: int) -> float:
        """Calculate annualized volatility for given period."""
        if len(returns) < period:
            period = len(returns)
        return float(returns.iloc[-period:].std() * np.sqrt(252) * 100)
    
    def _calculate_volatility_percentile(self, returns: pd.Series) -> float:
        """Calculate where current volatility ranks historically."""
        if len(returns) < 60:
            return 50.0
        
        rolling_vol = returns.rolling(20).std()
        current_vol = rolling_vol.iloc[-1]
        percentile = (rolling_vol < current_vol).sum() / len(rolling_vol) * 100
        return float(percentile)
    
    def _calculate_drawdowns(
        self, prices: pd.Series
    ) -> Tuple[float, float, float, int]:
        """Calculate drawdown metrics."""
        # Calculate running maximum
        running_max = prices.expanding().max()
        drawdown = (prices - running_max) / running_max * 100
        
        # Current drawdown
        current_dd = float(drawdown.iloc[-1])
        
        # Max drawdown in last 90 days
        max_dd_90d = float(drawdown.iloc[-90:].min()) if len(drawdown) >= 90 else float(drawdown.min())
        
        # Max drawdown in last year
        max_dd_1y = float(drawdown.iloc[-252:].min()) if len(drawdown) >= 252 else float(drawdown.min())
        
        # Average drawdown duration (simplified)
        in_drawdown = (drawdown < -1).values  # Consider >1% as significant, use .values to avoid index issues
        drawdown_periods = []
        current_period = 0
        for is_dd in in_drawdown:
            if is_dd:
                current_period += 1
            elif current_period > 0:
                drawdown_periods.append(current_period)
                current_period = 0
        
        avg_duration = int(np.mean(drawdown_periods)) if drawdown_periods else 0
        
        return current_dd, max_dd_90d, max_dd_1y, avg_duration
    
    def _calculate_sharpe_ratio(self, returns: pd.Series) -> Optional[float]:
        """Calculate annualized Sharpe ratio."""
        if len(returns) < 30:
            return None
        
        daily_rf = self.RISK_FREE_RATE / 252
        excess_returns = returns - daily_rf
        
        if excess_returns.std() == 0:
            return None
        
        sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
        return float(sharpe)
    
    def _calculate_sortino_ratio(self, returns: pd.Series) -> Optional[float]:
        """Calculate Sortino ratio (downside risk-adjusted)."""
        if len(returns) < 30:
            return None
        
        daily_rf = self.RISK_FREE_RATE / 252
        excess_returns = returns - daily_rf
        
        # Downside deviation
        negative_mask = (excess_returns < 0).values
        negative_returns = excess_returns.iloc[negative_mask]
        if len(negative_returns) == 0 or negative_returns.std() == 0:
            return None
        
        downside_std = negative_returns.std() * np.sqrt(252)
        annual_excess_return = excess_returns.mean() * 252
        
        sortino = annual_excess_return / downside_std
        return float(sortino)
    
    def _calculate_calmar_ratio(
        self, returns: pd.Series, max_dd: float
    ) -> Optional[float]:
        """Calculate Calmar ratio (return / max drawdown)."""
        if max_dd == 0:
            return None
        
        annual_return = returns.mean() * 252 * 100
        calmar = annual_return / abs(max_dd)
        return float(calmar)
    
    def _calculate_beta_correlation(
        self, returns: pd.Series
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate beta and correlation to ASI."""
        if self._asi_data is None or len(self._asi_data) < 30:
            return None, None
        
        # Align dates
        asi_returns = self._asi_data['Close'].pct_change().dropna()
        
        # Use overlapping periods
        common_len = min(len(returns), len(asi_returns))
        if common_len < 30:
            return None, None
        
        stock_ret = returns.iloc[-common_len:].values
        market_ret = asi_returns.iloc[-common_len:].values
        
        # Correlation
        correlation = float(np.corrcoef(stock_ret, market_ret)[0, 1])
        
        # Beta
        covariance = np.cov(stock_ret, market_ret)[0, 1]
        market_variance = np.var(market_ret)
        beta = float(covariance / market_variance) if market_variance > 0 else 1.0
        
        return beta, correlation
    
    def _calculate_var(
        self, returns: pd.Series
    ) -> Tuple[float, float, float]:
        """Calculate Value at Risk metrics."""
        var_95 = float(np.percentile(returns, 5) * 100)
        var_99 = float(np.percentile(returns, 1) * 100)
        
        # Conditional VaR (Expected Shortfall)
        threshold = np.percentile(returns, 5)
        below_threshold_mask = (returns <= threshold).values
        cvar_95 = float(returns.iloc[below_threshold_mask].mean() * 100)
        
        return var_95, var_99, cvar_95
    
    def _calculate_downside_deviation(self, returns: pd.Series) -> float:
        """Calculate downside deviation."""
        negative_mask = (returns < 0).values
        negative_returns = returns.iloc[negative_mask]
        if len(negative_returns) == 0:
            return 0.0
        return float(negative_returns.std() * np.sqrt(252) * 100)
    
    def _calculate_capture_ratios(
        self, returns: pd.Series
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate upside and downside capture ratios."""
        if self._asi_data is None:
            return None, None
        
        asi_returns = self._asi_data['Close'].pct_change().dropna()
        common_len = min(len(returns), len(asi_returns))
        
        if common_len < 30:
            return None, None
        
        # Convert to numpy arrays to avoid index alignment issues
        stock_ret = returns.iloc[-common_len:].values
        market_ret = asi_returns.iloc[-common_len:].values
        
        # Upside capture
        up_market = market_ret > 0
        if up_market.sum() > 0:
            upside_capture = (stock_ret[up_market].mean() / market_ret[up_market].mean()) * 100
        else:
            upside_capture = None
        
        # Downside capture
        down_market = market_ret < 0
        if down_market.sum() > 0:
            downside_capture = (stock_ret[down_market].mean() / market_ret[down_market].mean()) * 100
        else:
            downside_capture = None
        
        return upside_capture, downside_capture
    
    def _determine_risk_level(
        self, vol: float, max_dd: float, beta: Optional[float],
        var_95: float, liquidity_score: float
    ) -> Tuple[RiskLevel, float]:
        """Determine overall risk level and score."""
        score = 0.0
        
        # Volatility component (0-30 points)
        vol_score = min(30, (vol / self.BASELINE_VOLATILITY) * 15)
        score += vol_score
        
        # Drawdown component (0-30 points)
        dd_score = min(30, abs(max_dd) * 1.5)
        score += dd_score
        
        # Beta component (0-20 points)
        if beta is not None:
            beta_score = min(20, abs(beta - 1) * 10)
            score += beta_score
        else:
            score += 10  # Default moderate
        
        # VaR component (0-10 points)
        var_score = min(10, abs(var_95) * 2)
        score += var_score
        
        # Liquidity penalty (0-10 points)
        liquidity_penalty = (1 - liquidity_score) * 10
        score += liquidity_penalty
        
        # Determine level
        if score >= 70:
            level = RiskLevel.VERY_HIGH
        elif score >= 50:
            level = RiskLevel.HIGH
        elif score >= 30:
            level = RiskLevel.MODERATE
        else:
            level = RiskLevel.LOW
        
        return level, min(100, score)
    
    def _calculate_max_position(
        self, risk_score: float, liquidity_score: float
    ) -> float:
        """Calculate suggested maximum position size as % of portfolio."""
        # Base position size
        base_position = 10.0  # 10% max for low risk
        
        # Risk adjustment
        if risk_score >= 70:
            risk_multiplier = 0.3
        elif risk_score >= 50:
            risk_multiplier = 0.5
        elif risk_score >= 30:
            risk_multiplier = 0.75
        else:
            risk_multiplier = 1.0
        
        # Liquidity adjustment
        liquidity_multiplier = max(0.3, liquidity_score)
        
        max_position = base_position * risk_multiplier * liquidity_multiplier
        return round(max_position, 1)
    
    def _generate_warnings(
        self, vol: float, vol_pct: float, current_dd: float,
        max_dd: float, beta: Optional[float], liquidity: float
    ) -> List[str]:
        """Generate risk warnings."""
        warnings = []
        
        if vol > 50:
            warnings.append(f"⚠️ Very high volatility ({vol:.1f}% annualized)")
        elif vol > 35:
            warnings.append(f"⚠️ Elevated volatility ({vol:.1f}% annualized)")
        
        if vol_pct > 80:
            warnings.append("⚠️ Volatility at historical high - consider smaller position")
        
        if current_dd < -15:
            warnings.append(f"⚠️ Currently in significant drawdown ({current_dd:.1f}%)")
        
        if max_dd < -30:
            warnings.append(f"⚠️ High historical drawdown risk ({max_dd:.1f}% in 90 days)")
        
        if beta is not None and beta > 1.5:
            warnings.append(f"⚠️ High beta ({beta:.2f}) - amplified market moves")
        
        if liquidity < 0.4:
            warnings.append("⚠️ Low liquidity - exit may be difficult")
        
        return warnings
    
    def calculate_stop_loss_levels(
        self, current_price: float, atr: float, risk_metrics: RiskMetrics
    ) -> Dict[str, float]:
        """Calculate suggested stop-loss levels."""
        # ATR-based stops
        atr_1x = current_price - atr
        atr_2x = current_price - (2 * atr)
        atr_3x = current_price - (3 * atr)
        
        # Percentage-based stops (adjusted for risk)
        if risk_metrics.risk_level == RiskLevel.LOW:
            pct_stop = current_price * 0.95  # 5%
        elif risk_metrics.risk_level == RiskLevel.MODERATE:
            pct_stop = current_price * 0.93  # 7%
        elif risk_metrics.risk_level == RiskLevel.HIGH:
            pct_stop = current_price * 0.90  # 10%
        else:
            pct_stop = current_price * 0.85  # 15%
        
        return {
            "tight_stop_1atr": round(atr_1x, 2),
            "normal_stop_2atr": round(atr_2x, 2),
            "wide_stop_3atr": round(atr_3x, 2),
            "risk_adjusted_stop": round(pct_stop, 2),
            "recommended_stop": round(atr_2x, 2)  # Default to 2 ATR
        }
