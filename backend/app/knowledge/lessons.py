"""
Learning Paths and Lessons for NSE Trader.

Structured educational content for different user levels.
"""
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum


class LessonLevel(str, Enum):
    """Lesson difficulty level."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


@dataclass
class Lesson:
    """A single lesson in a learning path."""
    id: str
    title: str
    level: LessonLevel
    description: str
    content: str
    quiz_questions: List[Dict] = field(default_factory=list)
    estimated_minutes: int = 5
    prerequisites: List[str] = field(default_factory=list)


@dataclass
class LearningPath:
    """A structured learning path with multiple lessons."""
    id: str
    title: str
    description: str
    target_audience: str
    lessons: List[str]  # Lesson IDs in order
    estimated_hours: float


class LessonManager:
    """
    Manages educational lessons and learning paths.
    """
    
    LESSONS = {
        # Beginner lessons
        'intro_stock_market': Lesson(
            id='intro_stock_market',
            title='Introduction to the Stock Market',
            level=LessonLevel.BEGINNER,
            description='Learn what stocks are and how the stock market works.',
            content='''
# What is a Stock?

A stock represents ownership in a company. When you buy a stock, you become a part-owner of that company.

## Why Companies Issue Stocks

Companies sell stocks to raise money (capital) for:
- Expanding their business
- Developing new products
- Paying off debt
- Funding operations

## How You Make Money

1. **Capital Appreciation**: Stock price increases, you sell for a profit
2. **Dividends**: Company shares profits with shareholders

## The Stock Exchange

A stock exchange is a marketplace where stocks are bought and sold. In Nigeria, the main exchange is the **Nigerian Exchange Group (NGX)**.

## Key Terms

- **Bull Market**: Market is going up
- **Bear Market**: Market is going down
- **Portfolio**: Collection of your investments
- **Broker**: Company that executes your trades
''',
            quiz_questions=[
                {
                    'question': 'What does owning a stock mean?',
                    'options': [
                        'You loaned money to the company',
                        'You own a part of the company',
                        'You work for the company',
                        'You can control the company'
                    ],
                    'correct': 1
                },
                {
                    'question': 'What are the two main ways to make money from stocks?',
                    'options': [
                        'Fees and commissions',
                        'Dividends and capital appreciation',
                        'Interest and bonuses',
                        'Salaries and wages'
                    ],
                    'correct': 1
                }
            ],
            estimated_minutes=10
        ),
        
        'understanding_price': Lesson(
            id='understanding_price',
            title='Understanding Stock Prices',
            level=LessonLevel.BEGINNER,
            description='Learn what determines stock prices and how to read price data.',
            content='''
# What Determines Stock Price?

Stock prices are determined by **supply and demand**:
- More buyers than sellers → Price goes UP
- More sellers than buyers → Price goes DOWN

## Price Data

When looking at stock data, you'll see:

- **Open**: First traded price of the day
- **High**: Highest price during the day
- **Low**: Lowest price during the day
- **Close**: Last traded price of the day
- **Volume**: Number of shares traded

## Price Change

Price change shows how much the stock moved:
- **Green/Positive**: Stock is UP from previous close
- **Red/Negative**: Stock is DOWN from previous close
- **Percentage**: How much in percentage terms

## Example

If DANGCEM opened at ₦350, went to ₦360 (high), dropped to ₦345 (low), and closed at ₦355:
- The stock gained ₦5 from open (₦355 - ₦350)
- That's about 1.4% gain
''',
            quiz_questions=[
                {
                    'question': 'What makes stock prices go up?',
                    'options': [
                        'Government decision',
                        'More buyers than sellers',
                        'Random chance',
                        'Company announcement'
                    ],
                    'correct': 1
                }
            ],
            estimated_minutes=8,
            prerequisites=['intro_stock_market']
        ),
        
        'intro_technical_analysis': Lesson(
            id='intro_technical_analysis',
            title='Introduction to Technical Analysis',
            level=LessonLevel.BEGINNER,
            description='Learn the basics of reading charts and using technical indicators.',
            content='''
# What is Technical Analysis?

Technical analysis is the study of past price and volume data to predict future price movements.

## Core Principles

1. **Price discounts everything**: All known information is reflected in price
2. **Price moves in trends**: Once a trend starts, it tends to continue
3. **History repeats**: Price patterns tend to repeat over time

## Types of Charts

1. **Line Chart**: Simple, shows closing prices
2. **Candlestick Chart**: Shows open, high, low, close - most popular
3. **Bar Chart**: Similar to candlestick, different visual

## Key Concepts

- **Support**: Price level where buyers tend to enter
- **Resistance**: Price level where sellers tend to exit
- **Trend**: Overall direction of price movement
- **Volume**: Confirms the strength of price moves

## Starting Out

Begin by learning to:
1. Identify the overall trend (up, down, sideways)
2. Find key support and resistance levels
3. Confirm moves with volume
''',
            estimated_minutes=12,
            prerequisites=['understanding_price']
        ),
        
        'reading_rsi': Lesson(
            id='reading_rsi',
            title='How to Use RSI',
            level=LessonLevel.INTERMEDIATE,
            description='Master the Relative Strength Index indicator.',
            content='''
# RSI Deep Dive

RSI measures momentum on a 0-100 scale.

## Basic Signals

- **Below 30**: Oversold - potential buy
- **Above 70**: Overbought - potential sell
- **50 Line**: Above = bullish bias, Below = bearish bias

## Advanced Techniques

### Divergence

When price and RSI don't agree:
- **Bullish Divergence**: Price makes lower low, RSI makes higher low
- **Bearish Divergence**: Price makes higher high, RSI makes lower high

Divergences often precede reversals.

### RSI in Trends

In strong uptrends:
- RSI can stay above 50 for extended periods
- Oversold readings (30-40) can be buying opportunities

In strong downtrends:
- RSI can stay below 50 for extended periods
- Overbought readings (60-70) can be selling opportunities

## Nigerian Market Tips

- On NGX, RSI extremes can persist in low-liquidity stocks
- Use 14-period RSI on daily charts
- Combine with volume for confirmation
''',
            estimated_minutes=15,
            prerequisites=['intro_technical_analysis']
        ),
        
        'risk_management': Lesson(
            id='risk_management',
            title='Risk Management Essentials',
            level=LessonLevel.BEGINNER,
            description='Learn to protect your capital with proper risk management.',
            content='''
# Why Risk Management Matters

Risk management is more important than finding winning trades. One big loss can wipe out many small wins.

## The 1% Rule

Never risk more than 1-2% of your portfolio on a single trade.

**Example**: If you have ₦1,000,000 portfolio:
- Max risk per trade: ₦10,000 - ₦20,000
- This determines your position size

## Position Sizing

Calculate position size based on your risk:

```
Position Size = Risk Amount / (Entry Price - Stop Loss)
```

**Example**: 
- Risk: ₦10,000
- Entry: ₦100
- Stop Loss: ₦95
- Position Size = ₦10,000 / ₦5 = 2,000 shares

## Stop-Loss Orders

A stop-loss is a predetermined exit point to limit losses:
- Set before entering the trade
- Never move stop-loss further away
- Typical stops: 5-10% below entry

## Diversification

Don't put all your eggs in one basket:
- Spread across different stocks
- Spread across different sectors
- Keep some cash reserve
''',
            estimated_minutes=15,
            prerequisites=['intro_stock_market']
        )
    }
    
    LEARNING_PATHS = {
        'beginner': LearningPath(
            id='beginner',
            title='Complete Beginner Path',
            description='Start from zero and learn the fundamentals of stock trading.',
            target_audience='New investors with no prior experience',
            lessons=[
                'intro_stock_market',
                'understanding_price',
                'risk_management',
                'intro_technical_analysis'
            ],
            estimated_hours=1.5
        ),
        'technical_analysis': LearningPath(
            id='technical_analysis',
            title='Technical Analysis Mastery',
            description='Learn to read charts and use technical indicators effectively.',
            target_audience='Investors who understand basics and want to time entries/exits',
            lessons=[
                'intro_technical_analysis',
                'reading_rsi'
            ],
            estimated_hours=1.0
        )
    }
    
    def __init__(self):
        pass
    
    def get_lesson(self, lesson_id: str) -> Optional[Lesson]:
        """Get a specific lesson."""
        return self.LESSONS.get(lesson_id)
    
    def get_lessons_by_level(self, level: LessonLevel) -> List[Lesson]:
        """Get all lessons at a specific level."""
        return [l for l in self.LESSONS.values() if l.level == level]
    
    def get_all_lessons(self) -> List[Lesson]:
        """Get all lessons."""
        return list(self.LESSONS.values())
    
    def get_learning_path(self, path_id: str) -> Optional[LearningPath]:
        """Get a specific learning path."""
        return self.LEARNING_PATHS.get(path_id)
    
    def get_all_paths(self) -> List[LearningPath]:
        """Get all learning paths."""
        return list(self.LEARNING_PATHS.values())
    
    def get_path_lessons(self, path_id: str) -> List[Lesson]:
        """Get all lessons in a path in order."""
        path = self.LEARNING_PATHS.get(path_id)
        if not path:
            return []
        return [self.LESSONS[lid] for lid in path.lessons if lid in self.LESSONS]
    
    def check_prerequisites(
        self, lesson_id: str, completed: List[str]
    ) -> tuple[bool, List[str]]:
        """Check if prerequisites are met for a lesson."""
        lesson = self.LESSONS.get(lesson_id)
        if not lesson:
            return False, []
        
        missing = [p for p in lesson.prerequisites if p not in completed]
        return len(missing) == 0, missing
    
    def get_next_lesson(
        self, path_id: str, completed: List[str]
    ) -> Optional[Lesson]:
        """Get the next lesson in a path based on completed lessons."""
        path = self.LEARNING_PATHS.get(path_id)
        if not path:
            return None
        
        for lesson_id in path.lessons:
            if lesson_id not in completed:
                return self.LESSONS.get(lesson_id)
        
        return None  # All lessons completed
    
    def calculate_progress(
        self, path_id: str, completed: List[str]
    ) -> Dict[str, Any]:
        """Calculate progress in a learning path."""
        path = self.LEARNING_PATHS.get(path_id)
        if not path:
            return {'error': 'Path not found'}
        
        total = len(path.lessons)
        done = len([l for l in path.lessons if l in completed])
        
        return {
            'path_id': path_id,
            'total_lessons': total,
            'completed_lessons': done,
            'progress_percent': (done / total * 100) if total > 0 else 0,
            'is_complete': done == total,
            'next_lesson': self.get_next_lesson(path_id, completed)
        }
