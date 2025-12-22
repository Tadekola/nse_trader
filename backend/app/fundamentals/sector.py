"""
Sector Analysis and Rotation for NSE Trader.

Provides sector-level analysis and rotation signals for the Nigerian market.
"""
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class SectorTrend(str, Enum):
    """Sector trend classification."""
    LEADING = "leading"       # Outperforming market
    IMPROVING = "improving"   # Gaining momentum
    LAGGING = "lagging"       # Underperforming
    WEAKENING = "weakening"   # Losing momentum


@dataclass
class SectorMetrics:
    """Metrics for a market sector."""
    name: str
    stock_count: int
    total_market_cap: float
    
    # Performance
    change_1d: float
    change_1w: float
    change_1m: float
    change_ytd: float
    
    # Relative strength
    relative_strength_vs_asi: float
    trend: SectorTrend
    
    # Breadth
    advancing: int
    declining: int
    unchanged: int
    breadth_ratio: float
    
    # Volume
    total_volume: int
    volume_vs_avg: float
    
    # Top movers
    top_gainer: Optional[str]
    top_loser: Optional[str]
    most_active: Optional[str]


@dataclass
class SectorRotationSignal:
    """Sector rotation recommendation."""
    from_sector: str
    to_sector: str
    confidence: float
    reasoning: str
    timeframe: str


class SectorAnalyzer:
    """
    Analyzes Nigerian market sectors and provides rotation signals.
    
    Nigerian market sectors:
    - Financial Services (dominant, ~40% of trading)
    - Consumer Goods
    - Industrial Goods
    - Oil & Gas
    - ICT (growing, high market cap)
    - Conglomerates
    - Agriculture
    """
    
    SECTORS = [
        'Financial Services',
        'Consumer Goods', 
        'Industrial Goods',
        'Oil & Gas',
        'ICT',
        'Conglomerates',
        'Agriculture',
        'Healthcare',
        'Services'
    ]
    
    # Sector characteristics for Nigerian market
    SECTOR_CHARACTERISTICS = {
        'Financial Services': {
            'drivers': ['interest_rates', 'loan_growth', 'npl_ratio', 'regulatory'],
            'leading_stocks': ['GTCO', 'ZENITHBANK', 'ACCESSCORP', 'UBA', 'FBNH'],
            'typical_pe_range': (3, 8),
            'typical_yield_range': (6, 15),
            'cyclicality': 'moderate',
            'fx_sensitivity': 'moderate',
            'weight_in_market': 0.25
        },
        'Consumer Goods': {
            'drivers': ['inflation', 'consumer_spending', 'fx_rate', 'input_costs'],
            'leading_stocks': ['NESTLE', 'DANGSUGAR', 'FLOURMILL', 'NB', 'GUINNESS'],
            'typical_pe_range': (8, 20),
            'typical_yield_range': (3, 8),
            'cyclicality': 'low',
            'fx_sensitivity': 'high',
            'weight_in_market': 0.15
        },
        'Industrial Goods': {
            'drivers': ['infrastructure_spend', 'construction', 'cement_demand'],
            'leading_stocks': ['DANGCEM', 'BUACEMENT', 'WAPCO'],
            'typical_pe_range': (6, 15),
            'typical_yield_range': (3, 7),
            'cyclicality': 'high',
            'fx_sensitivity': 'moderate',
            'weight_in_market': 0.20
        },
        'Oil & Gas': {
            'drivers': ['crude_price', 'refinery_capacity', 'subsidy_policy', 'production'],
            'leading_stocks': ['SEPLAT', 'OANDO', 'TOTAL', 'ARDOVA'],
            'typical_pe_range': (4, 12),
            'typical_yield_range': (4, 10),
            'cyclicality': 'high',
            'fx_sensitivity': 'high',
            'weight_in_market': 0.08
        },
        'ICT': {
            'drivers': ['subscriber_growth', 'data_revenue', 'tower_expansion', '5g_rollout'],
            'leading_stocks': ['MTNN', 'AIRTELAFRI'],
            'typical_pe_range': (8, 25),
            'typical_yield_range': (2, 6),
            'cyclicality': 'low',
            'fx_sensitivity': 'moderate',
            'weight_in_market': 0.25
        },
        'Conglomerates': {
            'drivers': ['economic_growth', 'diversification', 'management'],
            'leading_stocks': ['TRANSCORP', 'UACN'],
            'typical_pe_range': (5, 12),
            'typical_yield_range': (3, 8),
            'cyclicality': 'moderate',
            'fx_sensitivity': 'moderate',
            'weight_in_market': 0.05
        },
        'Agriculture': {
            'drivers': ['commodity_prices', 'weather', 'export_policy'],
            'leading_stocks': ['PRESCO', 'OKOMUOIL'],
            'typical_pe_range': (5, 12),
            'typical_yield_range': (2, 6),
            'cyclicality': 'moderate',
            'fx_sensitivity': 'moderate',
            'weight_in_market': 0.02
        }
    }
    
    def analyze_sector(
        self,
        sector_name: str,
        stocks_data: List[Dict[str, Any]],
        asi_performance: Dict[str, float]
    ) -> SectorMetrics:
        """Analyze a single sector."""
        if not stocks_data:
            return self._empty_sector_metrics(sector_name)
        
        # Calculate aggregates
        total_market_cap = sum(s.get('market_cap', 0) for s in stocks_data)
        total_volume = sum(s.get('volume', 0) for s in stocks_data)
        
        # Performance (weighted by market cap)
        weighted_change_1d = self._weighted_average(stocks_data, 'change_1d', 'market_cap')
        weighted_change_1w = self._weighted_average(stocks_data, 'change_1w', 'market_cap')
        weighted_change_1m = self._weighted_average(stocks_data, 'change_1m', 'market_cap')
        weighted_change_ytd = self._weighted_average(stocks_data, 'change_ytd', 'market_cap')
        
        # Relative strength vs ASI
        asi_change_1m = asi_performance.get('change_1m', 0)
        relative_strength = weighted_change_1m - asi_change_1m
        
        # Determine trend
        trend = self._determine_trend(relative_strength, weighted_change_1w, weighted_change_1m)
        
        # Breadth
        advancing = sum(1 for s in stocks_data if s.get('change_1d', 0) > 0)
        declining = sum(1 for s in stocks_data if s.get('change_1d', 0) < 0)
        unchanged = len(stocks_data) - advancing - declining
        breadth_ratio = advancing / len(stocks_data) if stocks_data else 0.5
        
        # Top movers
        sorted_by_change = sorted(stocks_data, key=lambda x: x.get('change_1d', 0), reverse=True)
        sorted_by_volume = sorted(stocks_data, key=lambda x: x.get('volume', 0), reverse=True)
        
        return SectorMetrics(
            name=sector_name,
            stock_count=len(stocks_data),
            total_market_cap=total_market_cap,
            change_1d=weighted_change_1d,
            change_1w=weighted_change_1w,
            change_1m=weighted_change_1m,
            change_ytd=weighted_change_ytd,
            relative_strength_vs_asi=relative_strength,
            trend=trend,
            advancing=advancing,
            declining=declining,
            unchanged=unchanged,
            breadth_ratio=breadth_ratio,
            total_volume=total_volume,
            volume_vs_avg=1.0,  # Would need historical data
            top_gainer=sorted_by_change[0].get('symbol') if sorted_by_change else None,
            top_loser=sorted_by_change[-1].get('symbol') if sorted_by_change else None,
            most_active=sorted_by_volume[0].get('symbol') if sorted_by_volume else None
        )
    
    def get_rotation_signals(
        self,
        sector_metrics: List[SectorMetrics]
    ) -> List[SectorRotationSignal]:
        """Generate sector rotation signals."""
        signals = []
        
        # Sort by relative strength
        sorted_sectors = sorted(
            sector_metrics,
            key=lambda x: x.relative_strength_vs_asi,
            reverse=True
        )
        
        # Identify leading and lagging sectors
        leading = [s for s in sorted_sectors if s.trend == SectorTrend.LEADING]
        lagging = [s for s in sorted_sectors if s.trend == SectorTrend.LAGGING]
        
        # Generate rotation signals
        for weak in lagging[:2]:
            for strong in leading[:2]:
                if weak.name != strong.name:
                    signals.append(SectorRotationSignal(
                        from_sector=weak.name,
                        to_sector=strong.name,
                        confidence=self._calculate_rotation_confidence(weak, strong),
                        reasoning=self._generate_rotation_reasoning(weak, strong),
                        timeframe="1-3 months"
                    ))
        
        return signals[:3]  # Top 3 signals
    
    def get_sector_recommendation(
        self,
        sector_name: str,
        metrics: SectorMetrics
    ) -> Dict[str, Any]:
        """Get recommendation for a sector."""
        characteristics = self.SECTOR_CHARACTERISTICS.get(sector_name, {})
        
        if metrics.trend == SectorTrend.LEADING:
            stance = "OVERWEIGHT"
            action = "Increase allocation"
        elif metrics.trend == SectorTrend.IMPROVING:
            stance = "NEUTRAL-OVERWEIGHT"
            action = "Consider adding on pullbacks"
        elif metrics.trend == SectorTrend.WEAKENING:
            stance = "NEUTRAL-UNDERWEIGHT"
            action = "Reduce exposure gradually"
        else:
            stance = "UNDERWEIGHT"
            action = "Minimize exposure"
        
        return {
            'sector': sector_name,
            'stance': stance,
            'action': action,
            'relative_strength': metrics.relative_strength_vs_asi,
            'breadth': metrics.breadth_ratio,
            'key_drivers': characteristics.get('drivers', []),
            'leading_stocks': characteristics.get('leading_stocks', []),
            'fx_sensitivity': characteristics.get('fx_sensitivity', 'unknown')
        }
    
    def _weighted_average(
        self,
        data: List[Dict],
        value_key: str,
        weight_key: str
    ) -> float:
        """Calculate weighted average."""
        total_weight = sum(d.get(weight_key, 0) for d in data)
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(
            d.get(value_key, 0) * d.get(weight_key, 0)
            for d in data
        )
        return weighted_sum / total_weight
    
    def _determine_trend(
        self,
        relative_strength: float,
        change_1w: float,
        change_1m: float
    ) -> SectorTrend:
        """Determine sector trend."""
        if relative_strength > 3 and change_1w > 0:
            return SectorTrend.LEADING
        elif relative_strength > 0 and change_1w > change_1m / 4:
            return SectorTrend.IMPROVING
        elif relative_strength < -3 and change_1w < 0:
            return SectorTrend.LAGGING
        elif relative_strength < 0 and change_1w < change_1m / 4:
            return SectorTrend.WEAKENING
        return SectorTrend.IMPROVING if change_1w > 0 else SectorTrend.WEAKENING
    
    def _calculate_rotation_confidence(
        self,
        weak: SectorMetrics,
        strong: SectorMetrics
    ) -> float:
        """Calculate confidence in rotation signal."""
        # Based on relative strength difference and breadth
        rs_diff = strong.relative_strength_vs_asi - weak.relative_strength_vs_asi
        breadth_diff = strong.breadth_ratio - weak.breadth_ratio
        
        confidence = 50  # Base
        confidence += min(rs_diff * 3, 25)  # RS contribution
        confidence += min(breadth_diff * 30, 15)  # Breadth contribution
        
        return min(95, max(30, confidence))
    
    def _generate_rotation_reasoning(
        self,
        weak: SectorMetrics,
        strong: SectorMetrics
    ) -> str:
        """Generate reasoning for rotation."""
        return (
            f"{strong.name} is outperforming with {strong.relative_strength_vs_asi:.1f}% "
            f"relative strength and {strong.breadth_ratio*100:.0f}% positive breadth. "
            f"{weak.name} is lagging with {weak.relative_strength_vs_asi:.1f}% relative strength."
        )
    
    def _empty_sector_metrics(self, name: str) -> SectorMetrics:
        """Return empty sector metrics."""
        return SectorMetrics(
            name=name, stock_count=0, total_market_cap=0,
            change_1d=0, change_1w=0, change_1m=0, change_ytd=0,
            relative_strength_vs_asi=0, trend=SectorTrend.LAGGING,
            advancing=0, declining=0, unchanged=0, breadth_ratio=0.5,
            total_volume=0, volume_vs_avg=0,
            top_gainer=None, top_loser=None, most_active=None
        )
