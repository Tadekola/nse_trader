"""
SQLAlchemy models for NSE Trader PostgreSQL persistence (G3).

Tables:
- ohlcv_prices: Daily OHLCV for stocks
- market_index: ASI daily values
- signals: Generated signal records
- no_trade_events: NO_TRADE decisions with reason codes
- audit_events: System-wide audit log
- source_health: Per-source health tracking
- corporate_actions: Dividends, splits, bonus issues (Milestone A)
- adjusted_prices: Split-adjusted close + Total Return Index (Milestone A)
- fx_rates: Daily FX rates (e.g. USDNGN) for multi-currency reporting (Milestone B)
- macro_series: Macro indicators (CPI) for inflation-adjusted reporting (Milestone B)
- portfolios: User portfolios with base currency (Milestone B)
- portfolio_transactions: Buy/sell/dividend/cash transactions (Milestone B)
"""

from datetime import datetime, date
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, String, Float, Integer, BigInteger, Date, DateTime,
    Boolean, Text, Index, UniqueConstraint, ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class ApiKey(Base):
    """
    API keys for beta authentication.

    Keys are stored as SHA-256 hashes. The plain-text key is shown
    once at creation time and never stored.
    """
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)  # human label, e.g. "dev-laptop"
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    scopes = Column(String(500), nullable=True)  # comma-separated, future use


class OHLCVPrice(Base):
    """Daily OHLCV price data for stocks."""
    __tablename__ = "ohlcv_prices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    ts = Column(Date, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False, default=0)
    source = Column(String(50), nullable=False, default="NGNMARKET_HISTORICAL")
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "ts", name="uq_ohlcv_symbol_ts"),
        Index("ix_ohlcv_symbol_ts_desc", "symbol", ts.desc()),
    )


class MarketIndex(Base):
    """Market index (ASI) daily values."""
    __tablename__ = "market_index"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(20), nullable=False, default="ASI", index=True)
    ts = Column(Date, nullable=False)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=True)
    source = Column(String(50), nullable=False, default="NGNMARKET_HISTORICAL")
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("name", "ts", name="uq_market_index_name_ts"),
        Index("ix_market_index_name_ts_desc", "name", ts.desc()),
    )


class Signal(Base):
    """Generated trading signal records."""
    __tablename__ = "signals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    signal_id = Column(String(64), nullable=False, unique=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    as_of = Column(DateTime, nullable=False)
    strategy = Column(String(50), nullable=False)
    horizon = Column(String(20), nullable=False)
    direction = Column(String(20), nullable=False)  # bullish/neutral/bearish
    confidence = Column(Float, nullable=False)
    bias_probability = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE/SUPPRESSED/INVALID/NO_TRADE
    params = Column(JSONB, nullable=True)
    provenance = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_signals_symbol_as_of", "symbol", as_of.desc()),
        Index("ix_signals_status", "status"),
    )


class NoTradeEvent(Base):
    """NO_TRADE decisions with full provenance."""
    __tablename__ = "no_trade_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    scope = Column(String(20), nullable=False, default="symbol")  # symbol | market | system
    symbol = Column(String(20), nullable=True, index=True)
    reason_code = Column(String(50), nullable=False)
    detail = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    provenance = Column(JSONB, nullable=True)


class AuditEvent(Base):
    """System-wide audit log."""
    __tablename__ = "audit_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    component = Column(String(50), nullable=False, index=True)
    level = Column(String(10), nullable=False, default="INFO")  # DEBUG/INFO/WARN/ERROR
    event_type = Column(String(50), nullable=False, index=True)
    message = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=True)


class SourceHealth(Base):
    """Per-source health tracking for operational visibility (P1-3)."""
    __tablename__ = "source_health"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True, index=True)
    last_success = Column(DateTime, nullable=True)
    last_error = Column(DateTime, nullable=True)
    last_error_message = Column(Text, nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    total_calls = Column(Integer, nullable=False, default=0)
    total_failures = Column(Integer, nullable=False, default=0)
    error_rate = Column(Float, nullable=False, default=0.0)
    stale_count = Column(Integer, nullable=False, default=0)
    circuit_state = Column(String(20), nullable=False, default="CLOSED")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CorporateAction(Base):
    """
    Corporate actions: dividends, splits, bonus issues (Milestone A).

    action_type values:
      CASH_DIVIDEND  — cash dividend per share (amount in NGN)
      STOCK_SPLIT    — ratio_from:ratio_to (e.g. 1:2 means 1 old → 2 new)
      BONUS_ISSUE    — ratio_from:ratio_to (e.g. 1:10 means 1 bonus per 10 held)
      RIGHTS_ISSUE   — future use
      SUSPENSION     — future use
    """
    __tablename__ = "corporate_actions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    action_type = Column(String(30), nullable=False, index=True)
    ex_date = Column(Date, nullable=False, index=True)
    record_date = Column(Date, nullable=True)
    payment_date = Column(Date, nullable=True)
    amount = Column(Float, nullable=True)          # dividend per share (NGN)
    ratio_from = Column(Integer, nullable=True)    # split/bonus: old shares
    ratio_to = Column(Integer, nullable=True)      # split/bonus: new shares
    currency = Column(String(5), nullable=False, default="NGN")
    source = Column(String(50), nullable=False)
    confidence = Column(String(10), nullable=False, default="HIGH")  # HIGH/MEDIUM/LOW
    notes = Column(Text, nullable=True)
    artifact_ref = Column(String(255), nullable=True)
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    provenance = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "action_type", "ex_date",
                         name="uq_corp_action_symbol_type_exdate"),
        Index("ix_corp_action_symbol_exdate", "symbol", ex_date.desc()),
    )


class AdjustedPrice(Base):
    """
    Split-adjusted close + Total Return Index per symbol per day (Milestone A).

    tri_quality values:
      FULL        — both price and dividend data available
      PRICE_ONLY  — no dividend data; TRI = price return only
    """
    __tablename__ = "adjusted_prices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    ts = Column(Date, nullable=False)
    close_raw = Column(Float, nullable=False)
    adj_factor = Column(Float, nullable=False, default=1.0)
    adj_close = Column(Float, nullable=False)
    tri = Column(Float, nullable=False)
    daily_return_price = Column(Float, nullable=True)
    daily_return_total = Column(Float, nullable=True)
    tri_quality = Column(String(20), nullable=False, default="PRICE_ONLY")
    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    provenance = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "ts", name="uq_adj_price_symbol_ts"),
        Index("ix_adj_price_symbol_ts_desc", "symbol", ts.desc()),
    )


class FxRate(Base):
    """
    Daily FX rates for multi-currency reporting (Milestone B).

    Convention: pair = "USDNGN" means rate = NGN per 1 USD.
    All pairs stored as XXX/NGN (foreign currency per NGN amount).
    """
    __tablename__ = "fx_rates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    pair = Column(String(10), nullable=False, index=True)  # e.g. USDNGN, GBPNGN
    ts = Column(Date, nullable=False, index=True)
    rate = Column(Float, nullable=False)  # NGN per 1 unit of foreign currency
    source = Column(String(50), nullable=False)
    confidence = Column(String(10), nullable=False, default="HIGH")
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    provenance = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("pair", "ts", name="uq_fx_rate_pair_ts"),
        Index("ix_fx_rate_pair_ts_desc", "pair", ts.desc()),
    )


class MacroSeries(Base):
    """
    Macro economic indicators — CPI, etc. (Milestone B).

    frequency: DAILY, MONTHLY, QUARTERLY
    For monthly series (CPI), ts = first day of month. Forward-fill to daily
    is done in the service layer, not stored.
    """
    __tablename__ = "macro_series"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    series_name = Column(String(30), nullable=False, index=True)  # e.g. CPI_NGN
    ts = Column(Date, nullable=False, index=True)
    value = Column(Float, nullable=False)
    frequency = Column(String(10), nullable=False, default="MONTHLY")  # DAILY/MONTHLY/QUARTERLY
    source = Column(String(50), nullable=False)
    confidence = Column(String(10), nullable=False, default="HIGH")
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    provenance = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("series_name", "ts", name="uq_macro_series_name_ts"),
        Index("ix_macro_series_name_ts_desc", "series_name", ts.desc()),
    )


class Portfolio(Base):
    """
    User portfolio — a named container for transactions (Milestone B).

    base_currency: the reporting currency preference (NGN default).
    Reporting can always be done in any mode regardless of base_currency.
    """
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    base_currency = Column(String(5), nullable=False, default="NGN")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PortfolioTransaction(Base):
    """
    Portfolio transactions — buys, sells, dividends, cash flows (Milestone B).

    tx_type values:
      BUY       — purchase shares (quantity > 0, price_ngn > 0)
      SELL      — sell shares (quantity > 0, price_ngn > 0)
      DIVIDEND  — cash dividend received (amount_ngn > 0)
      CASH_IN   — deposit cash into portfolio
      CASH_OUT  — withdraw cash from portfolio
      FEE       — brokerage/regulatory fee
    """
    __tablename__ = "portfolio_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    ts = Column(Date, nullable=False, index=True)
    symbol = Column(String(20), nullable=True, index=True)  # NULL for CASH_IN/OUT
    tx_type = Column(String(20), nullable=False)  # BUY/SELL/DIVIDEND/CASH_IN/CASH_OUT/FEE
    quantity = Column(Float, nullable=True)        # shares for BUY/SELL
    price_ngn = Column(Float, nullable=True)       # per-share price for BUY/SELL
    amount_ngn = Column(Float, nullable=False)     # total NGN amount (positive=inflow, negative=outflow)
    fees_ngn = Column(Float, nullable=False, default=0.0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    provenance = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_ptx_portfolio_ts", "portfolio_id", ts.desc()),
        Index("ix_ptx_portfolio_symbol", "portfolio_id", "symbol"),
    )


# ═══════════════════════════════════════════════════════════════════════
# NGX Quality Scanner Models
# ═══════════════════════════════════════════════════════════════════════

class UniverseMember(Base):
    """
    Liquid universe membership — which symbols are eligible for scanning.

    Computed from OHLCV data (value_traded proxy = volume × close over N days).
    Can be overridden via SYMBOL_UNIVERSE env var.
    """
    __tablename__ = "universe_members"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    universe_name = Column(String(50), nullable=False, index=True)  # e.g. "top_liquid_50"
    as_of_date = Column(Date, nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    liquidity_score = Column(Float, nullable=False)
    avg_daily_value = Column(Float, nullable=True)       # avg(volume * close) over window
    zero_volume_days = Column(Integer, nullable=True)    # count of zero-vol days in window
    provenance = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "universe_name", "as_of_date",
                         name="uq_universe_member"),
        Index("ix_universe_name_date", "universe_name", as_of_date.desc()),
    )


class FundamentalsPeriodic(Base):
    """
    Periodic financial statements — one row per symbol per reporting period.

    period_type: ANNUAL or INTERIM (half-year / quarterly).
    All monetary values in NGN (millions optional, but be consistent per source).
    """
    __tablename__ = "fundamentals_periodic"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    period_end_date = Column(Date, nullable=False, index=True)
    period_type = Column(String(10), nullable=False, default="ANNUAL")  # ANNUAL | INTERIM
    currency = Column(String(5), nullable=False, default="NGN")

    # Income statement
    revenue = Column(Float, nullable=True)
    operating_profit = Column(Float, nullable=True)       # EBIT proxy
    net_income = Column(Float, nullable=True)

    # Balance sheet
    total_assets = Column(Float, nullable=True)
    total_equity = Column(Float, nullable=True)
    total_debt = Column(Float, nullable=True)
    cash = Column(Float, nullable=True)

    # Cash flow
    operating_cash_flow = Column(Float, nullable=True)
    capex = Column(Float, nullable=True)
    dividends_paid = Column(Float, nullable=True)         # total div paid in period

    # Shares
    shares_outstanding = Column(Float, nullable=True)     # in millions or units

    # Provenance
    source = Column(String(50), nullable=False)
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    provenance = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "period_end_date", "period_type", "source",
                         name="uq_fundamentals_periodic"),
        Index("ix_fund_periodic_symbol_date", "symbol", period_end_date.desc()),
    )


class FundamentalsDerived(Base):
    """
    Derived quality metrics — computed from FundamentalsPeriodic rows.

    One row per symbol per as_of_date (typically the latest period_end_date).
    """
    __tablename__ = "fundamentals_derived"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False, index=True)

    # Profitability
    roe = Column(Float, nullable=True)                    # net_income / equity
    roic_proxy = Column(Float, nullable=True)             # operating_profit / (equity + debt)
    op_margin = Column(Float, nullable=True)              # operating_profit / revenue
    net_margin = Column(Float, nullable=True)             # net_income / revenue

    # Balance sheet
    debt_to_equity = Column(Float, nullable=True)
    cash_to_debt = Column(Float, nullable=True)

    # Cash quality
    ocf_to_net_income = Column(Float, nullable=True)      # cash conversion ratio
    fcf = Column(Float, nullable=True)                    # ocf - capex

    # Stability (computed across multiple periods)
    earnings_stability = Column(Float, nullable=True)     # 1 - CoV(net_income)
    margin_stability = Column(Float, nullable=True)       # 1 - CoV(op_margin)

    # Composite
    quality_score = Column(Float, nullable=True)          # 0-100
    sub_scores = Column(JSONB, nullable=True)             # {"profitability":, "balance_sheet":, ...}
    reasons = Column(JSONB, nullable=True)                # human-readable list
    red_flags = Column(JSONB, nullable=True)              # list of warning strings
    data_freshness_days = Column(Integer, nullable=True)  # days since period_end_date
    periods_available = Column(Integer, nullable=True)    # how many periods used

    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    provenance = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_fundamentals_derived"),
        Index("ix_fund_derived_symbol_date", "symbol", as_of_date.desc()),
        Index("ix_fund_derived_score", quality_score.desc()),
    )


class ScanRun(Base):
    """
    Scanner execution record — one row per scan invocation.
    """
    __tablename__ = "scan_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    as_of_date = Column(Date, nullable=False, index=True)
    universe_name = Column(String(50), nullable=False)
    symbols_scanned = Column(Integer, nullable=False, default=0)
    symbols_ranked = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    summary = Column(JSONB, nullable=True)                # top-level metrics
    provenance = Column(JSONB, nullable=True)


class ScanResult(Base):
    """
    Per-symbol result from a scan run.
    """
    __tablename__ = "scan_results"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    quality_score = Column(Float, nullable=False)
    sub_scores = Column(JSONB, nullable=True)
    reasons = Column(JSONB, nullable=True)
    red_flags = Column(JSONB, nullable=True)
    flags = Column(JSONB, nullable=True)                  # {"liquidity_gated": false, "data_quality": "FULL"}
    liquidity_score = Column(Float, nullable=True)
    confidence_penalty = Column(Float, nullable=True, default=0.0)

    # Trailing returns (pre-computed for API speed)
    tri_1y_ngn = Column(Float, nullable=True)
    tri_3y_ngn = Column(Float, nullable=True)
    tri_1y_usd = Column(Float, nullable=True)
    tri_3y_usd = Column(Float, nullable=True)
    tri_1y_real = Column(Float, nullable=True)
    tri_3y_real = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "symbol", name="uq_scan_result_run_symbol"),
        Index("ix_scan_result_run_rank", "run_id", "rank"),
    )
