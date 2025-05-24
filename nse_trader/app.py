"""Main application module for NSE Trader."""
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import logging
from datetime import datetime

from .config import Config
from .data_fetcher import NSEDataFetcher

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    CORS(app)
    
    # Initialize data fetcher
    data_fetcher = NSEDataFetcher()

    @app.route('/')
    def index():
        """Render the main page."""
        return render_template('index.html')

    @app.route('/api/market-summary')
    def market_summary():
        """Get NSE market summary data."""
        try:
            summary = data_fetcher.get_market_summary()
            
            # Ensure all expected fields exist
            if not summary:
                summary = {}
            
            if 'asi' not in summary:
                summary['asi'] = '54,235.12'
            if 'change' not in summary:
                summary['change'] = 1.25
            if 'change_percent' not in summary:
                summary['change_percent'] = '▲ 1.25%'
            if 'market_cap' not in summary:
                summary['market_cap'] = '₦29.48T'
            if 'volume' not in summary:
                summary['volume'] = '325.6M'
            if 'value' not in summary:
                summary['value'] = '₦5.82B'
            if 'last_update' not in summary:
                summary['last_update'] = datetime.now().isoformat()
                
            return jsonify(summary)
        except Exception as e:
            app.logger.error(f"Error fetching market summary: {str(e)}")
            # Return default data in case of error to prevent UI breaking
            return jsonify({
                'asi': '54,235.12',
                'change': 1.25,
                'change_percent': '▲ 1.25%',
                'market_cap': '₦29.48T',
                'volume': '325.6M',
                'value': '₦5.82B',
                'last_update': datetime.now().isoformat()
            }), 500

    @app.route('/api/stocks/top')
    def get_top_stocks():
        """Get list of top stocks with analysis."""
        try:
            stocks = data_fetcher.get_top_stocks(limit=10)
            return jsonify(stocks)
        except Exception as e:
            logger.error(f"Error getting stocks: {str(e)}")
            return jsonify({'error': 'Failed to fetch stocks'}), 500
    
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
                'timestamp': datetime.now().isoformat()
            }
            return jsonify(quote)
        except Exception as e:
            logger.error(f"Error getting stock {symbol}: {str(e)}")
            return jsonify({'error': f'Failed to fetch stock {symbol}'}), 500

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
                    rsi_text = f"RSI at {rsi_value}"
                    
                # Add MACD explanation
                if macd_signal == 'buy':
                    macd_text = "MACD shows bullish crossover"
                else:
                    macd_text = "Watch MACD for confirmation"
                    
                # Add Bollinger Bands explanation
                if bollinger_signal == 'buy':
                    bollinger_text = "Price at/below lower Bollinger Band"
                else:
                    bollinger_text = "Monitor Bollinger Bands for support levels"
                    
                entry_text = f"Entry point {price_formatted} with potential {round((result['take_profit']/result['price']-1)*100, 1)}% upside"
                stop_text = f"Stop loss at {stop_loss_formatted} ({round((1-result['stop_loss']/result['price'])*100, 1)}% risk)"
                
                factors = [
                    rsi_text,
                    macd_text,
                    bollinger_text,
                    f"Risk-to-reward ratio of 1:{ratio}",
                    entry_text,
                    stop_text
                ]
            elif result['type'] == 'sell':
                # Create comprehensive explanation for sell signal
                if rsi_value > 70:
                    rsi_text = f"RSI indicates overbought at {rsi_value}"
                else:
                    rsi_text = f"RSI at {rsi_value}"
                    
                # Add MACD explanation
                if macd_signal == 'sell':
                    macd_text = "MACD shows bearish crossover"
                else:
                    macd_text = "Watch MACD for confirmation"
                    
                # Add Bollinger Bands explanation
                if bollinger_signal == 'sell':
                    bollinger_text = "Price at/above upper Bollinger Band"
                else:
                    bollinger_text = "Monitor Bollinger Bands for resistance levels"
                    
                entry_text = f"Entry point {price_formatted} with potential {round((1-result['stop_loss']/result['price'])*100, 1)}% downside"
                stop_text = f"Stop loss at {take_profit_formatted} ({round((result['take_profit']/result['price']-1)*100, 1)}% risk)"
                
                factors = [
                    rsi_text,
                    macd_text,
                    bollinger_text,
                    f"Risk-to-reward ratio of 1:{ratio}",
                    entry_text,
                    stop_text
                ]
            else:
                # Create explanation for neutral/hold signal
                factors = [
                    f"RSI at neutral level {rsi_value}",
                    "No clear technical signals at current price",
                    f"Current price: {price_formatted}",
                    f"Monitor for breakout above {take_profit_formatted} or breakdown below {stop_loss_formatted}",
                    f"Signal strength: {result['strength'].capitalize()}"
                ]
            
            # Add justification text
            result['justification'] = ', '.join(factors)
            
            # Ensure all required fields exist
            # Ensure all required fields exist - corrected indentation
            if 'price' not in result:
                result['price'] = 100.0
            if 'stop_loss' not in result:
                result['stop_loss'] = result['price'] * 0.95
            if 'take_profit' not in result:
                result['take_profit'] = result['price'] * 1.15
                
            return jsonify(result)
        except Exception as e:
            app.logger.error(f"Error calculating entry/exit points for {symbol}: {str(e)}")
            return jsonify({
                'error': f"Could not calculate entry/exit points for {symbol}",
                'price': 100.0,
                'stop_loss': 95.0,
                'take_profit': 115.0,
                'justification': 'Error occurred, using default values',
                'type': 'hold',
                'strength': 'neutral',
                'rsi': 50,
                'macd': 'neutral',
                'bollinger': 'neutral'
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

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
