"""
NSE Trader API - Main Application

A comprehensive Nigerian Stock Exchange trading analysis platform.
"""
from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
from fastapi.middleware.cors import CORSMiddleware

# Import API routers
from app.api.v1.stocks import router as stocks_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.knowledge import router as knowledge_router

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting up NSE Trader API v2.0...")
    logger.info("Initializing services...")
    # Initialize services, connections, etc.
    yield
    logger.info("Shutting down NSE Trader API...")
    # Cleanup


app = FastAPI(
    title="NSE Trader API",
    description="""
## NSE Trader - Nigerian Stock Exchange Trading Platform

A comprehensive stock analysis and recommendation platform designed specifically 
for the Nigerian market.

### Features

- **Real-time Stock Data**: Live prices from TradingView
- **Multi-layer Recommendations**: Intelligent buy/sell signals with explanations
- **Market Regime Detection**: Bull, bear, range-bound market identification
- **Risk Assessment**: Volatility, drawdown, and position sizing guidance
- **Liquidity Scoring**: Critical for Nigerian market conditions
- **Educational Content**: Knowledge base for investor education

### API Sections

- **Stocks**: Market data, prices, and technical indicators
- **Recommendations**: AI-powered trading recommendations
- **Knowledge Base**: Educational articles and learning paths
""",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware - Allow all origins in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API routers
app.include_router(stocks_router, prefix="/api/v1")
app.include_router(recommendations_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")


@app.get("/", tags=["Health Check"])
def read_root():
    """API root endpoint."""
    return {
        "name": "NSE Trader API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "stocks": "/api/v1/stocks",
            "recommendations": "/api/v1/recommendations",
            "knowledge": "/api/v1/knowledge"
        }
    }


@app.get("/health", tags=["Health Check"])
async def health_check():
    """Check if the API is running and healthy."""
    return {
        "status": "ok",
        "version": "2.0.0",
        "services": {
            "api": "running",
            "tradingview": "available"
        }
    }


@app.get("/api/v1", tags=["API Info"])
def api_info():
    """Get API version and available endpoints."""
    return {
        "version": "1.0",
        "endpoints": {
            "stocks": {
                "list": "GET /api/v1/stocks",
                "detail": "GET /api/v1/stocks/{symbol}",
                "indicators": "GET /api/v1/stocks/{symbol}/indicators",
                "market_summary": "GET /api/v1/stocks/market-summary"
            },
            "recommendations": {
                "list": "GET /api/v1/recommendations",
                "buy": "GET /api/v1/recommendations/buy",
                "sell": "GET /api/v1/recommendations/sell",
                "detail": "GET /api/v1/recommendations/{symbol}",
                "market_regime": "GET /api/v1/recommendations/market-regime"
            },
            "knowledge": {
                "articles": "GET /api/v1/knowledge/articles",
                "lessons": "GET /api/v1/knowledge/lessons",
                "paths": "GET /api/v1/knowledge/paths"
            }
        }
    }
