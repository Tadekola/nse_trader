"""
Explanation Generator for NSE Trader.

Generates human-readable explanations for recommendations that:
- Explain indicators in plain English
- Provide Nigerian market context
- Warn about common pitfalls
- Educate while informing
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

from app.core.market_regime import MarketRegime
from app.core.risk_calculator import RiskLevel


class UserLevel(str, Enum):
    """User experience level for explanation customization."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


@dataclass
class IndicatorExplanation:
    """Explanation for a technical indicator."""
    name: str
    value: float
    what_it_is: str
    what_it_means: str
    nigerian_context: str
    action_implication: str


class ExplanationGenerator:
    """
    Generates contextual explanations for trading signals and indicators.
    
    Designed to educate users while providing actionable insights.
    """
    
    # Indicator explanation templates
    INDICATOR_EXPLANATIONS = {
        'rsi': {
            'what_it_is': "RSI (Relative Strength Index) measures how fast the price is moving up or down on a scale of 0 to 100.",
            'thresholds': {
                'oversold': (0, 30, "The stock may be oversold - it's dropped quickly and might bounce back."),
                'neutral': (30, 70, "The stock is trading normally with no extreme momentum."),
                'overbought': (70, 100, "The stock may be overbought - it's risen quickly and might pull back.")
            },
            'nigerian_context': "In Nigerian stocks with low liquidity, RSI can stay extreme for weeks. Don't assume an immediate bounce."
        },
        'macd': {
            'what_it_is': "MACD shows the relationship between two moving averages. When the lines cross, it can signal a trend change.",
            'signals': {
                'bullish_crossover': "MACD just crossed above its signal line - this often precedes upward price movement.",
                'bearish_crossover': "MACD just crossed below its signal line - this often precedes downward price movement.",
                'bullish': "MACD is above its signal line, indicating upward momentum.",
                'bearish': "MACD is below its signal line, indicating downward momentum."
            },
            'nigerian_context': "MACD works best on actively traded stocks. For less liquid NGX stocks, signals may be delayed."
        },
        'bollinger': {
            'what_it_is': "Bollinger Bands show price volatility. When price touches the bands, it may be at an extreme.",
            'signals': {
                'lower_band': "Price is at the lower band - historically, this often precedes a bounce.",
                'upper_band': "Price is at the upper band - historically, this often precedes a pullback.",
                'squeeze': "Bands are narrow - volatility is low, which often precedes a big move."
            },
            'nigerian_context': "Nigerian stocks can trend outside Bollinger Bands for extended periods during strong moves."
        },
        'volume': {
            'what_it_is': "Volume shows how many shares are trading. High volume confirms price moves; low volume suggests weak moves.",
            'signals': {
                'high': "Volume is much higher than average - significant interest in this stock today.",
                'low': "Volume is lower than average - price move may not be reliable.",
                'normal': "Volume is near average - normal trading activity."
            },
            'nigerian_context': "Many NGX stocks trade only a few million Naira daily. Always check if there's enough volume to enter/exit your position."
        },
        'sma': {
            'what_it_is': "Simple Moving Average smooths out price action. When price is above the SMA, the trend is generally up.",
            'signals': {
                'above': "Price is above the moving average, indicating an uptrend.",
                'below': "Price is below the moving average, indicating a downtrend.",
                'golden_cross': "Shorter-term average crossed above longer-term - strong bullish signal.",
                'death_cross': "Shorter-term average crossed below longer-term - strong bearish signal."
            },
            'nigerian_context': "Use longer moving averages (50-day, 200-day) for Nigerian stocks as they're less noisy."
        },
        'atr': {
            'what_it_is': "ATR (Average True Range) measures how much a stock typically moves each day.",
            'usage': "Use ATR to set stop-losses. A 2x ATR stop gives the stock room to move without hitting your stop too early.",
            'nigerian_context': "Nigerian stocks can have very high ATR relative to price. Always calculate ATR as a percentage."
        },
        'adx': {
            'what_it_is': "ADX measures trend strength (not direction). Above 25 means strong trend; below 20 means no trend.",
            'signals': {
                'strong': "ADX above 25 indicates a strong trend - trend-following strategies work well.",
                'weak': "ADX below 20 indicates no clear trend - range-bound strategies work better.",
                'moderate': "ADX between 20-25 - trend is developing but not yet strong."
            },
            'nigerian_context': "Many NGX stocks spend long periods range-bound. ADX helps identify when to use trend vs. mean-reversion strategies."
        }
    }
    
    # Market regime explanations
    REGIME_EXPLANATIONS = {
        MarketRegime.BULL: {
            'what_it_means': "The overall market is in an uptrend. Most stocks tend to rise in bull markets.",
            'strategy': "Look for pullbacks to buy. Hold winning positions longer. Be patient with entries.",
            'warning': "Don't chase stocks that have already moved significantly. Pullbacks are normal."
        },
        MarketRegime.BEAR: {
            'what_it_means': "The overall market is in a downtrend. Most stocks tend to fall in bear markets.",
            'strategy': "Be defensive. Focus on quality stocks with strong dividends. Keep cash ready.",
            'warning': "Avoid catching falling knives. Wait for clear reversal signals before buying."
        },
        MarketRegime.RANGE_BOUND: {
            'what_it_means': "The market is moving sideways without a clear direction.",
            'strategy': "Buy near support levels, sell near resistance. Use tighter stops.",
            'warning': "Breakouts can be false. Wait for confirmation before committing to a direction."
        },
        MarketRegime.HIGH_VOLATILITY: {
            'what_it_means': "The market is experiencing unusually large price swings.",
            'strategy': "Reduce position sizes. Use wider stops. Be prepared for rapid changes.",
            'warning': "High volatility can wipe out positions quickly. Capital preservation is key."
        },
        MarketRegime.LOW_LIQUIDITY: {
            'what_it_means': "Trading volume across the market is very low.",
            'strategy': "Focus only on the most liquid stocks. Avoid small-caps.",
            'warning': "Low liquidity means wider spreads and harder exits. Trade smaller."
        },
        MarketRegime.CRISIS: {
            'what_it_means': "The market is in crisis mode - extreme selling or uncertainty.",
            'strategy': "Preserve capital. Hold cash. Avoid new positions.",
            'warning': "Do not try to time the bottom. Wait for stability before re-entering."
        }
    }
    
    # Risk level explanations
    RISK_EXPLANATIONS = {
        RiskLevel.LOW: {
            'description': "This stock has relatively stable price movement.",
            'position_guidance': "You can take a normal-sized position (up to 10% of portfolio).",
            'stop_guidance': "Use a 5-7% stop-loss from your entry price."
        },
        RiskLevel.MODERATE: {
            'description': "This stock has average volatility for the Nigerian market.",
            'position_guidance': "Consider a moderate position (5-8% of portfolio).",
            'stop_guidance': "Use a 7-10% stop-loss to account for normal swings."
        },
        RiskLevel.HIGH: {
            'description': "This stock experiences significant price swings.",
            'position_guidance': "Use smaller positions (3-5% of portfolio) to manage risk.",
            'stop_guidance': "Use a 10-15% stop-loss or ATR-based stop."
        },
        RiskLevel.VERY_HIGH: {
            'description': "This stock is highly volatile and risky.",
            'position_guidance': "Only small positions (1-3% of portfolio) if trading at all.",
            'stop_guidance': "Wide stops needed (15%+). Consider whether the risk is worth it."
        }
    }
    
    def __init__(self, user_level: UserLevel = UserLevel.BEGINNER):
        self.user_level = user_level
    
    def explain_indicator(
        self, 
        indicator_name: str, 
        value: float,
        signal: str
    ) -> IndicatorExplanation:
        """Generate explanation for an indicator."""
        template = self.INDICATOR_EXPLANATIONS.get(indicator_name.lower(), {})
        
        what_it_is = template.get('what_it_is', f'{indicator_name} is a technical indicator.')
        
        # Determine what_it_means based on value and signal
        what_it_means = self._get_indicator_meaning(indicator_name, value, signal, template)
        
        nigerian_context = template.get(
            'nigerian_context', 
            'Consider liquidity before acting on this signal in Nigerian stocks.'
        )
        
        action_implication = self._get_action_implication(indicator_name, signal)
        
        return IndicatorExplanation(
            name=indicator_name,
            value=value,
            what_it_is=what_it_is,
            what_it_means=what_it_means,
            nigerian_context=nigerian_context,
            action_implication=action_implication
        )
    
    def _get_indicator_meaning(
        self, name: str, value: float, signal: str, template: Dict
    ) -> str:
        """Get meaning based on indicator value."""
        if name.lower() == 'rsi':
            thresholds = template.get('thresholds', {})
            if value <= 30:
                return thresholds.get('oversold', ('', '', 'RSI is oversold'))[2]
            elif value >= 70:
                return thresholds.get('overbought', ('', '', 'RSI is overbought'))[2]
            else:
                return thresholds.get('neutral', ('', '', 'RSI is neutral'))[2]
        
        signals = template.get('signals', {})
        return signals.get(signal, f'{name} is currently {signal}.')
    
    def _get_action_implication(self, name: str, signal: str) -> str:
        """Get action implication from signal."""
        bullish_signals = ['bullish', 'oversold', 'lower_band', 'bullish_crossover', 'above', 'golden_cross']
        bearish_signals = ['bearish', 'overbought', 'upper_band', 'bearish_crossover', 'below', 'death_cross']
        
        if any(s in signal.lower() for s in bullish_signals):
            return "This signal suggests potential upside. Consider as part of a buy case."
        elif any(s in signal.lower() for s in bearish_signals):
            return "This signal suggests caution. Consider taking profits or avoiding new buys."
        else:
            return "This is a neutral signal. Wait for clearer direction."
    
    def explain_recommendation(
        self,
        action: str,
        confidence: float,
        primary_reason: str,
        supporting_reasons: List[str],
        risk_level: RiskLevel,
        liquidity_score: float,
        regime: MarketRegime
    ) -> str:
        """Generate comprehensive recommendation explanation."""
        parts = []
        
        # Action explanation
        action_explanations = {
            'STRONG_BUY': "We see a strong buying opportunity based on multiple confirming signals.",
            'BUY': "The technical setup favors buyers, though not all indicators agree.",
            'HOLD': "There's no clear direction. Maintain existing positions but avoid new ones.",
            'SELL': "The setup suggests downward pressure. Consider reducing exposure.",
            'STRONG_SELL': "Multiple indicators point to significant downside risk.",
            'AVOID': "This stock has issues (usually liquidity) that make it unsuitable for trading."
        }
        parts.append(action_explanations.get(action, f"Recommendation: {action}"))
        
        # Primary reason
        parts.append(f"\n\n**Why:** {primary_reason}")
        
        # Supporting reasons (simplified for beginners)
        if supporting_reasons and self.user_level != UserLevel.ADVANCED:
            parts.append("\n\n**Additional factors:**")
            for i, reason in enumerate(supporting_reasons[:3], 1):
                parts.append(f"\n{i}. {reason}")
        elif supporting_reasons:
            parts.append(f"\n\nSupporting: {'; '.join(supporting_reasons)}")
        
        # Confidence explanation
        if confidence >= 80:
            conf_text = "High confidence - multiple indicators strongly agree."
        elif confidence >= 60:
            conf_text = "Moderate confidence - most indicators lean the same direction."
        else:
            conf_text = "Lower confidence - indicators are mixed. Use caution."
        parts.append(f"\n\n**Confidence:** {confidence:.0f}% - {conf_text}")
        
        # Risk context
        risk_info = self.RISK_EXPLANATIONS.get(risk_level, {})
        parts.append(f"\n\n**Risk Level:** {risk_level.value.upper()}")
        parts.append(f"\n{risk_info.get('description', '')}")
        parts.append(f"\n{risk_info.get('position_guidance', '')}")
        
        # Liquidity warning
        if liquidity_score < 0.3:
            parts.append("\n\n⚠️ **LIQUIDITY WARNING:** This stock trades very little. You may have difficulty exiting your position.")
        elif liquidity_score < 0.5:
            parts.append("\n\n⚠️ **Note:** Moderate liquidity - consider splitting orders over multiple days.")
        
        # Market context
        regime_info = self.REGIME_EXPLANATIONS.get(regime, {})
        parts.append(f"\n\n**Market Context:** {regime_info.get('what_it_means', 'Normal market conditions')}")
        parts.append(f"\n{regime_info.get('strategy', '')}")
        
        return "".join(parts)
    
    def explain_why_not_strong_signal(
        self,
        action: str,
        conflicting_signals: List[str],
        risk_level: RiskLevel,
        liquidity_score: float
    ) -> str:
        """Explain why signal isn't stronger."""
        parts = [f"While we recommend {action}, here's why it's not a stronger signal:\n"]
        
        if conflicting_signals:
            parts.append("\n**Conflicting indicators:**")
            for signal in conflicting_signals[:3]:
                parts.append(f"\n• {signal}")
        
        if risk_level in [RiskLevel.HIGH, RiskLevel.VERY_HIGH]:
            parts.append(f"\n\n**Risk adjustment:** The stock's {risk_level.value} volatility reduces our confidence.")
        
        if liquidity_score < 0.5:
            parts.append(f"\n\n**Liquidity concern:** Low trading volume adds execution risk.")
        
        return "".join(parts)
    
    def get_educational_tip(self, indicator: str) -> str:
        """Get an educational tip about an indicator."""
        tips = {
            'rsi': "💡 **Tip:** RSI works best in ranging markets. In strong trends, RSI can stay overbought/oversold for extended periods.",
            'macd': "💡 **Tip:** MACD crossovers are more reliable when they occur with high volume confirmation.",
            'bollinger': "💡 **Tip:** Bollinger Band squeezes often precede big moves. Watch for volatility expansion.",
            'volume': "💡 **Tip:** Volume confirms price moves. A breakout on low volume is less reliable.",
            'sma': "💡 **Tip:** The 50-day and 200-day moving averages are watched by many traders, making them self-fulfilling support/resistance.",
            'atr': "💡 **Tip:** ATR is great for position sizing. Risk the same Naira amount on each trade regardless of stock price.",
            'liquidity': "💡 **Tip:** In Nigerian stocks, always check if daily volume is enough to absorb your trade without moving the price."
        }
        return tips.get(indicator.lower(), "💡 **Tip:** Always use multiple indicators together for confirmation.")
    
    def format_for_user_level(self, text: str) -> str:
        """Adjust explanation complexity for user level."""
        if self.user_level == UserLevel.BEGINNER:
            # Simplify technical terms
            replacements = {
                'overbought': 'risen quickly (may pull back)',
                'oversold': 'dropped quickly (may bounce)',
                'bullish': 'pointing up',
                'bearish': 'pointing down',
                'momentum': 'speed of price movement',
                'volatility': 'price swings',
                'liquidity': 'trading activity'
            }
            for term, simple in replacements.items():
                text = text.replace(term, f'{term} ({simple})')
        
        return text
