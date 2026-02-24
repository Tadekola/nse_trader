# NSE Trader Backend API v2.0

A Nigerian Stock Exchange analysis platform providing market data, technical indicators,
and educational content for informed investment decisions.

> **⚠️ Important Disclaimer**: This system provides analytical tools and educational content only.
> It is NOT a trading bot, does NOT execute trades, and does NOT guarantee returns.
> All recommendations are probabilistic assessments, not financial advice.

## System Status & Data Integrity

Check system health via: `GET /api/v1/health/trust`

| Status | Meaning |
|--------|---------|
| `READY` | Performance metrics available from real data |
| `PARTIALLY_READY` | Some symbols have sufficient history |
| `NOT_READY` | Historical ingestion required |

### Key Principles

- **Forward-only metrics**: Performance is computed from real forward returns only, never backfilled
- **NO_TRADE is protective**: When data is insufficient, the system refuses to recommend rather than guess
- **Transparency first**: All limitations are disclosed in API responses
- **No simulation in production**: All data comes from validated sources

## Features

- **Real-time Stock Data**: Live prices from TradingView API
- **Technical Indicators**: RSI, SMA, EMA, MACD, Bollinger Bands (gated by data availability)
- **Market Regime Detection**: Bull, bear, range-bound, high-volatility identification
- **Risk Assessment**: Volatility metrics, position sizing guidance
- **Liquidity Scoring**: Critical for Nigerian market conditions
- **Performance Tracking**: Forward-only hit rate computation (requires historical data)
- **Educational Content**: Knowledge base and learning paths

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

## Understanding System Responses

### NO_TRADE Signals

When the system returns `NO_TRADE`, this is a **protective outcome**, not an error:

```json
{
  "signal_state": "NO_TRADE",
  "reason": "INSUFFICIENT_HISTORY",
  "explanation": {
    "what_this_means": "The system has insufficient evidence to justify a trade.",
    "user_action": "No action required. Wait for more data."
  }
}
```

### Performance Metrics

All performance metrics are:
- **Forward-only**: Computed from actual future returns after signals were generated
- **Never backfilled**: No historical simulation of "what would have happened"
- **Sample-size aware**: Returns `INSUFFICIENT_SAMPLE` when data is too sparse

### Data Sources

| Source | Type | Notes |
|--------|------|-------|
| TradingView | Live prices | Real-time market data |
| NGNMarket | Historical OHLCV | Validated, stored locally |
| Market Breadth | Estimated | Clearly labeled as heuristic |

## Limitations

This system has explicit limitations that are disclosed in API responses:

1. **Historical Data Required**: Technical indicators require 50+ trading sessions
2. **Forward Data Required**: Performance evaluation requires future price data
3. **Not Financial Advice**: All outputs are analytical tools, not recommendations to trade
4. **Nigerian Market Only**: Designed for NGX-listed securities
5. **No Trade Execution**: Analysis only - does not connect to brokers

## API Health Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/health/trust` | Full system trust status |
| `GET /api/v1/health/trust/banner` | Simplified banner for UI |
| `GET /api/v1/health/explain/{code}` | Educational explanation for status codes |
| `GET /api/v1/health/ping` | Simple liveness check |

## Performance Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/performance/status` | Check if metrics are available |
| `GET /api/v1/performance/summary` | Overall hit rates and returns |
| `GET /api/v1/performance/calibration` | Predicted vs actual accuracy |

## Environment Variables

```env
REDIS_HOST=localhost
REDIS_PORT=6379
TRADINGVIEW_API_KEY=optional
```

## Running Tests

```bash
# Run all tests
poetry run pytest

# Run specific phase tests
poetry run pytest tests/test_phase0_audit.py      # Data integrity
poetry run pytest tests/test_historical_coverage.py  # Indicator gating
poetry run pytest tests/test_ingestion_hardening.py  # Validation
poetry run pytest tests/test_performance_reenable.py # Performance tracking
```

## License

MIT

---

*This system is designed for educational and analytical purposes. 
Always conduct your own research before making investment decisions.*
