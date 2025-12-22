# NSE Trader Stock Universe Contract

## Universe Definition

**Name:** Most Active / Tradable Nigerian Stocks  
**Type:** Curated Subset  
**Source:** Hardcoded registry in `app/data/sources/ngx_stocks.py`

## Current Universe Size

**Total Stocks: 41**

This is BY DESIGN. The Nigerian Exchange (NGX) has ~150+ listed equities, but this application intentionally tracks only the most actively traded stocks.

## Inclusion Criteria

Stocks are included in the universe based on:

1. **Market Capitalization**: Stocks with significant market cap (typically >₦30B)
2. **Trading Activity**: Stocks that trade regularly on the NGX
3. **Liquidity**: Stocks where investors can realistically enter/exit positions
4. **Data Availability**: Stocks with reliable price data

## Liquidity Tiers

| Tier | Description | Typical Volume | Count |
|------|-------------|----------------|-------|
| High | Blue chips, very liquid | >5M shares/day | ~10 |
| Medium | Actively traded | 500K-5M shares/day | ~15 |
| Low | Less liquid but tradable | 50K-500K shares/day | ~16 |

## Sector Coverage

| Sector | Stocks |
|--------|--------|
| Financial Services | 13 |
| Consumer Goods | 10 |
| Oil & Gas | 5 |
| Industrial Goods | 3 |
| Construction | 1 |
| Conglomerates | 2 |
| ICT | 2 |
| Services | 2 |
| Agriculture | 2 |

## Data Sources (Priority Order)

1. **TradingView** (Primary) - Real-time prices when available
2. **Simulated** (Fallback) - Derived from market cap when TradingView is rate-limited
3. **Registry** (Static) - Company info, sector, market cap

## What This Universe Is NOT

- ❌ Not all NGX-listed equities
- ❌ Not dynamically filtered based on real-time criteria
- ❌ Not limited by API rate limits (simulated fallback ensures all 41 always shown)
- ❌ Not a sample or demo dataset

## Verification

To verify universe integrity:

```bash
# Backend: Check registry size
curl http://localhost:8001/api/v1/stocks/ | jq '.count'
# Expected: 41

# Frontend: Check displayed count
# UI should show "41 of 41 stocks" in screener
```

## Expanding the Universe

To add more stocks:

1. Edit `app/data/sources/ngx_stocks.py`
2. Add new `StockInfo` entry with:
   - Symbol, name, sector
   - Market cap (billions)
   - Shares outstanding
   - Liquidity tier
3. Restart backend

## Contract Enforcement

- Backend returns ALL 41 stocks from registry
- No filtering removes stocks due to missing data
- Simulated prices ensure all stocks have displayable data
- Frontend displays full count without truncation

---

**Last Updated:** 2025-12-22  
**Contract Version:** 1.0
