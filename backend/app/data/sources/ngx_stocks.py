"""
NGX Stock Registry for NSE Trader.

Contains authoritative information about stocks listed on the
Nigerian Exchange Group (NGX), including:
- Stock symbols and company names
- Sector classifications
- Market capitalization data
- Fundamental reference data
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class Sector(str, Enum):
    """NGX sector classifications."""
    FINANCIAL_SERVICES = "Financial Services"
    CONSUMER_GOODS = "Consumer Goods"
    INDUSTRIAL_GOODS = "Industrial Goods"
    OIL_AND_GAS = "Oil & Gas"
    ICT = "ICT"
    HEALTHCARE = "Healthcare"
    AGRICULTURE = "Agriculture"
    CONGLOMERATES = "Conglomerates"
    CONSTRUCTION = "Construction"
    SERVICES = "Services"
    NATURAL_RESOURCES = "Natural Resources"


@dataclass
class StockInfo:
    """Stock registry information."""
    symbol: str
    name: str
    sector: Sector
    market_cap_billions: float  # In billions of Naira
    shares_outstanding: int     # Number of shares
    is_active: bool = True
    
    # Fundamental reference data (updated periodically)
    last_dividend: Optional[float] = None
    dividend_yield: Optional[float] = None
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    
    # Liquidity tier (based on average trading)
    liquidity_tier: str = "medium"  # high, medium, low, very_low


class NGXStockRegistry:
    """
    Registry of Nigerian Exchange Group listed stocks.
    
    Provides authoritative reference data for all supported stocks.
    """
    
    # Comprehensive stock registry with accurate sector classifications
    STOCKS = {
        # === FINANCIAL SERVICES ===
        'GTCO': StockInfo(
            symbol='GTCO',
            name='Guaranty Trust Holding Company Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=882.94,
            shares_outstanding=29_431_179_224,
            liquidity_tier='high'
        ),
        'ZENITHBANK': StockInfo(
            symbol='ZENITHBANK',
            name='Zenith Bank Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=1099.82,
            shares_outstanding=31_396_493_786,
            liquidity_tier='high'
        ),
        'ACCESSCORP': StockInfo(
            symbol='ACCESSCORP',
            name='Access Holdings Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=576.11,
            shares_outstanding=35_545_225_622,
            liquidity_tier='high'
        ),
        'UBA': StockInfo(
            symbol='UBA',
            name='United Bank for Africa Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=580.93,
            shares_outstanding=34_199_433_397,
            liquidity_tier='high'
        ),
        'FIRSTHOLDCO': StockInfo(
            symbol='FIRSTHOLDCO',
            name='First HoldCo Plc (formerly FBN Holdings)',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=592.27,
            shares_outstanding=35_895_292_790,
            liquidity_tier='high'
        ),
        'STANBIC': StockInfo(
            symbol='STANBIC',
            name='Stanbic IBTC Holdings Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=390.25,
            shares_outstanding=12_879_000_000,
            liquidity_tier='medium'
        ),
        'FIDELITYBK': StockInfo(
            symbol='FIDELITYBK',
            name='Fidelity Bank Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=103.21,
            shares_outstanding=32_128_258_678,
            liquidity_tier='medium'
        ),
        'FCMB': StockInfo(
            symbol='FCMB',
            name='FCMB Group Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=118.83,
            shares_outstanding=19_808_000_000,
            liquidity_tier='medium'
        ),
        'WEMABANK': StockInfo(
            symbol='WEMABANK',
            name='Wema Bank Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=42.25,
            shares_outstanding=40_833_000_000,
            liquidity_tier='medium'
        ),
        'ETI': StockInfo(
            symbol='ETI',
            name='Ecobank Transnational Incorporated',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=386.48,
            shares_outstanding=24_585_000_000,
            liquidity_tier='medium'
        ),
        'STERLINGNG': StockInfo(
            symbol='STERLINGNG',
            name='Sterling Financial Holdings Company Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=60.38,
            shares_outstanding=28_826_000_000,
            liquidity_tier='low'
        ),
        
        # === ICT ===
        'MTNN': StockInfo(
            symbol='MTNN',
            name='MTN Nigeria Communications Plc',
            sector=Sector.ICT,
            market_cap_billions=5329.89,
            shares_outstanding=20_354_513_050,
            liquidity_tier='high'
        ),
        'AIRTELAFRI': StockInfo(
            symbol='AIRTELAFRI',
            name='Airtel Africa Plc',
            sector=Sector.ICT,
            market_cap_billions=4134.82,
            shares_outstanding=3_758_151_504,
            liquidity_tier='high'
        ),
        
        # === INDUSTRIAL GOODS ===
        'DANGCEM': StockInfo(
            symbol='DANGCEM',
            name='Dangote Cement Plc',
            sector=Sector.INDUSTRIAL_GOODS,
            market_cap_billions=4618.95,
            shares_outstanding=17_040_507_405,
            liquidity_tier='high'
        ),
        'BUACEMENT': StockInfo(
            symbol='BUACEMENT',
            name='BUA Cement Plc',
            sector=Sector.INDUSTRIAL_GOODS,
            market_cap_billions=2436.21,
            shares_outstanding=33_864_354_060,
            liquidity_tier='high'
        ),
        'WAPCO': StockInfo(
            symbol='WAPCO',
            name='Lafarge Africa Plc',
            sector=Sector.INDUSTRIAL_GOODS,
            market_cap_billions=155.65,
            shares_outstanding=8_059_000_000,
            liquidity_tier='medium'
        ),
        'JBERGER': StockInfo(
            symbol='JBERGER',
            name='Julius Berger Nigeria Plc',
            sector=Sector.CONSTRUCTION,
            market_cap_billions=72.0,
            shares_outstanding=658_000_000,
            liquidity_tier='low'
        ),
        
        # === CONSUMER GOODS ===
        'NESTLE': StockInfo(
            symbol='NESTLE',
            name='Nestle Nigeria Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=1190.12,
            shares_outstanding=792_656_252,
            liquidity_tier='medium'
        ),
        'BUAFOODS': StockInfo(
            symbol='BUAFOODS',
            name='BUA Foods Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=1085.76,
            shares_outstanding=18_000_000_000,
            liquidity_tier='medium'
        ),
        'GUINNESS': StockInfo(
            symbol='GUINNESS',
            name='Guinness Nigeria Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=120.87,
            shares_outstanding=2_190_000_000,
            liquidity_tier='medium'
        ),
        'NB': StockInfo(
            symbol='NB',
            name='Nigerian Breweries Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=260.42,
            shares_outstanding=8_000_000_000,
            liquidity_tier='medium'
        ),
        # FLOURMILL: Delisted from NGX in December 2024
        'DANGSUGAR': StockInfo(
            symbol='DANGSUGAR',
            name='Dangote Sugar Refinery Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=138.89,
            shares_outstanding=12_146_000_000,
            liquidity_tier='medium'
        ),
        'NASCON': StockInfo(
            symbol='NASCON',
            name='NASCON Allied Industries Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=97.19,
            shares_outstanding=2_649_000_000,
            liquidity_tier='low'
        ),
        'UNILEVER': StockInfo(
            symbol='UNILEVER',
            name='Unilever Nigeria Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=85.83,
            shares_outstanding=5_745_000_000,
            liquidity_tier='low'
        ),
        'CADBURY': StockInfo(
            symbol='CADBURY',
            name='Cadbury Nigeria Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=33.45,
            shares_outstanding=1_875_000_000,
            liquidity_tier='low'
        ),
        'INTBREW': StockInfo(
            symbol='INTBREW',
            name='International Breweries Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=110.63,
            shares_outstanding=21_781_000_000,
            liquidity_tier='low'
        ),
        'VITAFOAM': StockInfo(
            symbol='VITAFOAM',
            name='Vitafoam Nigeria Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=42.01,
            shares_outstanding=1_085_000_000,
            liquidity_tier='low'
        ),
        
        # === OIL & GAS ===
        'SEPLAT': StockInfo(
            symbol='SEPLAT',
            name='Seplat Energy Plc',
            sector=Sector.OIL_AND_GAS,
            market_cap_billions=520.47,
            shares_outstanding=588_444_561,
            liquidity_tier='medium'
        ),
        'OANDO': StockInfo(
            symbol='OANDO',
            name='Oando Plc',
            sector=Sector.OIL_AND_GAS,
            market_cap_billions=447.53,
            shares_outstanding=12_442_000_000,
            liquidity_tier='medium'
        ),
        'TOTAL': StockInfo(
            symbol='TOTAL',
            name='TotalEnergies Marketing Nigeria Plc',
            sector=Sector.OIL_AND_GAS,
            market_cap_billions=118.75,
            shares_outstanding=339_500_000,
            liquidity_tier='low'
        ),
        'CONOIL': StockInfo(
            symbol='CONOIL',
            name='Conoil Plc',
            sector=Sector.OIL_AND_GAS,
            market_cap_billions=79.88,
            shares_outstanding=693_800_000,
            liquidity_tier='low'
        ),
        'ARDOVA': StockInfo(
            symbol='ARDOVA',
            name='Ardova Plc',
            sector=Sector.OIL_AND_GAS,
            market_cap_billions=66.67,
            shares_outstanding=1_302_000_000,
            liquidity_tier='low'
        ),
        
        # === CONGLOMERATES ===
        'TRANSCORP': StockInfo(
            symbol='TRANSCORP',
            name='Transnational Corporation Plc',
            sector=Sector.CONGLOMERATES,
            market_cap_billions=203.58,
            shares_outstanding=40_690_000_000,
            liquidity_tier='high'
        ),
        'UACN': StockInfo(
            symbol='UACN',
            name='UAC of Nigeria Plc',
            sector=Sector.CONGLOMERATES,
            market_cap_billions=63.5,
            shares_outstanding=2_883_000_000,
            liquidity_tier='low'
        ),
        
        # === OTHERS ===
        'GEREGU': StockInfo(
            symbol='GEREGU',
            name='Geregu Power Plc',
            sector=Sector.SERVICES,
            market_cap_billions=1000.0,
            shares_outstanding=2_500_000_000,
            liquidity_tier='medium'
        ),
        'UCAP': StockInfo(
            symbol='UCAP',
            name='United Capital Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=118.0,
            shares_outstanding=6_000_000_000,
            liquidity_tier='medium'
        ),
        'NAHCO': StockInfo(
            symbol='NAHCO',
            name='Nigerian Aviation Handling Company Plc',
            sector=Sector.SERVICES,
            market_cap_billions=36.58,
            shares_outstanding=1_687_000_000,
            liquidity_tier='low'
        ),
        'PRESCO': StockInfo(
            symbol='PRESCO',
            name='Presco Plc',
            sector=Sector.AGRICULTURE,
            market_cap_billions=125.0,
            shares_outstanding=1_000_000_000,
            liquidity_tier='low'
        ),
        'OKOMUOIL': StockInfo(
            symbol='OKOMUOIL',
            name='Okomu Oil Palm Plc',
            sector=Sector.AGRICULTURE,
            market_cap_billions=95.31,
            shares_outstanding=954_000_000,
            liquidity_tier='low'
        ),
        'NGXGROUP': StockInfo(
            symbol='NGXGROUP',
            name='Nigerian Exchange Group Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=54.42,
            shares_outstanding=1_964_000_000,
            liquidity_tier='low'
        ),
        
        # === ADDITIONAL STOCKS FROM NGNMARKET.COM ===
        
        # Financial Services (additional)
        'JAIZBANK': StockInfo(
            symbol='JAIZBANK',
            name='Jaiz Bank Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=45.0,
            shares_outstanding=29_464_249_300,
            liquidity_tier='medium'
        ),
        'MANSARD': StockInfo(
            symbol='MANSARD',
            name='AXA Mansard Insurance Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=28.0,
            shares_outstanding=2_100_000_000,
            liquidity_tier='medium'
        ),
        'NEM': StockInfo(
            symbol='NEM',
            name='NEM Insurance Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=15.0,
            shares_outstanding=620_000_000,
            liquidity_tier='low'
        ),
        'CUSTODIAN': StockInfo(
            symbol='CUSTODIAN',
            name='Custodian Investment Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=22.0,
            shares_outstanding=5_893_918_614,
            liquidity_tier='low'
        ),
        'CORNERST': StockInfo(
            symbol='CORNERST',
            name='Cornerstone Insurance Plc',
            sector=Sector.FINANCIAL_SERVICES,
            market_cap_billions=8.0,
            shares_outstanding=11_481_406_562,
            liquidity_tier='low'
        ),
        
        # Consumer Goods (additional)
        'TRANSCOHOT': StockInfo(
            symbol='TRANSCOHOT',
            name='Transcorp Hotels Plc',
            sector=Sector.SERVICES,
            market_cap_billions=95.0,
            shares_outstanding=10_242_090_500,
            liquidity_tier='medium'
        ),
        'HONYFLOUR': StockInfo(
            symbol='HONYFLOUR',
            name='Honeywell Flour Mills Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=85.0,
            shares_outstanding=8_986_743_463,
            liquidity_tier='medium'
        ),
        'CHAMPION': StockInfo(
            symbol='CHAMPION',
            name='Champion Breweries Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=12.0,
            shares_outstanding=3_388_000_000,
            liquidity_tier='low'
        ),
        'MCNICHOLS': StockInfo(
            symbol='MCNICHOLS',
            name='McNichols Plc',
            sector=Sector.CONSUMER_GOODS,
            market_cap_billions=5.0,
            shares_outstanding=420_000_000,
            liquidity_tier='very_low'
        ),
        
        # ICT (additional)
        'LEGENDINT': StockInfo(
            symbol='LEGENDINT',
            name='Legend Internet Plc',
            sector=Sector.ICT,
            market_cap_billions=3.0,
            shares_outstanding=500_000_000,
            liquidity_tier='low'
        ),
        'CHAMS': StockInfo(
            symbol='CHAMS',
            name='Chams Holding Company Plc',
            sector=Sector.ICT,
            market_cap_billions=4.0,
            shares_outstanding=7_393_505_960,
            liquidity_tier='low'
        ),
        'ETRANZACT': StockInfo(
            symbol='ETRANZACT',
            name='eTranzact International Plc',
            sector=Sector.ICT,
            market_cap_billions=15.0,
            shares_outstanding=4_275_366_750,
            liquidity_tier='low'
        ),
        
        # Industrial Goods (additional)
        'ALEX': StockInfo(
            symbol='ALEX',
            name='Aluminium Extrusion Industries Plc',
            sector=Sector.NATURAL_RESOURCES,
            market_cap_billions=8.0,
            shares_outstanding=569_099_627,
            liquidity_tier='low'
        ),
        'AUSTINLAZ': StockInfo(
            symbol='AUSTINLAZ',
            name='Austin Laz & Company Plc',
            sector=Sector.INDUSTRIAL_GOODS,
            market_cap_billions=2.0,
            shares_outstanding=500_000_000,
            liquidity_tier='very_low'
        ),
        'BETAGLAS': StockInfo(
            symbol='BETAGLAS',
            name='Beta Glass Plc',
            sector=Sector.INDUSTRIAL_GOODS,
            market_cap_billions=180.0,
            shares_outstanding=491_030_750,
            liquidity_tier='low'
        ),
        'CUTIX': StockInfo(
            symbol='CUTIX',
            name='Cutix Plc',
            sector=Sector.INDUSTRIAL_GOODS,
            market_cap_billions=6.0,
            shares_outstanding=1_210_000_000,
            liquidity_tier='low'
        ),
        
        # Healthcare (additional)
        'NEIMETH': StockInfo(
            symbol='NEIMETH',
            name='Neimeth International Pharmaceuticals Plc',
            sector=Sector.HEALTHCARE,
            market_cap_billions=4.0,
            shares_outstanding=988_192_000,
            liquidity_tier='low'
        ),
        'PHARMDEKO': StockInfo(
            symbol='PHARMDEKO',
            name='Pharma-Deko Plc',
            sector=Sector.HEALTHCARE,
            market_cap_billions=1.5,
            shares_outstanding=404_574_264,
            liquidity_tier='very_low'
        ),
        'MORISON': StockInfo(
            symbol='MORISON',
            name='Morison Industries Plc',
            sector=Sector.HEALTHCARE,
            market_cap_billions=3.0,
            shares_outstanding=443_700_000,
            liquidity_tier='very_low'
        ),
        
        # Services (additional)
        'LEARNAFRCA': StockInfo(
            symbol='LEARNAFRCA',
            name='Learn Africa Plc',
            sector=Sector.SERVICES,
            market_cap_billions=2.5,
            shares_outstanding=577_389_836,
            liquidity_tier='very_low'
        ),
        'REDSTAREX': StockInfo(
            symbol='REDSTAREX',
            name='Red Star Express Plc',
            sector=Sector.SERVICES,
            market_cap_billions=4.0,
            shares_outstanding=891_947_098,
            liquidity_tier='low'
        ),
        'CAVERTON': StockInfo(
            symbol='CAVERTON',
            name='Caverton Offshore Support Group Plc',
            sector=Sector.SERVICES,
            market_cap_billions=8.0,
            shares_outstanding=4_687_500_000,
            liquidity_tier='low'
        ),
        
        # Oil & Gas (additional)
        'ETERNA': StockInfo(
            symbol='ETERNA',
            name='Eterna Plc',
            sector=Sector.OIL_AND_GAS,
            market_cap_billions=18.0,
            shares_outstanding=1_320_000_000,
            liquidity_tier='medium'
        ),
        'JAPAULOIL': StockInfo(
            symbol='JAPAULOIL',
            name='Japaul Gold and Ventures Plc',
            sector=Sector.OIL_AND_GAS,
            market_cap_billions=6.0,
            shares_outstanding=10_000_000_000,
            liquidity_tier='low'
        ),
        
        # Conglomerates (additional)
        'JOHNHOLT': StockInfo(
            symbol='JOHNHOLT',
            name='John Holt Plc',
            sector=Sector.CONGLOMERATES,
            market_cap_billions=3.0,
            shares_outstanding=313_699_716,
            liquidity_tier='very_low'
        ),
        'SCOA': StockInfo(
            symbol='SCOA',
            name='SCOA Nigeria Plc',
            sector=Sector.CONGLOMERATES,
            market_cap_billions=4.0,
            shares_outstanding=351_000_000,
            liquidity_tier='very_low'
        ),
    }
    
    def __init__(self):
        self._stocks = {symbol: info.__dict__ for symbol, info in self.STOCKS.items()}
    
    def get_stock(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get stock information by symbol."""
        stock = self.STOCKS.get(symbol.upper())
        if stock:
            return stock.__dict__
        return None
    
    def get_all_stocks(self) -> List[Dict[str, Any]]:
        """Get all registered stocks."""
        return [info.__dict__ for info in self.STOCKS.values()]
    
    def get_by_sector(self, sector: Sector) -> List[Dict[str, Any]]:
        """Get all stocks in a sector."""
        return [
            info.__dict__ for info in self.STOCKS.values()
            if info.sector == sector
        ]
    
    def get_by_liquidity_tier(self, tier: str) -> List[Dict[str, Any]]:
        """Get stocks by liquidity tier."""
        return [
            info.__dict__ for info in self.STOCKS.values()
            if info.liquidity_tier == tier
        ]
    
    def get_high_liquidity_stocks(self) -> List[Dict[str, Any]]:
        """Get only high liquidity stocks."""
        return self.get_by_liquidity_tier('high')
    
    def get_symbols(self) -> List[str]:
        """Get list of all stock symbols."""
        return list(self.STOCKS.keys())
    
    def get_sectors(self) -> List[str]:
        """Get list of all sectors with stocks."""
        return list(set(info.sector.value for info in self.STOCKS.values()))
    
    def get_sector_for_symbol(self, symbol: str) -> Optional[str]:
        """Get sector for a specific symbol."""
        stock = self.STOCKS.get(symbol.upper())
        return stock.sector.value if stock else None
    
    def get_market_cap(self, symbol: str) -> Optional[float]:
        """Get market cap for a symbol (in billions)."""
        stock = self.STOCKS.get(symbol.upper())
        return stock.market_cap_billions if stock else None
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search stocks by symbol or name."""
        query = query.lower()
        results = []
        for stock in self.STOCKS.values():
            if query in stock.symbol.lower() or query in stock.name.lower():
                results.append(stock.__dict__)
        return results
