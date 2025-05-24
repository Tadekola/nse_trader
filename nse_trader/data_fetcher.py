"""Data fetching module for NSE stock data using TradingView."""
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd

from tradingview_ta import TA_Handler, Interval
from nse_trader.technical_analysis import TechnicalAnalyzer

logger = logging.getLogger(__name__)

class NSEDataFetcher:
    """Handles fetching and processing of NSE stock data from TradingView."""
    
    def __init__(self):
        self.exchange = "NSENG"
        self.screener = "nigeria"
        self.interval = Interval.INTERVAL_1_DAY
        self._last_update = None
        self.logger = logging.getLogger(__name__)
        
        # Market cap data (in billions of Naira)
        self.market_caps = {
            'MTNN': 5329.89,  # MTN Nigeria
            'DANGCEM': 4618.95,  # Dangote Cement
            'AIRTELAFRI': 4134.82,  # Airtel Africa
            'BUACEMENT': 2436.21,  # BUA Cement
            'GTCO': 882.94,  # GTCO
            'ZENITHBANK': 1099.82,  # Zenith Bank
            'NESTLE': 1190.12,  # Nestle Nigeria
            'BUAFOODS': 1085.76,  # BUA Foods
            'ACCESSCORP': 576.11,  # Access Holdings
            'UBA': 580.93,  # UBA
            'FBNH': 592.27,  # FBN Holdings
            'TRANSCORP': 203.58,  # Transcorp
            'GEREGU': 1000.0,  # Geregu Power
            'SEPLAT': 520.47,  # Seplat Energy
            'OANDO': 447.53,  # Oando
            'STANBIC': 390.25,  # Stanbic IBTC
            'GUINNESS': 120.87,  # Guinness Nigeria
            'NB': 260.42,  # Nigerian Breweries
            'TOTAL': 118.75,  # TotalEnergies Marketing
            'WAPCO': 155.65,  # Lafarge Africa
            'INTBREW': 110.63,  # International Breweries
            'JBERGER': 72.0,  # Julius Berger
            'PRESCO': 125.0,  # Presco
            'FIDELITYBK': 103.21,  # Fidelity Bank
            'FCMB': 118.83,  # FCMB Group
            'FLOURMILL': 206.25,  # Flour Mills of Nigeria
            'HONYFLOUR': 27.66,  # Honeywell Flour Mills
            'UNILEVER': 85.83,  # Unilever Nigeria
            'CUSTODIAN': 44.54,  # Custodian Investment
            'FTNCOCOA': 12.32,  # FTN Cocoa Processors
            'UCAP': 118.0,  # United Capital
            'CADBURY': 33.45,  # Cadbury Nigeria
            'NAHCO': 36.58,  # Nigerian Aviation Handling Company
            'WEMABANK': 42.25,  # Wema Bank
            'ETI': 386.48,  # Ecobank Transnational
            'DANGSUGAR': 138.89,  # Dangote Sugar Refinery
            'NASCON': 97.19,  # NASCON Allied Industries
            'UACN': 63.5,  # UAC of Nigeria
            'UPDCREIT': 15.8,  # UPDC Real Estate Investment Trust
            'UPDC': 32.64,  # UPDC
            'CAVERTON': 16.89,  # Caverton Offshore Support Group
            'CONOIL': 79.88,  # Conoil
            'ETERNA': 20.52,  # Eterna
            'JAPAULGOLD': 11.76,  # Japaul Gold & Ventures
            'MANSARD': 31.25,  # AXA Mansard Insurance
            'NCR': 10.91,  # NCR Nigeria
            'NGXGROUP': 54.42,  # Nigerian Exchange Group
            'PZ': 105.94,  # PZ Cussons Nigeria
            'STERLINGNG': 60.38,  # Sterling Financial Holdings Company
            'VERITASKAP': 10.14,  # Veritas Kapital Assurance
            'OKOMUOIL': 95.31,  # Okomu Oil Palm
            'ARDOVA': 66.67,  # Ardova
            'CHAMS': 14.02,  # Chams Holding Company
            'CHAMPION': 34.76,  # Champion Breweries
            'CUTIX': 17.51,  # Cutix
            'DAARCOMM': 12.93,  # DAAR Communications
            'LINKASSURE': 12.6,  # Linkage Assurance
            'LIVESTOCK': 16.5,  # Livestock Feeds
            'MBENEFIT': 11.03,  # Mutual Benefits Assurance
            'CORNERST': 19.26,  # Cornerstone Insurance
            'MAYBAKER': 13.52,  # May & Baker Nigeria
            'NEIMETH': 4.22,  # Neimeth International Pharmaceuticals
            'MORISON': 3.76,  # Morison Industries
            'VITAFOAM': 42.01  # Vitafoam Nigeria
        }
        
        # Trading signals explanation templates
        self.signal_explanations = {
            'STRONG_BUY': "Strong technicals with positive momentum and volume trends",
            'BUY': "Favorable price action and technical indicators suggest upside potential",
            'NEUTRAL': "Mixed signals, showing both positive and negative indicators",
            'SELL': "Technical indicators suggest downward pressure on price",
            'STRONG_SELL': "Multiple indicators showing negative momentum and selling pressure"
        }

    def get_top_stocks(self, limit: int = 10) -> List[Dict]:
        """Get top traded NSE stocks."""
        try:
            stocks_data = []
            
            for symbol in list(self.market_caps.keys())[:limit]:
                try:
                    handler = TA_Handler(
                        symbol=symbol,
                        exchange=self.exchange,
                        screener=self.screener,
                        interval=self.interval
                    )
                    analysis = handler.get_analysis()
                    
                    if analysis:
                        # Calculate market cap and other metrics
                        price = analysis.indicators.get('close', 0)
                        volume = analysis.indicators.get('volume', 0)
                        change = analysis.indicators.get('change', 0)
                        market_cap = self.market_caps.get(symbol, 0)
                        value = price * volume
                        
                        # Get recommendation and explanation
                        recommendation = analysis.summary.get('RECOMMENDATION', 'NEUTRAL')
                        explanation = self._get_recommendation_explanation(analysis)
                        
                        stocks_data.append({
                            'symbol': symbol,
                            'name': self._get_company_name(symbol),
                            'price': self._format_currency(price),
                            'price_raw': price,
                            'change': change,
                            'change_percent': f"{change:.2f}%" if change else "0.00%",
                            'volume': self._format_number(volume),
                            'volume_raw': volume,
                            'market_cap': self._format_currency(market_cap * 1e9),  # Convert billions to naira
                            'market_cap_raw': market_cap * 1e9,
                            'value': self._format_currency(value),
                            'value_raw': value,
                            'high': self._format_currency(analysis.indicators.get('high', price)),
                            'low': self._format_currency(analysis.indicators.get('low', price)),
                            'open': self._format_currency(analysis.indicators.get('open', price)),
                            'recommendation': recommendation,
                            'explanation': explanation,
                            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                except Exception as e:
                    logger.error(f"Error fetching data for {symbol}: {str(e)}")
                    continue
            
            # Sort by market cap
            stocks_data.sort(key=lambda x: x['market_cap_raw'], reverse=True)
            self._last_update = datetime.now()
            return stocks_data
        except Exception as e:
            logger.error(f"Error fetching top stocks: {str(e)}")
            return []

    def get_market_summary(self) -> Dict:
        """Get NSE market summary using the NGX30 index."""
        try:
            handler = TA_Handler(
                symbol="NGX30",
                exchange=self.exchange,
                screener=self.screener,
                interval=self.interval
            )
            analysis = handler.get_analysis()
            
            if not analysis:
                return {}
            
            # Calculate total market cap
            total_market_cap = sum(self.market_caps.values()) * 1e9  # Convert billions to naira
            
            # Get index value and calculate derived values
            index_value = analysis.indicators.get('close', 0)
            change = analysis.indicators.get('change', 0)
            volume = analysis.indicators.get('volume', 0)
            value = volume * analysis.indicators.get('close', 0)
            
            # Set last update time
            self._last_update = datetime.now()
            
            return {
                'asi': self._format_number(index_value, 2),
                'asi_raw': index_value,
                'change': change,
                'change_percent': f"{change:.2f}%" if change else "0.00%",
                'volume': self._format_number(volume),
                'volume_raw': volume,
                'value': self._format_currency(value),
                'value_raw': value,
                'market_cap': self._format_currency(total_market_cap),
                'market_cap_raw': total_market_cap,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'last_update': self._last_update.strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"Error fetching market summary: {str(e)}")
            return {}

    def get_historical_data(self, symbol: str, interval: str = '1d', lookback: int = 30) -> List[Dict]:
        """
        Fetch raw synthetic historical data for a given stock symbol.
        NOTE: This method generates synthetic historical data based on the current day's
        OHLCV values from the provider and projects it backwards with random variations.
        It does not fetch true, independent historical data points.
        """
        try:
            # Map interval string to TradingView interval
            interval_mapping = {
                '1d': Interval.INTERVAL_1_DAY,
                '4h': Interval.INTERVAL_4_HOURS,
                '1h': Interval.INTERVAL_1_HOUR,
                '1w': Interval.INTERVAL_1_WEEK,
                '1M': Interval.INTERVAL_1_MONTH
            }
            
            tv_interval = interval_mapping.get(interval, Interval.INTERVAL_1_DAY)
            
            handler = TA_Handler(
                symbol=symbol,
                exchange=self.exchange,
                screener=self.screener,
                interval=tv_interval
            )
            analysis = handler.get_analysis()
            
            if not analysis:
                logger.warning(f"No data returned for {symbol}")
                return []
                
            # Process and format data
            history = []
            # Create historical data from indicators
            # TradingView API doesn't directly provide historical data in a list
            # We'll create a simulated history based on the current data point
            current_close = analysis.indicators.get('close', 0)
            current_open = analysis.indicators.get('open', 0)
            current_high = analysis.indicators.get('high', 0)
            current_low = analysis.indicators.get('low', 0)
            current_volume = analysis.indicators.get('volume', 0)
            
            # Generate synthetic historical data
            from datetime import datetime, timedelta
            
            today = datetime.now()
            for i in range(lookback):
                # Generate a date for each historical data point
                date = today - timedelta(days=lookback-i)
                
                # Add some random variation for realistic data
                import random
                random.seed(i)  # For reproducibility
                
                variation = (random.random() - 0.5) * 0.05  # +/- 2.5% variation
                
                # Calculate values with some variation
                close = current_close * (1 + variation)
                open_price = current_open * (1 + variation * 0.8)
                high = max(close, open_price) * (1 + abs(variation) * 0.3)
                low = min(close, open_price) * (1 - abs(variation) * 0.3)
                volume = current_volume * (0.7 + random.random() * 0.6)  # 70% to 130% of current volume
                
                # Format date to string
                date_str = date.strftime("%Y-%m-%d")
                
                # Add data point to history
                history.append({
                    'date': date_str,
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close,
                    'volume': volume
                })
                
            return history
            
        except Exception as e:
            logger.error(f"Error fetching raw historical data for {symbol}: {str(e)}")
            return []

    def get_historical_data(self, symbol: str, interval: str = '1d', lookback: int = 30) -> Dict:
        """Fetch historical data for a given stock symbol and calculate entry/exit points."""
        try:
            # Get raw historical data
            history = self._get_raw_historical_data(symbol, interval, lookback)
            
            if not history:
                 return {
                    'historical_data': [],
                    'entry_exit_points': {} # Default if no history
                }

            # Calculate entry/exit points and add to response
            entry_exit = self.calculate_entry_exit_points(symbol, historical_data_input=history)
            
            return {
                'historical_data': history,
                'entry_exit_points': entry_exit
            }
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
            return {'historical_data': [], 'entry_exit_points': {}}
    
    def calculate_entry_exit_points(self, symbol, historical_data_input: Optional[List[Dict]] = None):
        """
        Calculate entry and exit points for a given stock based on technical analysis.
        
        Args:
            symbol (str): Stock symbol
            
        Returns:
            dict: Dictionary containing entry, exit points and other analysis data
        """
        try:
            # Get real-time price for the stock
            real_price = self.get_real_time_price(symbol)
            
            # Get historical data for technical indicators
            # Use provided historical data if available, otherwise fetch it
            if historical_data_input is None:
                # Call the internal method to avoid recursion with the public get_historical_data
                historical_data = self._get_raw_historical_data(symbol) 
            else:
                historical_data = historical_data_input
            
            # Create technical analyzer instance
            analyzer = TechnicalAnalyzer()
            
            # Calculate stop loss and take profit based on volatility and price
            # The percentages should vary by stock based on volatility
            volatility_factor = 0.05  # Default 5%
            
            # Higher-priced stocks generally have lower % volatility
            if real_price > 1000:
                volatility_factor = 0.03
            elif real_price > 500:
                volatility_factor = 0.04
            elif real_price < 50:
                volatility_factor = 0.08
                
            # Adjust stop loss and take profit based on volatility
            stop_loss = round(real_price * (1 - volatility_factor), 2)
            take_profit = round(real_price * (1 + (volatility_factor * 3)), 2)  # Risk:Reward of 1:3
            
            # Default values for indicators
            signal_type = 'hold'
            signal_strength = 'neutral'
            rsi_value = 50
            macd_signal = 'neutral'
            bollinger_signal = 'neutral'
            
            if historical_data and len(historical_data) > 14:
                # Extract closing prices
                closes = [d['close'] for d in historical_data]
                
                # Calculate RSI
                rsi_value = analyzer.calculate_rsi(closes)
                
                # Calculate MACD
                macd_data = analyzer.calculate_macd(closes)
                macd_signal = macd_data['signal']
                
                # Calculate Bollinger Bands
                bollinger_data = analyzer.calculate_bollinger_bands(closes)
                bollinger_signal = bollinger_data['signal']
                
                # Perform comprehensive analysis
                analysis = analyzer.analyze_stock(closes)
                
                # Determine signal type based on comprehensive analysis
                signal_type = analysis['recommendation']
                signal_strength = analysis['confidence']
                
                # For buy signals, adjust entry slightly above current to account for momentum
                if signal_type == 'buy':
                    real_price = round(real_price * 1.01, 2)  # 1% above current price
                # For sell signals, adjust entry slightly below current to account for momentum
                elif signal_type == 'sell':
                    real_price = round(real_price * 0.99, 2)  # 1% below current price
            
            return {
                'symbol': symbol,
                'price': real_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'type': signal_type, 
                'strength': signal_strength,
                'rsi': rsi_value,
                'macd': macd_signal,
                'bollinger': bollinger_signal
            }
        except Exception as e:
            self.logger.error(f"Error calculating entry/exit points for {symbol}: {str(e)}")
            # Return default values in case of error
            return {
                'symbol': symbol,
                'price': 100.0,
                'stop_loss': 95.0,
                'take_profit': 115.0,
                'type': 'hold',
                'strength': 'neutral',
                'rsi': 50,
                'macd': 'neutral',
                'bollinger': 'neutral'
            }
    
    def get_stock_list(self) -> List[Dict]:
        """Return a list of available stocks."""
        try:
            # Comprehensive list of Nigerian stocks with proper naming conventions
            return [
                {"symbol": "DANGCEM", "name": "Dangote Cement Plc"},
                {"symbol": "MTNN", "name": "MTN Nigeria Communications Plc"},
                {"symbol": "AIRTELAFRI", "name": "Airtel Africa Plc"},
                {"symbol": "BUACEMENT", "name": "BUA Cement Plc"},
                {"symbol": "GTCO", "name": "Guaranty Trust Holding Company Plc"},
                {"symbol": "ZENITHBANK", "name": "Zenith Bank Plc"},
                {"symbol": "NESTLE", "name": "Nestle Nigeria Plc"},
                {"symbol": "BUAFOODS", "name": "BUA Foods Plc"},
                {"symbol": "ACCESSCORP", "name": "Access Holdings Plc"},
                {"symbol": "UBA", "name": "United Bank for Africa Plc"},
                {"symbol": "FBNH", "name": "FBN Holdings Plc"},
                {"symbol": "TRANSCORP", "name": "Transcorp Plc"},
                {"symbol": "GEREGU", "name": "Geregu Power Plc"},
                {"symbol": "SEPLAT", "name": "Seplat Energy Plc"},
                {"symbol": "OANDO", "name": "Oando Plc"},
                {"symbol": "STANBIC", "name": "Stanbic IBTC Holdings Plc"},
                {"symbol": "GUINNESS", "name": "Guinness Nigeria Plc"},
                {"symbol": "NB", "name": "Nigerian Breweries Plc"},
                {"symbol": "TOTAL", "name": "TotalEnergies Marketing Nigeria Plc"},
                {"symbol": "WAPCO", "name": "Lafarge Africa Plc"},
                {"symbol": "INTBREW", "name": "International Breweries Plc"},
                {"symbol": "JBERGER", "name": "Julius Berger Nigeria Plc"},
                {"symbol": "PRESCO", "name": "Presco Plc"},
                {"symbol": "FIDELITYBK", "name": "Fidelity Bank Plc"},
                {"symbol": "FCMB", "name": "FCMB Group Plc"},
                {"symbol": "FLOURMILL", "name": "Flour Mills of Nigeria Plc"},
                {"symbol": "HONYFLOUR", "name": "Honeywell Flour Mills Plc"},
                {"symbol": "UNILEVER", "name": "Unilever Nigeria Plc"},
                {"symbol": "CUSTODIAN", "name": "Custodian Investment Plc"},
                {"symbol": "FTNCOCOA", "name": "FTN Cocoa Processors Plc"},
                {"symbol": "UCAP", "name": "United Capital Plc"},
                {"symbol": "CADBURY", "name": "Cadbury Nigeria Plc"},
                {"symbol": "NAHCO", "name": "Nigerian Aviation Handling Company Plc"},
                {"symbol": "WEMABANK", "name": "Wema Bank Plc"},
                {"symbol": "ETI", "name": "Ecobank Transnational Incorporated"},
                {"symbol": "DANGSUGAR", "name": "Dangote Sugar Refinery Plc"},
                {"symbol": "NASCON", "name": "NASCON Allied Industries Plc"},
                {"symbol": "UACN", "name": "UAC of Nigeria Plc"},
                {"symbol": "UPDCREIT", "name": "UPDC Real Estate Investment Trust"},
                {"symbol": "UPDC", "name": "UPDC Plc"},
                {"symbol": "CAVERTON", "name": "Caverton Offshore Support Group Plc"},
                {"symbol": "CONOIL", "name": "Conoil Plc"},
                {"symbol": "ETERNA", "name": "Eterna Plc"},
                {"symbol": "JAPAULGOLD", "name": "Japaul Gold & Ventures Plc"},
                {"symbol": "MANSARD", "name": "AXA Mansard Insurance Plc"},
                {"symbol": "NCR", "name": "NCR Nigeria Plc"},
                {"symbol": "NGXGROUP", "name": "Nigerian Exchange Group Plc"},
                {"symbol": "PZ", "name": "PZ Cussons Nigeria Plc"},
                {"symbol": "STERLINGNG", "name": "Sterling Financial Holdings Company Plc"},
                {"symbol": "VERITASKAP", "name": "Veritas Kapital Assurance Plc"},
                {"symbol": "OKOMUOIL", "name": "Okomu Oil Palm Plc"},
                {"symbol": "ARDOVA", "name": "Ardova Plc"},
                {"symbol": "CHAMS", "name": "Chams Holding Company Plc"},
                {"symbol": "CHAMPION", "name": "Champion Breweries Plc"},
                {"symbol": "CUTIX", "name": "Cutix Plc"},
                {"symbol": "DAARCOMM", "name": "DAAR Communications Plc"},
                {"symbol": "LINKASSURE", "name": "Linkage Assurance Plc"},
                {"symbol": "LIVESTOCK", "name": "Livestock Feeds Plc"},
                {"symbol": "MBENEFIT", "name": "Mutual Benefits Assurance Plc"},
                {"symbol": "CORNERST", "name": "Cornerstone Insurance Plc"},
                {"symbol": "MAYBAKER", "name": "May & Baker Nigeria Plc"},
                {"symbol": "NEIMETH", "name": "Neimeth International Pharmaceuticals Plc"},
                {"symbol": "MORISON", "name": "Morison Industries Plc"},
                {"symbol": "VITAFOAM", "name": "Vitafoam Nigeria Plc"}
            ]
        except Exception as e:
            self.logger.error(f"Error getting stock list: {str(e)}")
            return []
            
    def get_real_time_price(self, symbol: str) -> float:
        """
        Get real-time price for a stock symbol.
        In a real implementation, this would fetch from an external API.
        """
        try:
            # Simulate real prices based on common Nigerian stock ranges (as of 2023-2024)
            price_map = {
                "DANGCEM": 480.0,
                "MTNN": 264.2,
                "BUAFOODS": 418.0,
                "BUACEMENT": 93.0,
                "AIRTELAFRI": 2050.0,
                "GTCO": 43.5,
                "ZENITHBANK": 37.8,
                "SEPLAT": 2800.0,
                "TRANSCORP": 12.4,
                "ACCESSCORP": 22.7,
                "UBA": 26.5,
                "GEREGU": 650.0,
                "FBNH": 24.8,
                "STANBIC": 72.0,
                "OANDO": 12.75,
                "GUINNESS": 55.0,
                "NB": 32.9,
                "TOTAL": 350.0,
                "WAPCO": 45.8,
                "NESTLE": 950.0,
                # Additional stock prices
                "INTBREW": 4.2,
                "JBERGER": 48.0,
                "PRESCO": 235.0,
                "FIDELITYBK": 12.8,
                "FCMB": 6.3,
                "FLOURMILL": 37.5,
                "HONYFLOUR": 3.45,
                "UNILEVER": 14.9,
                "CUSTODIAN": 8.5,
                "FTNCOCOA": 1.5,
                "UCAP": 19.6,
                "CADBURY": 17.8,
                "NAHCO": 22.5,
                "WEMABANK": 11.6,
                "ETI": 21.15,
                "DANGSUGAR": 57.0,
                "NASCON": 46.0,
                "UACN": 13.2,
                "UPDCREIT": 3.95,
                "UPDC": 1.22,
                "CAVERTON": 1.3,
                "CONOIL": 115.0,
                "ETERNA": 15.7,
                "JAPAULGOLD": 1.9,
                "MANSARD": 4.5,
                "NCR": 3.61,
                "NGXGROUP": 21.5,
                "PZ": 26.7,
                "STERLINGNG": 4.15,
                "VERITASKAP": 0.5,
                "OKOMUOIL": 320.0,
                "ARDOVA": 25.4,
                "CHAMS": 1.87,
                "CHAMPION": 4.45,
                "CUTIX": 2.51,
                "DAARCOMM": 0.85,
                "LINKASSURE": 1.05,
                "LIVESTOCK": 2.2,
                "MBENEFIT": 0.55,
                "CORNERST": 1.3,
                "MAYBAKER": 7.8,
                "NEIMETH": 2.24,
                "MORISON": 2.55,
                "VITAFOAM": 22.0
            }
            
            # Return the mapped price or a default
            base_price = price_map.get(symbol, 100.0)
            
            # Add slight randomness to simulate market fluctuations (±2%)
            fluctuation = random.uniform(-0.02, 0.02)
            return round(base_price * (1 + fluctuation), 2)
        except Exception as e:
            self.logger.error(f"Error getting real-time price for {symbol}: {str(e)}")
            return 100.0

    def _get_recommendation_explanation(self, analysis) -> str:
        """Generate a detailed explanation for the trading recommendation."""
        recommendation = analysis.summary.get('RECOMMENDATION', 'NEUTRAL')
        oscillators = analysis.oscillators.get('COMPUTE', {})
        moving_averages = analysis.moving_averages.get('COMPUTE', {})
        
        # Count signals
        ma_buy = sum(1 for x in moving_averages.values() if x == 'BUY')
        ma_sell = sum(1 for x in moving_averages.values() if x == 'SELL')
        osc_buy = sum(1 for x in oscillators.values() if x == 'BUY')
        osc_sell = sum(1 for x in oscillators.values() if x == 'SELL')
        
        # Generate explanation
        if recommendation == 'STRONG_BUY':
            return f"Strong buy signals from {ma_buy} moving averages and {osc_buy} oscillators indicate bullish momentum"
        elif recommendation == 'BUY':
            return f"Positive signals from {ma_buy} moving averages suggest upward trend"
        elif recommendation == 'STRONG_SELL':
            return f"Strong sell signals from {ma_sell} moving averages and {osc_sell} oscillators indicate bearish pressure"
        elif recommendation == 'SELL':
            return f"Negative signals from {ma_sell} moving averages suggest downward trend"
        else:
            return "Mixed signals from indicators suggest sideways movement"

    def _get_company_name(self, symbol: str) -> str:
        """Get company name from symbol."""
        company_names = {
            'DANGCEM': 'Dangote Cement Plc',
            'AIRTELAFRI': 'Airtel Africa Plc',
            'MTNN': 'MTN Nigeria Communications Plc',
            'BUACEMENT': 'BUA Cement Plc',
            'NESTLE': 'Nestle Nigeria Plc',
            'GTCO': 'Guaranty Trust Holding Co Plc',
            'ZENITHBANK': 'Zenith Bank Plc',
            'FBNH': 'FBN Holdings Plc',
            'UBA': 'United Bank for Africa Plc',
            'ACCESSCORP': 'Access Holdings Plc',
            'TRANSCORP': 'Transcorp Plc',
            'GEREGU': 'Geregu Power Plc',
            'SEPLAT': 'Seplat Energy Plc',
            'OANDO': 'Oando Plc',
            'BUAFOODS': 'BUA Foods Plc',
            'STANBIC': 'Stanbic IBTC Holdings Plc',
            'GUINNESS': 'Guinness Nigeria Plc',
            'NB': 'Nigerian Breweries Plc',
            'TOTAL': 'TotalEnergies Marketing Nigeria Plc',
            'WAPCO': 'Lafarge Africa Plc',
            'INTBREW': 'International Breweries Plc',
            'JBERGER': 'Julius Berger Nigeria Plc',
            'PRESCO': 'Presco Plc',
            'FIDELITYBK': 'Fidelity Bank Plc',
            'FCMB': 'FCMB Group Plc',
            'FLOURMILL': 'Flour Mills of Nigeria Plc',
            'HONYFLOUR': 'Honeywell Flour Mills Plc',
            'UNILEVER': 'Unilever Nigeria Plc',
            'CUSTODIAN': 'Custodian Investment Plc',
            'FTNCOCOA': 'FTN Cocoa Processors Plc',
            'UCAP': 'United Capital Plc',
            'CADBURY': 'Cadbury Nigeria Plc',
            'NAHCO': 'Nigerian Aviation Handling Company Plc',
            'WEMABANK': 'Wema Bank Plc',
            'ETI': 'Ecobank Transnational Incorporated',
            'DANGSUGAR': 'Dangote Sugar Refinery Plc',
            'NASCON': 'NASCON Allied Industries Plc',
            'UACN': 'UAC of Nigeria Plc',
            'UPDCREIT': 'UPDC Real Estate Investment Trust',
            'UPDC': 'UPDC Plc',
            'CAVERTON': 'Caverton Offshore Support Group Plc',
            'CONOIL': 'Conoil Plc',
            'ETERNA': 'Eterna Plc',
            'JAPAULGOLD': 'Japaul Gold & Ventures Plc',
            'MANSARD': 'AXA Mansard Insurance Plc',
            'NCR': 'NCR Nigeria Plc',
            'NGXGROUP': 'Nigerian Exchange Group Plc',
            'PZ': 'PZ Cussons Nigeria Plc',
            'STERLINGNG': 'Sterling Financial Holdings Company Plc',
            'VERITASKAP': 'Veritas Kapital Assurance Plc',
            'OKOMUOIL': 'Okomu Oil Palm Plc',
            'ARDOVA': 'Ardova Plc',
            'CHAMS': 'Chams Holding Company Plc',
            'CHAMPION': 'Champion Breweries Plc',
            'CUTIX': 'Cutix Plc',
            'DAARCOMM': 'DAAR Communications Plc',
            'LINKASSURE': 'Linkage Assurance Plc',
            'LIVESTOCK': 'Livestock Feeds Plc',
            'MBENEFIT': 'Mutual Benefits Assurance Plc',
            'CORNERST': 'Cornerstone Insurance Plc',
            'MAYBAKER': 'May & Baker Nigeria Plc',
            'NEIMETH': 'Neimeth International Pharmaceuticals Plc',
            'MORISON': 'Morison Industries Plc',
            'VITAFOAM': 'Vitafoam Nigeria Plc'
        }
        return company_names.get(symbol, symbol)

    @staticmethod
    def _format_currency(value: float) -> str:
        """Format value as Nigerian Naira."""
        if value >= 1_000_000_000_000:  # Trillion
            return f"₦{value/1_000_000_000_000:.2f}T"
        elif value >= 1_000_000_000:  # Billion
            return f"₦{value/1_000_000_000:.2f}B"
        elif value >= 1_000_000:  # Million
            return f"₦{value/1_000_000:.2f}M"
        elif value >= 1_000:  # Thousand
            return f"₦{value/1_000:.2f}K"
        else:
            return f"₦{value:.2f}"

    @staticmethod
    def _format_number(value: float, decimals: int = 2) -> str:
        """Format large numbers with K, M, B, T suffixes."""
        if value >= 1_000_000_000_000:  # Trillion
            return f"{value/1_000_000_000_000:.{decimals}f}T"
        elif value >= 1_000_000_000:  # Billion
            return f"{value/1_000_000_000:.{decimals}f}B"
        elif value >= 1_000_000:  # Million
            return f"{value/1_000_000:.{decimals}f}M"
        elif value >= 1_000:  # Thousand
            return f"{value/1_000:.{decimals}f}K"
        else:
            return f"{value:.{decimals}f}"
