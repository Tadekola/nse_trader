# NSE Trader

A comprehensive real-time Nigerian Stock Exchange (NSE) trading analysis platform that provides market insights, trading signals, and investment recommendations based on validated data from multiple sources.

## Features

### Market Data
- Real-time market summary (NSE ASI, Market Cap, Volume, Value)
- Comprehensive stock data with validation from multiple sources (NGX, TradingView)
- Data quality indicators and validation metrics
- Auto-refreshing data (every minute)

### Investment Recommendations
- Most actively traded stocks tracking with sorting by volume
- Investment recommendations (Buy, Hold, Sell) with confidence metrics
- Detailed reasoning for each recommendation
- Technical analysis indicators and market sentiment

## Technical Stack

### Backend
- **Framework**: Python/Flask
- **Data Processing**: Pandas for technical analysis
- **Caching**: Redis for performance optimization
- **Reliability**: Circuit breaker pattern for API resilience
- **Validation**: Cross-source data verification system

### Frontend
- **UI**: HTML/CSS/JavaScript with responsive design
- **Visualization**: Visual indicators for recommendations and confidence
- **Interactivity**: Expandable details for each stock

### Data Sources
- Nigerian Exchange Group (NGX) simulated data
- TradingView Technical Analysis integration
- Multiple source validation for data accuracy

### Infrastructure
- **Dependency Management**: Poetry
- **Deployment**: Docker containerization
- **Testing**: Pytest for unit testing

## Project Structure

```
nse_trader/
├── app.py                  # Main Flask application & API endpoints
├── data_validator.py       # Multi-source data validation system
├── config/                 # Configuration settings
│   ├── config.py           # Environment and Redis configuration
│   └── settings.py         # Application settings
├── nse_trader/             # Core application code
│   ├── technical_analysis.py # Technical analysis and signal generation
│   └── other modules        # Additional core functionality
├── static/                 # Static assets
│   ├── css/                # Stylesheets
│   │   └── main.css        # Main CSS styling
│   └── js/                 # JavaScript modules
│       ├── ngx-market-data.js      # Market data handling
│       ├── validation-badges.js    # Data validation UI components
│       └── active-stocks.js        # Active stocks and recommendations
├── templates/              # HTML templates
│   └── index.html          # Main dashboard with tabbed interface
├── tests/                  # Unit tests
│   └── test_analysis.py    # Technical analysis tests
├── docker-compose.yml      # Docker deployment configuration
└── pyproject.toml         # Poetry dependency management
```

## Setup

### Local Development

1. Install Poetry (dependency management):
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Install dependencies:
```bash
poetry install
```

3. Run in development mode:
```bash
poetry run python app.py
```

### Production Deployment

1. Using Gunicorn (recommended):
```bash
poetry run gunicorn -c gunicorn_config.py app:app
```

2. Using Docker:
```bash
docker-compose up -d
```

### Optional: Redis Setup

Redis is used for caching and circuit breaker functionality. To enable Redis:

1. Start Redis (Docker):
```bash
docker run -d -p 6379:6379 --name redis redis:alpine
```

2. Or install Redis directly:
```bash
# Ubuntu/Debian
sudo apt-get install redis-server

# macOS
brew install redis
```

## Usage

### Key Features

1. **Most Actively Traded Stocks Tab**
   - Displays stocks sorted by trading volume
   - Shows investment recommendations (Buy/Hold/Sell)
   - Includes confidence metrics (0-100%)
   - Provides detailed reasoning for recommendations
   - Displays market sentiment indicators

2. **Market Data Tab**
   - Shows comprehensive market data for all tracked stocks
   - Includes validation badges showing data source reliability
   - Displays technical indicators and price information
   - Provides real-time market updates

3. **Data Validation**
   - Cross-references data from multiple sources
   - Shows validation accuracy indicators
   - Implements circuit breakers for reliability
   - Provides transparent source information

### Interacting with Recommendations

1. Click on any stock row to expand and view detailed information:
   - Complete list of recommendation reasons
   - Technical indicators behind the recommendation
   - Detailed stock information
   - Data sources and validation metrics

2. Use the confidence metric to gauge recommendation strength:
   - 80-100%: Strong confidence in the recommendation
   - 50-79%: Moderate confidence
   - Below 50%: Exercise caution

## Recommendation Methodology

The NSE Trader platform generates investment recommendations using a sophisticated multi-factor approach:

### Technical Indicators
- **Moving Averages**: Analyzes 50-day and 200-day SMAs and EMAs for trend direction
- **Relative Strength Index (RSI)**: Identifies overbought/oversold conditions
- **Bollinger Bands**: Detects price volatility and potential reversals
- **Volume Analysis**: Evaluates trading volume patterns for confirmation

### Confidence Calculation
- Based on agreement between multiple technical indicators
- Weighted by the strength of each signal
- Adjusted based on data validation accuracy
- Presented as a percentage (0-100%)

### Data Validation
- Cross-references data from multiple sources (NGX, TradingView)
- Calculates data accuracy based on source agreement
- Provides transparency about data sources for each recommendation
- Implements circuit breakers to prevent cascade failures

## Limitations

- Currently uses simulated/sample data for demonstration
- Will require API keys for live TradingView data
- Limited to Nigerian stocks covered by the data sources
- Technical analysis should be complemented with fundamental analysis

## Best Practices

- Check during Nigerian market hours (10:00 AM - 2:30 PM WAT)
- Use recommendations as part of a broader investment strategy
- Consider fundamental factors not captured in technical analysis
- Monitor multiple stocks for diversification
- Pay attention to the confidence metrics and validation accuracy
- Always conduct your own research before making investment decisions

## Future Enhancements

- **Live Data Integration**: Connect to official NGX API when available
- **Historical Analysis**: Add backtesting of recommendations
- **News Integration**: Incorporate relevant news that may impact stock performance
- **Fundamental Analysis**: Add key financial metrics and ratios
- **User Accounts**: Allow personalized watchlists and alerts
- **Mobile App**: Dedicated mobile application for on-the-go access
- **Advanced Filtering**: More criteria for finding investment opportunities
- **Predictive Analytics**: Machine learning models for price prediction

## License

Proprietary - All rights reserved

## Disclaimer

The investment recommendations provided by NSE Trader are for informational purposes only and do not constitute financial advice. Always consult with a qualified financial advisor before making investment decisions. The platform developers are not responsible for any losses incurred based on the information provided.