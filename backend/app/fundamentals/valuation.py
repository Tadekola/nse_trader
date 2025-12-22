"""
Valuation Analysis for NSE Trader.

Provides fundamental valuation metrics and analysis for Nigerian stocks.
"""
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum


class ValuationRating(str, Enum):
    """Valuation rating categories."""
    DEEPLY_UNDERVALUED = "deeply_undervalued"
    UNDERVALUED = "undervalued"
    FAIRLY_VALUED = "fairly_valued"
    OVERVALUED = "overvalued"
    DEEPLY_OVERVALUED = "deeply_overvalued"


@dataclass
class ValuationMetrics:
    """Complete valuation metrics for a stock."""
    symbol: str
    
    # Price ratios
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    ps_ratio: Optional[float]
    
    # Earnings metrics
    eps: Optional[float]
    eps_growth: Optional[float]
    
    # Dividend metrics
    dividend_yield: Optional[float]
    payout_ratio: Optional[float]
    
    # Quality metrics
    roe: Optional[float]
    roa: Optional[float]
    debt_to_equity: Optional[float]
    
    # Valuation assessment
    valuation_rating: ValuationRating
    valuation_score: float  # 0-100
    
    # Peer comparison
    pe_vs_sector: Optional[float]  # % difference from sector average
    pb_vs_sector: Optional[float]
    
    # Explanations
    valuation_summary: str
    key_strengths: List[str]
    key_concerns: List[str]


class ValuationAnalyzer:
    """
    Analyzes stock valuation using fundamental metrics.
    
    Nigerian market considerations:
    - Banking stocks typically trade at low P/E (3-6x)
    - Consumer goods at higher P/E (10-20x)
    - Dividend yield often 5-10%+
    """
    
    # Sector-specific P/E benchmarks for Nigerian market
    SECTOR_PE_BENCHMARKS = {
        'Financial Services': {'low': 3, 'median': 5, 'high': 8},
        'Consumer Goods': {'low': 8, 'median': 12, 'high': 20},
        'Industrial Goods': {'low': 6, 'median': 10, 'high': 15},
        'Oil & Gas': {'low': 4, 'median': 8, 'high': 12},
        'ICT': {'low': 8, 'median': 15, 'high': 25},
        'Conglomerates': {'low': 5, 'median': 8, 'high': 12},
        'Agriculture': {'low': 6, 'median': 10, 'high': 15},
    }
    
    # Sector-specific P/B benchmarks
    SECTOR_PB_BENCHMARKS = {
        'Financial Services': {'low': 0.3, 'median': 0.6, 'high': 1.2},
        'Consumer Goods': {'low': 1.5, 'median': 3.0, 'high': 6.0},
        'Industrial Goods': {'low': 1.0, 'median': 2.0, 'high': 4.0},
        'Oil & Gas': {'low': 0.5, 'median': 1.0, 'high': 2.0},
        'ICT': {'low': 2.0, 'median': 4.0, 'high': 8.0},
    }
    
    def analyze(
        self,
        symbol: str,
        sector: str,
        price: float,
        fundamentals: Dict[str, Any]
    ) -> ValuationMetrics:
        """
        Analyze stock valuation.
        
        Args:
            symbol: Stock symbol
            sector: Stock sector
            price: Current stock price
            fundamentals: Dict with fundamental data
        
        Returns:
            ValuationMetrics with complete analysis
        """
        # Extract metrics
        pe = fundamentals.get('pe_ratio')
        pb = fundamentals.get('pb_ratio')
        ps = fundamentals.get('ps_ratio')
        eps = fundamentals.get('eps')
        eps_growth = fundamentals.get('eps_growth')
        div_yield = fundamentals.get('dividend_yield')
        payout = fundamentals.get('payout_ratio')
        roe = fundamentals.get('roe')
        roa = fundamentals.get('roa')
        debt_equity = fundamentals.get('debt_to_equity')
        
        # Calculate sector comparisons
        pe_vs_sector = self._compare_to_sector(pe, sector, 'pe')
        pb_vs_sector = self._compare_to_sector(pb, sector, 'pb')
        
        # Calculate valuation score and rating
        valuation_score = self._calculate_valuation_score(
            pe, pb, div_yield, roe, eps_growth, sector
        )
        valuation_rating = self._determine_rating(valuation_score)
        
        # Generate summary and insights
        summary = self._generate_summary(
            symbol, valuation_rating, pe, pb, div_yield, sector
        )
        strengths, concerns = self._identify_strengths_concerns(
            pe, pb, div_yield, roe, debt_equity, eps_growth, sector
        )
        
        return ValuationMetrics(
            symbol=symbol,
            pe_ratio=pe,
            pb_ratio=pb,
            ps_ratio=ps,
            eps=eps,
            eps_growth=eps_growth,
            dividend_yield=div_yield,
            payout_ratio=payout,
            roe=roe,
            roa=roa,
            debt_to_equity=debt_equity,
            valuation_rating=valuation_rating,
            valuation_score=valuation_score,
            pe_vs_sector=pe_vs_sector,
            pb_vs_sector=pb_vs_sector,
            valuation_summary=summary,
            key_strengths=strengths,
            key_concerns=concerns
        )
    
    def _compare_to_sector(
        self, value: Optional[float], sector: str, metric: str
    ) -> Optional[float]:
        """Compare metric to sector median."""
        if value is None:
            return None
        
        if metric == 'pe':
            benchmarks = self.SECTOR_PE_BENCHMARKS.get(sector, {'median': 10})
        else:
            benchmarks = self.SECTOR_PB_BENCHMARKS.get(sector, {'median': 1.5})
        
        median = benchmarks.get('median', 10)
        return ((value - median) / median) * 100
    
    def _calculate_valuation_score(
        self,
        pe: Optional[float],
        pb: Optional[float],
        div_yield: Optional[float],
        roe: Optional[float],
        eps_growth: Optional[float],
        sector: str
    ) -> float:
        """Calculate overall valuation score (0-100, lower = more undervalued)."""
        score = 50  # Start neutral
        
        # P/E component (lower is better)
        if pe is not None:
            benchmarks = self.SECTOR_PE_BENCHMARKS.get(sector, {'median': 10})
            median_pe = benchmarks['median']
            if pe < median_pe * 0.5:
                score -= 20  # Very cheap
            elif pe < median_pe * 0.8:
                score -= 10  # Cheap
            elif pe > median_pe * 1.5:
                score += 15  # Expensive
            elif pe > median_pe * 1.2:
                score += 5  # Slightly expensive
        
        # Dividend yield (higher is better for value)
        if div_yield is not None:
            if div_yield > 8:
                score -= 15
            elif div_yield > 5:
                score -= 8
            elif div_yield < 2:
                score += 5
        
        # ROE quality adjustment (high ROE justifies premium)
        if roe is not None:
            if roe > 20:
                score -= 5  # Quality premium justified
            elif roe < 10:
                score += 5  # Low quality, needs discount
        
        # EPS growth adjustment
        if eps_growth is not None:
            if eps_growth > 20:
                score -= 10  # Growth justifies premium
            elif eps_growth < 0:
                score += 10  # Declining earnings = concern
        
        return max(0, min(100, score))
    
    def _determine_rating(self, score: float) -> ValuationRating:
        """Determine valuation rating from score."""
        if score <= 25:
            return ValuationRating.DEEPLY_UNDERVALUED
        elif score <= 40:
            return ValuationRating.UNDERVALUED
        elif score <= 60:
            return ValuationRating.FAIRLY_VALUED
        elif score <= 75:
            return ValuationRating.OVERVALUED
        else:
            return ValuationRating.DEEPLY_OVERVALUED
    
    def _generate_summary(
        self,
        symbol: str,
        rating: ValuationRating,
        pe: Optional[float],
        pb: Optional[float],
        div_yield: Optional[float],
        sector: str
    ) -> str:
        """Generate valuation summary."""
        rating_text = {
            ValuationRating.DEEPLY_UNDERVALUED: "appears deeply undervalued",
            ValuationRating.UNDERVALUED: "appears undervalued",
            ValuationRating.FAIRLY_VALUED: "appears fairly valued",
            ValuationRating.OVERVALUED: "appears overvalued",
            ValuationRating.DEEPLY_OVERVALUED: "appears deeply overvalued"
        }
        
        parts = [f"{symbol} {rating_text[rating]} relative to {sector} peers."]
        
        if pe is not None:
            parts.append(f"P/E of {pe:.1f}x")
        if div_yield is not None and div_yield > 0:
            parts.append(f"dividend yield of {div_yield:.1f}%")
        
        return " ".join(parts)
    
    def _identify_strengths_concerns(
        self,
        pe: Optional[float],
        pb: Optional[float],
        div_yield: Optional[float],
        roe: Optional[float],
        debt_equity: Optional[float],
        eps_growth: Optional[float],
        sector: str
    ) -> tuple[List[str], List[str]]:
        """Identify key strengths and concerns."""
        strengths = []
        concerns = []
        
        # P/E analysis
        if pe is not None:
            benchmarks = self.SECTOR_PE_BENCHMARKS.get(sector, {'median': 10})
            if pe < benchmarks['low']:
                strengths.append(f"Very low P/E ({pe:.1f}x) vs sector")
            elif pe > benchmarks['high']:
                concerns.append(f"High P/E ({pe:.1f}x) vs sector")
        
        # Dividend analysis
        if div_yield is not None:
            if div_yield > 7:
                strengths.append(f"Strong dividend yield ({div_yield:.1f}%)")
            elif div_yield < 2 and sector != 'ICT':
                concerns.append("Low/no dividend")
        
        # ROE analysis
        if roe is not None:
            if roe > 15:
                strengths.append(f"Strong ROE ({roe:.1f}%)")
            elif roe < 8:
                concerns.append(f"Weak ROE ({roe:.1f}%)")
        
        # Debt analysis
        if debt_equity is not None:
            if debt_equity > 2:
                concerns.append(f"High debt/equity ({debt_equity:.1f}x)")
            elif debt_equity < 0.5:
                strengths.append("Conservative debt levels")
        
        # Growth analysis
        if eps_growth is not None:
            if eps_growth > 15:
                strengths.append(f"Strong earnings growth ({eps_growth:.1f}%)")
            elif eps_growth < 0:
                concerns.append(f"Declining earnings ({eps_growth:.1f}%)")
        
        return strengths, concerns
