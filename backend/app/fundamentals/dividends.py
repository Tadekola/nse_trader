"""
Dividend Analysis for NSE Trader.

Nigerian stocks are known for attractive dividend yields.
This module analyzes dividend characteristics and sustainability.
"""
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class DividendRating(str, Enum):
    """Dividend rating categories."""
    EXCELLENT = "excellent"    # High yield, consistent, sustainable
    GOOD = "good"              # Good yield, mostly consistent
    MODERATE = "moderate"      # Average yield or less consistent
    WEAK = "weak"              # Low yield or concerns
    NONE = "none"              # No dividend


@dataclass
class DividendAnalysis:
    """Complete dividend analysis for a stock."""
    symbol: str
    
    # Current metrics
    current_yield: Optional[float]
    annual_dividend: Optional[float]
    payout_ratio: Optional[float]
    
    # History
    dividend_history_years: int
    consecutive_years_paid: int
    has_cut_dividend: bool
    average_yield_5y: Optional[float]
    
    # Growth
    dividend_growth_1y: Optional[float]
    dividend_growth_3y_cagr: Optional[float]
    
    # Sustainability
    earnings_coverage: Optional[float]  # How many times earnings cover dividend
    free_cash_flow_coverage: Optional[float]
    
    # Upcoming
    ex_dividend_date: Optional[datetime]
    payment_date: Optional[datetime]
    expected_dividend: Optional[float]
    
    # Assessment
    dividend_rating: DividendRating
    dividend_score: float  # 0-100
    
    # Insights
    summary: str
    strengths: List[str]
    risks: List[str]


class DividendAnalyzer:
    """
    Analyzes dividend characteristics for Nigerian stocks.
    
    Nigerian market specifics:
    - Many stocks pay interim + final dividends
    - Banking sector typically has high yields (8-15%)
    - Consumer goods sector more moderate (4-8%)
    - Payment delays can occur
    """
    
    # Sector-specific yield expectations
    SECTOR_YIELD_BENCHMARKS = {
        'Financial Services': {'good': 6, 'excellent': 10},
        'Consumer Goods': {'good': 4, 'excellent': 7},
        'Industrial Goods': {'good': 3, 'excellent': 6},
        'Oil & Gas': {'good': 4, 'excellent': 7},
        'ICT': {'good': 3, 'excellent': 5},
        'Conglomerates': {'good': 4, 'excellent': 7},
    }
    
    def analyze(
        self,
        symbol: str,
        sector: str,
        current_price: float,
        dividend_data: Dict[str, Any]
    ) -> DividendAnalysis:
        """
        Analyze dividend characteristics.
        
        Args:
            symbol: Stock symbol
            sector: Stock sector
            current_price: Current stock price
            dividend_data: Historical and current dividend data
        """
        # Extract data
        annual_dividend = dividend_data.get('annual_dividend', 0)
        current_yield = (annual_dividend / current_price * 100) if current_price > 0 else 0
        payout_ratio = dividend_data.get('payout_ratio')
        
        # History
        history_years = dividend_data.get('history_years', 0)
        consecutive_years = dividend_data.get('consecutive_years', 0)
        has_cut = dividend_data.get('has_cut_dividend', False)
        avg_yield_5y = dividend_data.get('average_yield_5y')
        
        # Growth
        growth_1y = dividend_data.get('growth_1y')
        growth_3y = dividend_data.get('growth_3y_cagr')
        
        # Coverage
        eps = dividend_data.get('eps', 0)
        earnings_coverage = (eps / annual_dividend) if annual_dividend > 0 else None
        fcf_coverage = dividend_data.get('fcf_coverage')
        
        # Upcoming
        ex_date = dividend_data.get('ex_dividend_date')
        payment_date = dividend_data.get('payment_date')
        expected_div = dividend_data.get('expected_dividend')
        
        # Calculate rating and score
        score = self._calculate_dividend_score(
            current_yield, payout_ratio, consecutive_years,
            has_cut, earnings_coverage, sector
        )
        rating = self._determine_rating(score, current_yield)
        
        # Generate insights
        summary = self._generate_summary(symbol, rating, current_yield, payout_ratio)
        strengths, risks = self._identify_strengths_risks(
            current_yield, payout_ratio, consecutive_years,
            has_cut, earnings_coverage, sector
        )
        
        return DividendAnalysis(
            symbol=symbol,
            current_yield=current_yield,
            annual_dividend=annual_dividend,
            payout_ratio=payout_ratio,
            dividend_history_years=history_years,
            consecutive_years_paid=consecutive_years,
            has_cut_dividend=has_cut,
            average_yield_5y=avg_yield_5y,
            dividend_growth_1y=growth_1y,
            dividend_growth_3y_cagr=growth_3y,
            earnings_coverage=earnings_coverage,
            free_cash_flow_coverage=fcf_coverage,
            ex_dividend_date=ex_date,
            payment_date=payment_date,
            expected_dividend=expected_div,
            dividend_rating=rating,
            dividend_score=score,
            summary=summary,
            strengths=strengths,
            risks=risks
        )
    
    def _calculate_dividend_score(
        self,
        yield_pct: float,
        payout_ratio: Optional[float],
        consecutive_years: int,
        has_cut: bool,
        earnings_coverage: Optional[float],
        sector: str
    ) -> float:
        """Calculate dividend score (0-100)."""
        score = 0
        
        # Yield component (0-30 points)
        benchmarks = self.SECTOR_YIELD_BENCHMARKS.get(sector, {'good': 4, 'excellent': 7})
        if yield_pct >= benchmarks['excellent']:
            score += 30
        elif yield_pct >= benchmarks['good']:
            score += 20
        elif yield_pct >= 2:
            score += 10
        
        # Consistency component (0-25 points)
        if consecutive_years >= 10:
            score += 25
        elif consecutive_years >= 5:
            score += 15
        elif consecutive_years >= 3:
            score += 10
        
        # Cut penalty
        if has_cut:
            score -= 10
        
        # Sustainability component (0-25 points)
        if payout_ratio is not None:
            if 30 <= payout_ratio <= 60:
                score += 25  # Healthy payout
            elif payout_ratio < 30:
                score += 15  # Conservative
            elif payout_ratio <= 80:
                score += 10  # High but manageable
            # >80% is concerning, no points
        
        # Coverage component (0-20 points)
        if earnings_coverage is not None:
            if earnings_coverage >= 2:
                score += 20
            elif earnings_coverage >= 1.5:
                score += 15
            elif earnings_coverage >= 1:
                score += 5
        
        return max(0, min(100, score))
    
    def _determine_rating(self, score: float, yield_pct: float) -> DividendRating:
        """Determine dividend rating."""
        if yield_pct == 0:
            return DividendRating.NONE
        
        if score >= 75:
            return DividendRating.EXCELLENT
        elif score >= 50:
            return DividendRating.GOOD
        elif score >= 25:
            return DividendRating.MODERATE
        else:
            return DividendRating.WEAK
    
    def _generate_summary(
        self,
        symbol: str,
        rating: DividendRating,
        yield_pct: float,
        payout_ratio: Optional[float]
    ) -> str:
        """Generate dividend summary."""
        if rating == DividendRating.NONE:
            return f"{symbol} does not currently pay a dividend."
        
        rating_text = {
            DividendRating.EXCELLENT: "excellent dividend profile",
            DividendRating.GOOD: "good dividend characteristics",
            DividendRating.MODERATE: "moderate dividend profile",
            DividendRating.WEAK: "weak dividend characteristics"
        }
        
        parts = [f"{symbol} has {rating_text[rating]} with a {yield_pct:.1f}% yield."]
        
        if payout_ratio is not None:
            if payout_ratio > 80:
                parts.append("High payout ratio suggests limited room for growth.")
            elif payout_ratio < 40:
                parts.append("Conservative payout leaves room for increases.")
        
        return " ".join(parts)
    
    def _identify_strengths_risks(
        self,
        yield_pct: float,
        payout_ratio: Optional[float],
        consecutive_years: int,
        has_cut: bool,
        earnings_coverage: Optional[float],
        sector: str
    ) -> tuple[List[str], List[str]]:
        """Identify dividend strengths and risks."""
        strengths = []
        risks = []
        
        # Yield analysis
        benchmarks = self.SECTOR_YIELD_BENCHMARKS.get(sector, {'good': 4})
        if yield_pct >= benchmarks.get('excellent', 7):
            strengths.append(f"Excellent yield of {yield_pct:.1f}%")
        elif yield_pct >= benchmarks.get('good', 4):
            strengths.append(f"Attractive yield of {yield_pct:.1f}%")
        
        # Consistency analysis
        if consecutive_years >= 10:
            strengths.append(f"Consistent dividend for {consecutive_years}+ years")
        elif consecutive_years >= 5:
            strengths.append("Reliable dividend history")
        
        if has_cut:
            risks.append("Has previously cut dividend")
        
        # Payout analysis
        if payout_ratio is not None:
            if payout_ratio > 90:
                risks.append("Very high payout ratio - sustainability concern")
            elif payout_ratio > 75:
                risks.append("High payout ratio limits growth")
            elif payout_ratio < 40:
                strengths.append("Room for dividend growth")
        
        # Coverage analysis
        if earnings_coverage is not None:
            if earnings_coverage < 1:
                risks.append("Dividend not fully covered by earnings")
            elif earnings_coverage >= 2:
                strengths.append("Well-covered by earnings")
        
        return strengths, risks
    
    def get_upcoming_dividends(
        self,
        stocks: List[Dict[str, Any]],
        days_ahead: int = 30
    ) -> List[Dict[str, Any]]:
        """Get stocks with upcoming dividends."""
        upcoming = []
        cutoff = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        
        for stock in stocks:
            ex_date = stock.get('ex_dividend_date')
            if ex_date and ex_date <= cutoff:
                upcoming.append({
                    'symbol': stock.get('symbol'),
                    'name': stock.get('name'),
                    'ex_date': ex_date,
                    'expected_dividend': stock.get('expected_dividend'),
                    'yield': stock.get('dividend_yield')
                })
        
        return sorted(upcoming, key=lambda x: x['ex_date'])
