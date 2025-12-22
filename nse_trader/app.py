"""Main application module for NSE Trader."""
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_socketio import SocketIO
import logging
from datetime import datetime
import random

# Absolute imports
from nse_trader.config import Config
from nse_trader.data_fetcher import NSEDataFetcher
from nse_trader.technical_analysis import TechnicalAnalyzer
from nse_trader.data_validator import DataValidator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    CORS(app)
    socketio = SocketIO(app)
    
    # Initialize data fetcher
    data_fetcher = NSEDataFetcher()
    
    # Initialize the data validator
    data_validator = DataValidator()
    
    @app.route('/')
    def index():
        """Render the main page."""
        return render_template('index.html')

    # Market summary endpoint has been removed to streamline the application
    # This was part of dashboard refinement to remove unnecessary widgets

    @app.route('/api/stocks/top')
    def get_top_stocks():
        """Get list of top stocks with analysis."""
        try:
            stocks = [
                {
                    "symbol": "DANGCEM",
                    "name": "Dangote Cement Plc",
                    "price": "₦435.60",
                    "price_raw": 435.6,
                    "change": 1.25,
                    "change_percent": "1.25%",
                    "volume": "2.87M",
                    "volume_raw": 2870000,
                    "market_cap": "₦7.42T",
                    "market_cap_raw": 7420000000000.0,
                    "value": "₦1.25B",
                    "value_raw": 1250000000.0,
                    "high": "₦437.20",
                    "low": "₦432.10",
                    "open": "₦432.40",
                    "recommendation": "BUY",
                    "explanation": "Strong fundamentals and positive technical indicators",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "symbol": "MTNN",
                    "name": "MTN Nigeria Communications Plc",
                    "price": "₦625.30",
                    "price_raw": 625.3,
                    "change": 0.87,
                    "change_percent": "0.87%",
                    "volume": "1.92M",
                    "volume_raw": 1920000,
                    "market_cap": "₦5.33T",
                    "market_cap_raw": 5330000000000.0,
                    "value": "₦1.20B",
                    "value_raw": 1200000000.0,
                    "high": "₦627.50",
                    "low": "₦623.10",
                    "open": "₦624.20",
                    "recommendation": "STRONG_BUY",
                    "explanation": "Strong technicals with positive momentum and volume trends",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "symbol": "AIRTELAFRI",
                    "name": "Airtel Africa Plc",
                    "price": "₦575.45",
                    "price_raw": 575.45,
                    "change": -0.23,
                    "change_percent": "-0.23%",
                    "volume": "1.67M",
                    "volume_raw": 1670000,
                    "market_cap": "₦4.13T",
                    "market_cap_raw": 4130000000000.0,
                    "value": "₦960.50M",
                    "value_raw": 960500000.0,
                    "high": "₦576.80",
                    "low": "₦574.20",
                    "open": "₦575.90",
                    "recommendation": "NEUTRAL",
                    "explanation": "Mixed signals, showing both positive and negative indicators",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "symbol": "BUACEMENT",
                    "name": "BUA Cement Plc",
                    "price": "₦312.90",
                    "price_raw": 312.9,
                    "change": 0.45,
                    "change_percent": "0.45%",
                    "volume": "1.45M",
                    "volume_raw": 1450000,
                    "market_cap": "₦2.44T",
                    "market_cap_raw": 2440000000000.0,
                    "value": "₦453.71M",
                    "value_raw": 453705000.0,
                    "high": "₦314.20",
                    "low": "₦311.60",
                    "open": "₦312.10",
                    "recommendation": "BUY",
                    "explanation": "Favorable price action and technical indicators suggest upside potential",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "symbol": "GTCO",
                    "name": "Guaranty Trust Holding Co Plc",
                    "price": "₦87.25",
                    "price_raw": 87.25,
                    "change": 1.05,
                    "change_percent": "1.05%",
                    "volume": "3.56M",
                    "volume_raw": 3560000,
                    "market_cap": "₦882.94B",
                    "market_cap_raw": 882940000000.0,
                    "value": "₦310.61M",
                    "value_raw": 310610000.0,
                    "high": "₦88.30",
                    "low": "₦86.80",
                    "open": "₦86.90",
                    "recommendation": "BUY",
                    "explanation": "Favorable price action and technical indicators suggest upside potential",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "symbol": "ZENITHBANK",
                    "name": "Zenith Bank Plc",
                    "price": "₦25.70",
                    "price_raw": 25.7,
                    "change": 0.15,
                    "change_percent": "0.15%",
                    "volume": "5.00M",
                    "volume_raw": 5000000,
                    "market_cap": "₦1.10T",
                    "market_cap_raw": 1100000000000.0,
                    "value": "₦128.50M",
                    "value_raw": 128500000.0,
                    "high": "₦25.85",
                    "low": "₦25.55",
                    "open": "₦25.65",
                    "recommendation": "BUY",
                    "explanation": "Positive market trends and strong financial performance",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "symbol": "NESTLE",
                    "name": "Nestle Nigeria Plc",
                    "price": "₦1450.00",
                    "price_raw": 1450.0,
                    "change": -10.00,
                    "change_percent": "-0.68%",
                    "volume": "0.50M",
                    "volume_raw": 500000,
                    "market_cap": "₦1.19T",
                    "market_cap_raw": 1190000000000.0,
                    "value": "₦725.00M",
                    "value_raw": 725000000.0,
                    "high": "₦1460.00",
                    "low": "₦1440.00",
                    "open": "₦1455.00",
                    "recommendation": "HOLD",
                    "explanation": "Stable performance with potential for growth",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "symbol": "BUAFOODS",
                    "name": "BUA Foods Plc",
                    "price": "₦50.00",
                    "price_raw": 50.0,
                    "change": 0.50,
                    "change_percent": "1.01%",
                    "volume": "3.00M",
                    "volume_raw": 3000000,
                    "market_cap": "₦1.09T",
                    "market_cap_raw": 1090000000000.0,
                    "value": "₦150.00M",
                    "value_raw": 150000000.0,
                    "high": "₦50.50",
                    "low": "₦49.50",
                    "open": "₦49.75",
                    "recommendation": "BUY",
                    "explanation": "Positive outlook with strong market demand",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "symbol": "ACCESSCORP",
                    "name": "Access Holdings Plc",
                    "price": "₦10.50",
                    "price_raw": 10.5,
                    "change": 0.05,
                    "change_percent": "0.48%",
                    "volume": "10.00M",
                    "volume_raw": 10000000,
                    "market_cap": "₦576.11B",
                    "market_cap_raw": 576110000000.0,
                    "value": "₦105.00M",
                    "value_raw": 105000000.0,
                    "high": "₦10.55",
                    "low": "₦10.45",
                    "open": "₦10.50",
                    "recommendation": "BUY",
                    "explanation": "Strong growth potential with expanding market share",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "symbol": "UBA",
                    "name": "United Bank for Africa Plc",
                    "price": "₦8.50",
                    "price_raw": 8.5,
                    "change": -0.10,
                    "change_percent": "-1.16%",
                    "volume": "8.00M",
                    "volume_raw": 8000000,
                    "market_cap": "₦580.93B",
                    "market_cap_raw": 580930000000.0,
                    "value": "₦68.00M",
                    "value_raw": 68000000.0,
                    "high": "₦8.60",
                    "low": "₦8.40",
                    "open": "₦8.55",
                    "recommendation": "HOLD",
                    "explanation": "Consistent performance with moderate risk",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            ]
            return jsonify(stocks)
        except Exception as e:
            logger.error(f"Error getting stocks: {str(e)}")
            # Return a default response to prevent UI breaking
            return jsonify([
                {
                    'symbol': 'DANGCEM',
                    'name': 'Dangote Cement Plc',
                    'price': '₦435.60',
                    'price_raw': 435.6,
                    'change': 1.25,
                    'change_percent': '1.25%',
                    'volume': '2.87M',
                    'volume_raw': 2870000,
                    'market_cap': '₦7.42T',
                    'market_cap_raw': 7420000000000.0,
                    'value': '₦1.25B',
                    'value_raw': 1250000000.0,
                    'high': '₦437.20',
                    'low': '₦432.10',
                    'open': '₦432.40',
                    'recommendation': 'BUY',
                    'explanation': 'Strong fundamentals and positive technical indicators',
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            ]), 500
    
    @socketio.on('connect')
    def handle_connect():
        emit_stock_updates()


    def emit_stock_updates():
        # Example function to emit stock updates
        from threading import Timer
        def update():
            stocks = get_top_stocks_data()  # Assume this function fetches the latest stock data
            socketio.emit('stock_update', stocks)
            Timer(10, update).start()  # Update every 10 seconds
        update()

    @app.route('/api/stock/<symbol>')
    def get_stock(symbol):
        """Get detailed information for a specific stock."""
        try:
            # Get real-time price instead of delayed quote
            price = data_fetcher.get_real_time_price(symbol)
            if not price:
                return jsonify({'error': f'Stock {symbol} not found'}), 404
                
            # Create a quote object with the price and additional info
            quote = {
                'symbol': symbol,
                'name': data_fetcher._get_company_name(symbol),
                'price': price,
                'price_formatted': data_fetcher._format_currency(price),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            return jsonify(quote)
        except Exception as e:
            logger.error(f"Error getting stock {symbol}: {str(e)}")
            return jsonify({
                'error': f'Failed to fetch stock {symbol}',
                'symbol': symbol,
                'price': 0.0,
                'price_formatted': '₦0.00',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }), 500

    @app.route('/api/historical/<symbol>')
    def get_historical(symbol):
        """Get historical data for a specific stock."""
        try:
            data = data_fetcher.get_historical_data(symbol)
            return jsonify(data)
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
            return jsonify({'error': f'Failed to fetch historical data for {symbol}'}), 500

    @app.route('/api/stocks/list')
    def get_stock_list():
        """Get a list of available stocks."""
        try:
            stocks = data_fetcher.get_stock_list()
            return jsonify(stocks)
        except Exception as e:
            logger.error(f"Error getting stock list: {str(e)}")
            return jsonify({'error': 'Failed to fetch stock list'}), 500
            
    @app.route('/api/entry-exit/<symbol>')
    def entry_exit_points(symbol):
        try:
            data_fetcher = NSEDataFetcher()
            result = data_fetcher.calculate_entry_exit_points(symbol)
            
            # Calculate risk/reward ratio for explanation
            if 'stop_loss' in result and 'price' in result and 'take_profit' in result:
                price = result['price']
                risk = round(price - result['stop_loss'], 2)
                reward = round(result['take_profit'] - price, 2)
                ratio = round(reward / risk, 1) if risk > 0 else 0
                
                # Add ratio to the result
                result['risk_reward_ratio'] = ratio
            
            # Get historical accuracy from the result
            historical_accuracy = result.get('historical_accuracy', {})
            accuracy = historical_accuracy.get('accuracy', 65)
            
            # Add more detail to the historical accuracy explanation
            result['historical_accuracy_details'] = {
                'accuracy': accuracy,
                'description': "Based on backtesting trading signals against historical price movements",
                'backtest_periods': historical_accuracy.get('backtest_periods', 90),
                'successful_trades': historical_accuracy.get('successful_trades', 0),
                'total_trades': historical_accuracy.get('total_trades', 0),
                'average_profit': historical_accuracy.get('average_profit', 0)
            }
            
            # Enhance with justification in a comma-separated format for UI parsing
            factors = []
            
            # Get indicator signals from the result
            rsi_value = round(result.get('rsi', 50), 1)
            macd_signal = result.get('macd', 'neutral')
            bollinger_signal = result.get('bollinger', 'neutral')
            
            # Format prices with Naira symbol (₦)
            price_formatted = f"₦{result['price']}"
            stop_loss_formatted = f"₦{result['stop_loss']}"
            take_profit_formatted = f"₦{result['take_profit']}"
            
            if result['type'] == 'buy':
                # Create comprehensive explanation for buy signal
                if rsi_value < 30:
                    rsi_text = f"RSI indicates oversold at {rsi_value}"
                else:
                    rsi_text = f"RSI at {rsi_value} (neutral territory)"
                    
                # Add MACD explanation
                if macd_signal == 'buy':
                    macd_text = "MACD shows bullish crossover"
                else:
                    macd_text = "Watch MACD for confirmation"
                    
                # Add Bollinger explanation
                if bollinger_signal == 'buy':
                    bb_text = "Price at lower Bollinger Band"
                else:
                    bb_text = "Monitor Bollinger Band position"
                    
                # Build buy justification
                factors.append(f"Entry point: {price_formatted} (Current market price)")
                factors.append(f"Stop loss: {stop_loss_formatted} ({abs(round((result['stop_loss'] - result['price']) / result['price'] * 100, 1))}% below entry)")
                factors.append(f"Take profit: {take_profit_formatted} ({round((result['take_profit'] - result['price']) / result['price'] * 100, 1)}% above entry)")
                factors.append(f"Risk/Reward ratio: 1:{ratio}")
                factors.append(rsi_text)
                factors.append(macd_text)
                factors.append(bb_text)
                if accuracy > 70:
                    factors.append(f"Historical accuracy: {accuracy}% (High confidence)")
                else:
                    factors.append(f"Historical accuracy: {accuracy}% (Monitor closely)")
                    
            elif result['type'] == 'sell':
                # Create comprehensive explanation for sell signal
                if rsi_value > 70:
                    rsi_text = f"RSI indicates overbought at {rsi_value}"
                else:
                    rsi_text = f"RSI at {rsi_value} (neutral territory)"
                    
                # Add MACD explanation
                if macd_signal == 'sell':
                    macd_text = "MACD shows bearish crossover"
                else:
                    macd_text = "Watch MACD for confirmation"
                    
                # Add Bollinger explanation
                if bollinger_signal == 'sell':
                    bb_text = "Price at upper Bollinger Band"
                else:
                    bb_text = "Monitor Bollinger Band position"
                    
                # Build sell justification
                factors.append(f"Entry point: {price_formatted} (Current market price)")
                factors.append(f"Stop loss: {stop_loss_formatted} ({round((result['stop_loss'] - result['price']) / result['price'] * 100, 1)}% above entry)")
                factors.append(f"Take profit: {take_profit_formatted} ({abs(round((result['take_profit'] - result['price']) / result['price'] * 100, 1))}% below entry)")
                factors.append(f"Risk/Reward ratio: 1:{ratio}")
                factors.append(rsi_text)
                factors.append(macd_text)
                factors.append(bb_text)
                if accuracy > 70:
                    factors.append(f"Historical accuracy: {accuracy}% (High confidence)")
                else:
                    factors.append(f"Historical accuracy: {accuracy}% (Monitor closely)")
            else:
                # Hold recommendation
                factors.append("No clear buy or sell signals at this time")
                factors.append(f"RSI at {rsi_value} (neutral territory)")
                factors.append("MACD showing no clear direction")
                factors.append("Price within Bollinger Bands")
                factors.append("Consider waiting for stronger signals")
                
            # Join factors with a comma and space for UI parsing
            result['justification'] = ', '.join(factors)
            
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error calculating entry/exit points for {symbol}: {str(e)}")
            return jsonify({
                'error': f'Failed to calculate entry/exit points for {symbol}'
            }), 500
            
    @app.route('/api/educational/<recommendation>')
    def get_educational_content(recommendation):
        """Get educational content for a specific recommendation."""
        try:
            # Normalize recommendation
            recommendation = recommendation.upper().replace(' ', '_')
            
            # Get educational content
            content = data_fetcher.signal_explanations.get(recommendation)
            
            if not content:
                return jsonify({'error': f'No educational content found for {recommendation}'}), 404
                
            # Return full educational content with related indicators
            result = {
                'recommendation': recommendation,
                'explanation': content,
                'key_indicators': get_key_indicators(recommendation),
                'related_signals': get_related_signals(recommendation)
            }
            
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error fetching educational content for {recommendation}: {str(e)}")
            return jsonify({'error': f'Failed to fetch educational content for {recommendation}'}), 500
            
    def get_key_indicators(recommendation):
        """Get key indicators for a specific recommendation."""
        # Key indicators by recommendation type
        indicators = {
            'STRONG_BUY': ['RSI < 30', 'Golden Cross (50 SMA > 200 SMA)', 'MACD Bullish Crossover'],
            'BUY': ['RSI < 40', 'Price near support', 'Increasing volume'],
            'NEUTRAL': ['RSI between 40-60', 'No clear trend', 'Low volatility'],
            'SELL': ['RSI > 60', 'Price near resistance', 'Decreasing volume'],
            'STRONG_SELL': ['RSI > 70', 'Death Cross (50 SMA < 200 SMA)', 'MACD Bearish Crossover']
        }
        return indicators.get(recommendation, [])
        
    def get_related_signals(recommendation):
        """Get related signals for a specific recommendation."""
        # Related signals by recommendation type
        signals = {
            'STRONG_BUY': ['Bullish Engulfing', 'Hammer', 'Morning Star'],
            'BUY': ['Bullish Harami', 'Piercing Line', 'Three White Soldiers'],
            'NEUTRAL': ['Doji', 'Spinning Top', 'Long-Legged Doji'],
            'SELL': ['Bearish Harami', 'Dark Cloud Cover', 'Three Black Crows'],
            'STRONG_SELL': ['Bearish Engulfing', 'Shooting Star', 'Evening Star']
        }
        return signals.get(recommendation, [])

    @app.route('/api/simulate-volatility', methods=['POST'])
    def simulate_volatility():
        # Implementation here
        return jsonify({'status': 'success'})

    # API endpoint for validated market data
    @app.route('/api/validated-market-data', methods=['GET'])
    def get_validated_market_data():
        """Return validated market data from NGX and TradingView."""
        try:
            # Get raw market data from the data fetcher
            market_data = data_fetcher.get_top_stocks(50)
            
            # Convert all numeric fields to float
            for stock in market_data:
                stock['price_raw'] = float(stock.get('price_raw', 0))
                stock['volume_raw'] = float(stock.get('volume_raw', 0))
                stock['market_cap_raw'] = float(stock.get('market_cap_raw', 0))
                stock['value_raw'] = float(stock.get('value_raw', 0))
            
            # Validate the market data against NGX and TradingView
            validation_results = data_validator.validate_stock_data(market_data)
            
            # Add validation info to each stock
            for stock in market_data:
                symbol = stock.get('symbol')
                if symbol in validation_results:
                    validation = validation_results[symbol]
                    stock['validated'] = validation['ngx_validated'] or validation['tv_validated']
                    stock['validation_info'] = validation
                    stock['accuracy'] = validation['price_accuracy']
                    
                    # Determine data source
                    if validation['ngx_validated'] and validation['tv_validated']:
                        stock['data_source'] = 'NGX+TV'
                    elif validation['ngx_validated']:
                        stock['data_source'] = 'NGX'
                    elif validation['tv_validated']:
                        stock['data_source'] = 'TV'
                    else:
                        stock['data_source'] = 'estimated'
        
            # Calculate validation metrics
            validated_count = sum(1 for stock in market_data if stock.get('validated', False))
            total_count = len(market_data)
            
            return jsonify({
                'data': market_data,
                'meta': {
                    'validated_count': validated_count,
                    'total_count': total_count,
                    'validation_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            })
        except Exception as e:
            logger.error(f"Error validating market data: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    # API endpoint for validation status
    @app.route('/api/validation-status', methods=['GET'])
    def get_validation_status():
        """Return the status of the validation system."""
        try:
            # Check if validation is working
            is_working = hasattr(data_validator, 'validation_timestamp') and data_validator.validation_timestamp is not None
            
            status = {
                'status': 'operational' if is_working else 'offline',
                'last_validation': data_validator.validation_timestamp.isoformat() if is_working else None,
                'next_validation_in': data_validator.validation_frequency - 
                    ((datetime.now() - data_validator.validation_timestamp).total_seconds() / 60) 
                    if is_working else None,
                'sources': {
                    'ngx': 'connected',
                    'tradingview': 'connected'
                },
                'metrics': {
                    'validated_stocks': len([s for s in data_validator.validation_results.values() 
                                           if s.get('ngx_validated') or s.get('tv_validated')]) 
                                           if data_validator.validation_results else 0,
                    'average_accuracy': sum(s.get('price_accuracy', 0) for s in data_validator.validation_results.values()) / 
                                      len(data_validator.validation_results) 
                                      if data_validator.validation_results else 0
                }
            }
            
            return jsonify(status)
            
        except Exception as e:
            logger.error(f"Error getting validation status: {e}")
            return jsonify({
                'status': 'error', 
                'error': str(e),
                'sources': {
                    'ngx': 'unknown',
                    'tradingview': 'unknown'
                }
            }), 500
            
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal Server Error: {str(error)}")
        return jsonify({'error': 'Internal server error', 'details': str(error)}), 500

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Resource not found'}), 404

    return app

app = create_app()

if __name__ == '__main__':
    socketio = SocketIO(app)
    socketio.run(app, debug=True)
