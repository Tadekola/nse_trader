# NSE Trader Backend API v2.0

A comprehensive Nigerian Stock Exchange trading analysis and recommendation platform.

## Features

- **Real-time Stock Data**: Live prices from TradingView API
- **Multi-layer Recommendation Engine**: Intelligent buy/sell signals with explainable confidence
- **Market Regime Detection**: Bull, bear, range-bound, high-volatility market identification
- **Risk Assessment**: Volatility, drawdown, VaR, and position sizing guidance
- **Liquidity Scoring**: Critical for Nigerian market conditions
- **Fundamental Analysis**: P/E, dividend yield, sector rotation
- **Educational Content**: Knowledge base and learning paths for investor education

## Architecture

```
backend/
├── app/
│   ├── api/v1/                 # API endpoints
│   │   ├── stocks.py           # Stock data endpoints
│   │   ├── recommendations.py  # Recommendation endpoints
│   │   └── knowledge.py        # Knowledge base endpoints
│   ├── core/                   # Core business logic
│   │   ├── market_regime.py    # Market regime detection
│   │   ├── recommendation_engine.py  # Multi-layer recommendation engine
│   │   ├── risk_calculator.py  # Risk metrics calculation
│   │   └── explanation_generator.py  # Human-readable explanations
│   ├── data/                   # Data layer
│   │   └── sources/
│   │       ├── tradingview.py  # TradingView data source
│   │       └── ngx_stocks.py   # NGX stock registry
│   ├── fundamentals/           # Fundamental analysis
│   │   ├── valuation.py        # Valuation metrics
│   │   ├── dividends.py        # Dividend analysis
│   │   └── sector.py           # Sector rotation
│   ├── indicators/             # Technical indicators
│   │   ├── base.py             # Base indicator classes
│   │   ├── trend.py            # SMA, EMA, MACD
│   │   ├── momentum.py         # RSI, Stochastic, ADX
│   │   ├── volatility.py       # ATR, Bollinger Bands
│   │   ├── volume.py           # OBV, Volume Ratio, Liquidity
│   │   └── composite.py        # Composite indicators
│   ├── knowledge/              # Educational content
│   │   ├── base.py             # Knowledge articles
│   │   └── lessons.py          # Learning paths
│   ├── schemas/                # Pydantic models
│   │   ├── stock.py            # Stock schemas
│   │   ├── recommendation.py   # Recommendation schemas
│   │   ├── market.py           # Market schemas
│   │   └── user.py             # User schemas
│   ├── services/               # Business services
│   │   ├── market_data.py      # Market data service
│   │   └── recommendation.py   # Recommendation service
│   └── main.py                 # FastAPI application
└── pyproject.toml              # Dependencies
```

## Installation

```bash
cd backend
poetry install
```

## Running the API

```bash
# Development
poetry run uvicorn app.main:app --reload --port 8000

# Production
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### Stocks

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/stocks` | GET | Get all stocks |
| `/api/v1/stocks/{symbol}` | GET | Get stock details |
| `/api/v1/stocks/{symbol}/indicators` | GET | Get technical indicators |
| `/api/v1/stocks/market-summary` | GET | Get market summary |
| `/api/v1/stocks/search?q=` | GET | Search stocks |
| `/api/v1/stocks/sectors` | GET | Get all sectors |

### Recommendations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/recommendations` | GET | Get top recommendations |
| `/api/v1/recommendations/buy` | GET | Get buy recommendations |
| `/api/v1/recommendations/sell` | GET | Get sell recommendations |
| `/api/v1/recommendations/{symbol}` | GET | Get recommendation for stock |
| `/api/v1/recommendations/market-regime` | GET | Get market regime analysis |

### Knowledge Base

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/knowledge/articles` | GET | Get all articles |
| `/api/v1/knowledge/articles/{id}` | GET | Get specific article |
| `/api/v1/knowledge/lessons` | GET | Get all lessons |
| `/api/v1/knowledge/paths` | GET | Get learning paths |

## Recommendation Engine

The recommendation engine uses a multi-layer approach:

1. **Layer 1: Market Regime Detection**
   - Detects bull, bear, range-bound, high-volatility, low-liquidity, crisis modes
   - Adjusts all signals based on market conditions

2. **Layer 2: Technical Signal Analysis**
   - 11+ technical indicators with weighted scoring
   - Trend, momentum, volatility, and volume indicators

3. **Layer 3: Risk Assessment**
   - Volatility metrics (20d, 60d annualized)
   - Drawdown analysis
   - VaR calculations
   - Risk-adjusted position sizing

4. **Layer 4: Liquidity Filtering**
   - Critical for Nigerian market
   - Liquidity score 0-1
   - AVOID signals for illiquid stocks

5. **Layer 5: Time-Horizon Mapping**
   - Short-term (1-5 days)
   - Swing (1-4 weeks)
   - Long-term (3+ months)

6. **Layer 6: Explanation Generation**
   - Human-readable explanations
   - Tailored for beginner/intermediate/advanced users
   - Nigerian market context

## Nigerian Market Specifics

- **Liquidity Awareness**: Many NGX stocks trade <₦10M daily
- **Price Limits**: ±10% daily price limits
- **Dividend Focus**: High yields (5-15%) common
- **Sector Concentration**: Banking ~40% of trading
- **Settlement**: T+2

## Environment Variables

```env
REDIS_HOST=localhost
REDIS_PORT=6379
TRADINGVIEW_API_KEY=optional
```

## License

MIT
