"""
Knowledge Base for NSE Trader.

Provides educational content about trading, indicators, and the Nigerian market.
"""
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum


class ContentCategory(str, Enum):
    """Knowledge content categories."""
    INDICATOR = "indicator"
    CONCEPT = "concept"
    NIGERIAN_MARKET = "nigerian_market"
    RISK_WARNING = "risk_warning"
    STRATEGY = "strategy"
    GLOSSARY = "glossary"


@dataclass
class KnowledgeArticle:
    """A knowledge base article."""
    id: str
    title: str
    category: ContentCategory
    summary: str
    content: str
    nigerian_context: Optional[str] = None
    related_articles: List[str] = None
    difficulty: str = "beginner"  # beginner, intermediate, advanced
    read_time_minutes: int = 2
    
    def __post_init__(self):
        if self.related_articles is None:
            self.related_articles = []


class KnowledgeBase:
    """
    Knowledge base for investor education.
    
    Provides contextual explanations of:
    - Technical indicators
    - Trading concepts
    - Nigerian market specifics
    - Risk warnings
    """
    
    # Indicator explanations
    INDICATORS = {
        'rsi': KnowledgeArticle(
            id='rsi',
            title='RSI (Relative Strength Index)',
            category=ContentCategory.INDICATOR,
            summary='Measures momentum by comparing recent gains to losses on a 0-100 scale.',
            content='''
## What is RSI?

RSI (Relative Strength Index) is a momentum oscillator that measures the speed and magnitude of recent price changes. It ranges from 0 to 100.

## How to Read RSI

- **RSI below 30**: The stock is considered "oversold" - it may have dropped too fast and could bounce back.
- **RSI above 70**: The stock is considered "overbought" - it may have risen too fast and could pull back.
- **RSI between 30-70**: The stock is in a neutral zone with no extreme momentum.

## How to Use RSI

1. **Buy Signal**: When RSI drops below 30 and then crosses back above, it can signal a buying opportunity.
2. **Sell Signal**: When RSI rises above 70 and then crosses back below, it can signal a selling opportunity.
3. **Divergence**: If price makes a new high but RSI doesn't, it's a bearish divergence (potential reversal).

## Common Mistakes

- Don't buy just because RSI is below 30 - wait for it to turn back up.
- In strong trends, RSI can stay overbought/oversold for extended periods.
''',
            nigerian_context='''
In Nigerian stocks with low liquidity, RSI can remain at extreme levels (below 30 or above 70) for weeks or even months. This is because there aren't enough buyers or sellers to move the price quickly. 

**Important**: On the NGX, always combine RSI with volume analysis. An RSI signal with low volume is less reliable.
''',
            related_articles=['macd', 'stochastic', 'momentum'],
            difficulty='beginner',
            read_time_minutes=3
        ),
        
        'macd': KnowledgeArticle(
            id='macd',
            title='MACD (Moving Average Convergence Divergence)',
            category=ContentCategory.INDICATOR,
            summary='Shows the relationship between two moving averages to identify trend changes.',
            content='''
## What is MACD?

MACD is a trend-following momentum indicator that shows the relationship between two moving averages of a stock's price.

## Components

1. **MACD Line**: The difference between 12-day and 26-day exponential moving averages.
2. **Signal Line**: A 9-day EMA of the MACD line.
3. **Histogram**: The difference between MACD and Signal lines.

## How to Read MACD

- **Bullish Crossover**: MACD crosses above the signal line - potential buy signal.
- **Bearish Crossover**: MACD crosses below the signal line - potential sell signal.
- **Zero Line Cross**: MACD crossing above zero confirms uptrend, below zero confirms downtrend.

## Best Practices

- Use MACD on daily charts for swing trading.
- Combine with RSI for confirmation.
- Watch for divergences between MACD and price.
''',
            nigerian_context='''
MACD works best on actively traded Nigerian stocks like DANGCEM, MTNN, GTCO, and ZENITHBANK. For less liquid stocks, MACD signals may be delayed or unreliable.

**Tip**: Use weekly MACD for longer-term positions in Nigerian stocks, as daily signals can be noisy.
''',
            related_articles=['rsi', 'moving_averages', 'trend'],
            difficulty='intermediate',
            read_time_minutes=4
        ),
        
        'bollinger': KnowledgeArticle(
            id='bollinger',
            title='Bollinger Bands',
            category=ContentCategory.INDICATOR,
            summary='Shows volatility and potential overbought/oversold conditions using standard deviation bands.',
            content='''
## What are Bollinger Bands?

Bollinger Bands consist of three lines:
1. **Middle Band**: 20-day simple moving average
2. **Upper Band**: Middle band + 2 standard deviations
3. **Lower Band**: Middle band - 2 standard deviations

## How to Read Bollinger Bands

- **Price at Upper Band**: Stock may be overbought, potential resistance.
- **Price at Lower Band**: Stock may be oversold, potential support.
- **Band Width**: Narrow bands = low volatility (potential breakout coming); Wide bands = high volatility.

## Trading Strategies

1. **Mean Reversion**: Buy when price touches lower band, sell when it reaches middle or upper band.
2. **Breakout**: When bands squeeze tight, watch for a breakout in either direction.
3. **Trend Following**: In strong trends, price can "walk the band" (stay at upper or lower band).
''',
            nigerian_context='''
Nigerian stocks can trend outside Bollinger Bands for extended periods during strong moves, especially in banking stocks during earnings season or after dividend announcements.

**Warning**: In low-liquidity stocks, Bollinger Bands can be misleading because the bands reflect historical volatility which may not predict future moves.
''',
            related_articles=['volatility', 'atr', 'support_resistance'],
            difficulty='intermediate',
            read_time_minutes=4
        ),
        
        'volume': KnowledgeArticle(
            id='volume',
            title='Volume Analysis',
            category=ContentCategory.INDICATOR,
            summary='Trading volume confirms price moves and reveals the strength of market conviction.',
            content='''
## What is Volume?

Volume is the number of shares traded during a given period. It's one of the most important indicators for confirming price movements.

## Key Principles

1. **Volume Confirms Price**: A price move with high volume is more significant than one with low volume.
2. **Volume Precedes Price**: Unusual volume often appears before a major price move.
3. **Exhaustion**: Extremely high volume after a long move can signal exhaustion.

## How to Use Volume

- **Breakouts**: Valid breakouts should have higher-than-average volume.
- **Pullbacks**: Healthy pullbacks in uptrends should have lower volume.
- **Reversals**: Watch for volume spikes at potential reversal points.
''',
            nigerian_context='''
Volume analysis is CRITICAL in Nigerian stocks because many stocks trade very little on normal days.

**Key Points for NGX:**
- Many stocks trade less than ₦10 million per day
- Always check if there's enough volume to enter/exit your position
- High volume in a normally illiquid stock can signal insider activity
- Dividend season often brings increased volume in banking and consumer goods stocks
''',
            related_articles=['liquidity', 'obv', 'breakout'],
            difficulty='beginner',
            read_time_minutes=3
        )
    }
    
    # Nigerian market articles
    NIGERIAN_MARKET = {
        'ngx_basics': KnowledgeArticle(
            id='ngx_basics',
            title='Understanding the Nigerian Stock Exchange (NGX)',
            category=ContentCategory.NIGERIAN_MARKET,
            summary='An introduction to the Nigerian Exchange Group and how it works.',
            content='''
## About the Nigerian Exchange Group (NGX)

The Nigerian Exchange Group (formerly Nigerian Stock Exchange) is the primary stock exchange in Nigeria, with over 150 listed companies.

## Trading Hours

- **Pre-Open**: 9:30 AM - 10:00 AM WAT
- **Market Open**: 10:00 AM - 2:30 PM WAT
- **Closing Auction**: 2:30 PM - 2:45 PM WAT

## Key Characteristics

1. **Settlement**: T+2 (trades settle 2 business days after execution)
2. **Price Limits**: Stocks can move maximum ±10% per day
3. **Currency**: All trades in Nigerian Naira (₦)
4. **Sectors**: Banking dominates trading, followed by Consumer Goods and Industrials

## Major Indices

- **All-Share Index (ASI)**: Tracks all listed stocks
- **NGX 30**: Top 30 most liquid stocks
- **NGX Banking**: Banking sector index
- **NGX Consumer Goods**: Consumer goods sector index
''',
            nigerian_context=None,
            related_articles=['liquidity_ngx', 'sectors_ngx', 'dividends_ngx'],
            difficulty='beginner',
            read_time_minutes=4
        ),
        
        'liquidity_ngx': KnowledgeArticle(
            id='liquidity_ngx',
            title='Understanding Liquidity on the NGX',
            category=ContentCategory.NIGERIAN_MARKET,
            summary='Why liquidity matters and how to avoid illiquidity traps.',
            content='''
## What is Liquidity?

Liquidity refers to how easily you can buy or sell a stock without significantly affecting its price.

## Liquidity on the NGX

The Nigerian market has unique liquidity challenges:

- **Top 10 stocks**: Account for ~70% of daily trading value
- **Many stocks**: Trade less than ₦5 million per day
- **Some stocks**: Don't trade for days at a time

## Liquidity Categories

1. **High Liquidity**: DANGCEM, MTNN, GTCO, ZENITHBANK, ACCESSCORP
   - Daily value: ₦100M+
   - Easy to enter/exit

2. **Medium Liquidity**: Most banking and consumer goods stocks
   - Daily value: ₦10M - ₦100M
   - May take 1-2 days for large orders

3. **Low Liquidity**: Smaller stocks
   - Daily value: <₦10M
   - Difficult to exit quickly

## How to Protect Yourself

1. **Check Volume**: Before buying, check average daily value
2. **Size Positions**: Never buy more than 1 day's average volume
3. **Use Limits**: Always use limit orders, not market orders
4. **Be Patient**: Exit illiquid positions gradually
''',
            nigerian_context=None,
            related_articles=['ngx_basics', 'position_sizing'],
            difficulty='beginner',
            read_time_minutes=5
        ),
        
        'dividends_ngx': KnowledgeArticle(
            id='dividends_ngx',
            title='Dividends on the Nigerian Stock Exchange',
            category=ContentCategory.NIGERIAN_MARKET,
            summary='How Nigerian dividends work and why they matter.',
            content='''
## Dividends in Nigeria

Nigerian stocks are known for attractive dividend yields, often 5-15% annually.

## Types of Dividends

1. **Interim Dividend**: Paid during the year (usually after H1 results)
2. **Final Dividend**: Paid after full-year results (usually Q1 of following year)
3. **Special Dividend**: One-time extra dividends

## Key Dates

- **Declaration Date**: Company announces dividend
- **Qualification Date**: You must own shares by this date
- **Ex-Dividend Date**: First day shares trade without dividend right
- **Payment Date**: Dividend is paid to shareholders

## Important Notes

- **Withholding Tax**: 10% tax is deducted at source
- **Payment Delays**: Some companies take weeks to pay after payment date
- **Share Price Drop**: On ex-dividend date, price typically drops by dividend amount
''',
            nigerian_context=None,
            related_articles=['ngx_basics', 'dividend_strategy'],
            difficulty='beginner',
            read_time_minutes=4
        )
    }
    
    # Risk warnings
    RISK_WARNINGS = {
        'pump_dump': KnowledgeArticle(
            id='pump_dump',
            title='Warning: Pump and Dump Schemes',
            category=ContentCategory.RISK_WARNING,
            summary='How to identify and avoid stock manipulation schemes.',
            content='''
## What is a Pump and Dump?

A pump and dump is when promoters artificially inflate a stock price through misleading information, then sell their shares at the peak, leaving other investors with losses.

## Red Flags

1. **Sudden price spikes** in previously quiet stocks
2. **Social media hype** without fundamental news
3. **Penny stocks** under ₦1 with sudden volume
4. **Vague promises** of huge returns
5. **Pressure to buy immediately**

## How to Protect Yourself

- Research the company fundamentals
- Be skeptical of unsolicited tips
- Check if there's real news justifying the move
- Never invest based on WhatsApp or social media tips
- If it sounds too good to be true, it is
''',
            nigerian_context='''
Pump and dump schemes are common in low-liquidity Nigerian stocks. The small market size makes it easy for coordinated groups to move prices.

**Be especially careful with:**
- Stocks priced under ₦1
- Stocks that don't trade for days then suddenly spike
- "Hot tips" on WhatsApp or Telegram groups
''',
            related_articles=['liquidity_ngx', 'due_diligence'],
            difficulty='beginner',
            read_time_minutes=3
        )
    }
    
    def __init__(self):
        self._all_articles = {}
        self._all_articles.update(self.INDICATORS)
        self._all_articles.update(self.NIGERIAN_MARKET)
        self._all_articles.update(self.RISK_WARNINGS)
    
    def get_article(self, article_id: str) -> Optional[KnowledgeArticle]:
        """Get a specific article by ID."""
        return self._all_articles.get(article_id)
    
    def get_articles_by_category(
        self, category: ContentCategory
    ) -> List[KnowledgeArticle]:
        """Get all articles in a category."""
        return [
            a for a in self._all_articles.values()
            if a.category == category
        ]
    
    def get_all_articles(self) -> List[KnowledgeArticle]:
        """Get all articles."""
        return list(self._all_articles.values())
    
    def search(self, query: str) -> List[KnowledgeArticle]:
        """Search articles by keyword."""
        query = query.lower()
        results = []
        for article in self._all_articles.values():
            if (query in article.title.lower() or
                query in article.summary.lower() or
                query in article.content.lower()):
                results.append(article)
        return results
    
    def get_indicator_explanation(
        self, indicator: str
    ) -> Optional[Dict[str, Any]]:
        """Get contextual explanation for an indicator."""
        article = self.INDICATORS.get(indicator.lower())
        if article:
            return {
                'title': article.title,
                'summary': article.summary,
                'content': article.content,
                'nigerian_context': article.nigerian_context,
                'difficulty': article.difficulty,
                'read_time': article.read_time_minutes
            }
        return None
    
    def get_nigerian_context(self, topic: str) -> Optional[str]:
        """Get Nigerian market context for a topic."""
        article = self._all_articles.get(topic)
        if article and article.nigerian_context:
            return article.nigerian_context
        
        # Check indicators
        indicator_article = self.INDICATORS.get(topic.lower())
        if indicator_article and indicator_article.nigerian_context:
            return indicator_article.nigerian_context
        
        return None
