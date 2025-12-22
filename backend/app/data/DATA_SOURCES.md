# NSE Trader Data Sources

## Overview

NSE Trader uses a 3-tier data sourcing pipeline to ensure reliable stock price data even when primary sources are unavailable.

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Source Pipeline                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Tier 1: NGX Official ───► Real delayed prices (preferred)  │
│              │                                               │
│              ▼ (if unavailable)                              │
│  Tier 2: Apt Securities ───► Alternative real prices        │
│              │                                               │
│              ▼ (if unavailable)                              │
│  Tier 3: Simulated ───► Derived from market cap (⚠️ LAST    │
│                         RESORT - triggers warning banner)   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Tier 1: NGX Official Equities Price List

**Source:** Nigerian Exchange Group Official Website  
**URL:** `https://ngxgroup.com/exchange/data/equities-price-list/`  
**Provider:** `NgxEquitiesPriceListProvider`

### Characteristics
- **Delay:** 15-20 minutes during trading hours
- **Update Frequency:** Real-time during market hours
- **Coverage:** All NGX-listed equities
- **Authority:** Official exchange data

### Data Fields
| Field | Description |
|-------|-------------|
| `open` | Opening price |
| `high` | Day high |
| `low` | Day low |
| `close` | Current/closing price |
| `change` | Price change (₦) |
| `change_percent` | Percentage change |
| `volume` | Shares traded |
| `value` | Trading value (₦) |
| `trades` | Number of deals |

### Failure Modes
- Rate limiting (unlikely for HTML scraping)
- Website maintenance
- Network issues
- HTML structure changes

---

## Tier 2: Apt Securities Daily Price List

**Source:** Apt Securities Broker Website  
**URL:** `https://aptsecurities.com/ngx-daily-price-list/`  
**Provider:** `AptSecuritiesDailyPriceProvider`

### Characteristics
- **Delay:** End of day (updated after market close)
- **Update Frequency:** Daily
- **Coverage:** Most traded equities
- **Authority:** Broker-aggregated data

### Why This Source?
- Free public access
- No API key required
- No rate limits
- Reliable daily updates
- Covers all major stocks

### Failure Modes
- Website unavailable
- Table format changes
- Data not yet updated for current day

---

## Tier 3: Simulated Fallback

**Source:** Calculated from market cap and shares outstanding  
**Provider:** `SimulatedProvider`

### ⚠️ CRITICAL WARNING

**Simulated data is NOT real market data.**

When simulated data is used:
1. Frontend displays a **warning banner**
2. API response includes `is_simulated: true`
3. Affected symbols are listed in `simulated_symbols`

### How Simulation Works

```python
base_price = market_cap_billions * 1e9 / shares_outstanding
price = base_price * (1 + random_variation)  # ±3%
```

- Prices are derived from market capitalization
- Variation is deterministic (same within each hour)
- Volume based on liquidity tier
- OHLC generated with realistic intraday range

### When Simulation Is Used
- Tier 1 AND Tier 2 both unavailable
- Stock not covered by real data sources
- Network/parsing errors for a symbol

---

## Caching Strategy

### Cache Configuration
- **TTL:** 120 seconds (2 minutes) for Tier 1/2 data
- **Storage:** In-memory (Redis-ready interface)
- **Scope:** Per-symbol snapshots

### Cache Behavior
| Source | Cached? | TTL |
|--------|---------|-----|
| NGX Official | ✅ Yes | 120s |
| Apt Securities | ✅ Yes | 120s |
| Simulated | ❌ No | - |

Simulated data is never cached to ensure fresh calculations when real data becomes available.

---

## API Response Metadata

Every `/api/v1/stocks/` response includes:

```json
{
  "success": true,
  "count": 41,
  "data": [...],
  "source": "ngx_official",
  "meta": {
    "source_breakdown": {
      "ngx_official": 35,
      "apt_securities": 4,
      "simulated": 2
    },
    "is_simulated": true,
    "simulated_count": 2,
    "simulated_symbols": ["SYMBOL1", "SYMBOL2"],
    "last_updated": "2025-12-22T12:00:00.000Z",
    "fetch_time_ms": 1250.5
  }
}
```

### Frontend Behavior

When `is_simulated: true`:
- Display **SimulationWarningBanner** component
- Show affected symbol count
- List affected symbols (first 5)
- Display "Do NOT use for live trading decisions"

---

## Adding New Data Sources

To add a new data source:

1. Create provider in `app/market_data/providers/`
2. Implement `MarketDataProvider` interface
3. Set appropriate `tier` (lower = higher priority)
4. Add to `ProviderChain` in service initialization
5. Document in this file

### Provider Interface

```python
class MarketDataProvider(ABC):
    @property
    def name(self) -> str: ...
    
    @property
    def tier(self) -> int: ...
    
    @property
    def source(self) -> DataSource: ...
    
    async def fetch_snapshot(
        self, 
        symbols: List[str]
    ) -> FetchResult: ...
    
    def is_available(self) -> bool: ...
```

---

## Constraints

### What We Don't Use
- ❌ Paid APIs (Bloomberg, Refinitiv, etc.)
- ❌ API keys or authentication
- ❌ Aggressive scraping (>1 request/second)
- ❌ TradingView (rate-limited, unreliable)

### Rate Limiting
- NGX: No known limits for HTML access
- Apt Securities: No known limits
- Self-imposed: Max 1 batch request per 2 minutes (via caching)

---

## Troubleshooting

### All Data Simulated
1. Check internet connectivity
2. Verify NGX website is accessible
3. Check provider logs for errors
4. HTML structure may have changed (update parsers)

### Partial Simulation
- Normal for some symbols
- Some stocks may not be on alternative sources
- Check `simulated_symbols` in API response

### Stale Data
- Cache TTL is 2 minutes
- Force refresh: Call `service.clear_cache()`
- Check `last_updated` in response meta

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-22 | 1.0 | Initial 3-tier pipeline implementation |

---

**Document Version:** 1.0  
**Last Updated:** 2025-12-22
