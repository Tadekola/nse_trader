"""
NSE Trader API - Main Application

A comprehensive Nigerian Stock Exchange trading analysis platform.
"""
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import API routers
from app.api.v1.stocks import router as stocks_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.market import router as market_router
from app.api.v1.performance import router as performance_router
from app.api.v1.health import router as health_router
from app.api.v1.ui import router as ui_router
from app.api.v1.audit import router as audit_router
from app.api.v1.total_return import router as total_return_router
from app.api.v1.portfolios import router as portfolios_router
from app.api.v1.scanner import router as scanner_router
from app.middleware.provenance import ProvenanceEnforcementMiddleware
from app.middleware.auth import require_api_key
from app.core.config import get_settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiter (keyed by remote address)
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting up NSE Trader API v2.0...")

    # Initialize PostgreSQL tables
    from app.db.engine import init_db, close_db
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        logger.warning("Continuing without persistent DB — audit trail will be unavailable")

    yield

    logger.info("Shutting down NSE Trader API...")
    try:
        await close_db()
    except Exception as e:
        logger.error("Database shutdown error: %s", e)


app = FastAPI(
    redirect_slashes=False,
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

# ── Rate limiting ──────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS — whitelist origins from config ───────────────────────────
_settings = get_settings()
_allowed_origins = [o.strip() for o in _settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Provenance completeness enforcement (P3-3)
# Temporarily disabled — middleware body consumption breaks ASGI streaming
# on Windows, causing ConnectionResetError for Next.js proxy requests.
# TODO: Re-enable after fixing middleware to use background body inspection.
# app.add_middleware(ProvenanceEnforcementMiddleware)


# ── Protected routers (require API key in non-dev) ────────────────
_auth = [Depends(require_api_key)]
app.include_router(stocks_router, prefix="/api/v1", dependencies=_auth)
app.include_router(recommendations_router, prefix="/api/v1", dependencies=_auth)
app.include_router(knowledge_router, prefix="/api/v1", dependencies=_auth)
app.include_router(market_router, prefix="/api/v1", dependencies=_auth)
app.include_router(performance_router, prefix="/api/v1", dependencies=_auth)
app.include_router(ui_router, prefix="/api/v1", dependencies=_auth)
app.include_router(audit_router, prefix="/api/v1", dependencies=_auth)
app.include_router(total_return_router, prefix="/api/v1", dependencies=_auth)
app.include_router(portfolios_router, prefix="/api/v1", dependencies=_auth)
app.include_router(scanner_router, prefix="/api/v1", dependencies=_auth)

# ── Public routers (no auth required) ─────────────────────────────
app.include_router(health_router, prefix="/api/v1")


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
