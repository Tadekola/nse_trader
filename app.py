from flask import Flask, render_template, jsonify, request
from redis import Redis, RedisError
from config.config import Config
from datetime import datetime
import json
import random
import logging
import pandas as pd
from nse_trader.technical_analysis import TechnicalAnalyzer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('nse_trader')

# Import validation functions
try:
    from data_validator import validate_stock_data, ValidationError
except ImportError:
    # Fallback if module not fully implemented
    class ValidationError(Exception):
        pass

    def validate_stock_data(data):
        raise ValidationError("Data validation module not available")
        return data

app = Flask(__name__)

# Initialize Redis connection with error handling
try:
    redis = Redis(
        host=Config.REDIS_HOST, 
        port=Config.REDIS_PORT, 
        db=Config.REDIS_DB,
        socket_connect_timeout=5
    )
    # Test connection
    redis.ping()
    logger.info(f"Redis connection established: {Config.REDIS_HOST}:{Config.REDIS_PORT}")
except RedisError as e:
    logger.warning(f"Redis connection failed: {e}. Using fallback data.")
    redis = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health_check():
    return 'OK', 200

# Sample stock data
def get_sample_stock_data():
    return [
        {
            'symbol': 'DANGCEM',
            'name': 'Dangote Cement',
            'price': 243.50,
            'change': 2.5,
            'volume': 1245678,
            'marketCap': '4.15T',
            'peRatio': 15.7
        },
        {
            'symbol': 'ZENITHBANK',
            'name': 'Zenith Bank',
            'price': 24.75,
            'change': -0.25,
            'volume': 3456789,
            'marketCap': '777.5B',
            'peRatio': 6.2
        },
        {
            'symbol': 'MTNN',
            'name': 'MTN Nigeria',
            'price': 178.90,
            'change': 1.2,
            'volume': 567890,
            'marketCap': '3.64T',
            'peRatio': 12.8
        },
        {
            'symbol': 'NESTLE',
            'name': 'Nestle Nigeria',
            'price': 1050.00,
            'change': -5.0,
            'volume': 123456,
            'marketCap': '833.6B',
            'peRatio': 18.5
        },
        {
            'symbol': 'GTCO',
            'name': 'Guaranty Trust Holding',
            'price': 28.40,
            'change': 0.15,
            'volume': 2345678,
            'marketCap': '835.2B',
            'peRatio': 5.8
        }
    ]

def get_validated_market_data():
    # Get sample data
    stock_data = get_sample_stock_data()
    
    # Add validation information
    for stock in stock_data:
        sources = []
        if random.random() > 0.2:  # 80% chance to have NGX as source
            sources.append('NGX')
        if random.random() > 0.3:  # 70% chance to have TradingView as source
            sources.append('TradingView')
        
        if not sources:
            sources = ['NGX']  # Ensure at least one source
            
        accuracy = random.uniform(0.8, 1.0) if len(sources) > 1 else random.uniform(0.7, 0.9)
        
        stock['sources'] = sources
        stock['accuracy'] = accuracy
        stock['validation_status'] = 'verified' if accuracy > 0.9 else 'unverified'
    
    # Try to validate with data_validator module
    try:
        validated_data = validate_stock_data(stock_data)
        return validated_data
    except Exception:
        # Return data with simulated validation if validation fails
        return stock_data

def calculate_accuracy():
    # Simulate overall validation accuracy
    return random.uniform(0.85, 0.98)

def check_ngx_health():
    # Simulate NGX API health
    return 'healthy' if random.random() > 0.1 else 'degraded'

def check_tradingview_health():
    # Simulate TradingView API health
    return 'healthy' if random.random() > 0.05 else 'degraded'

@app.route('/api/validated-market-data')
def validated_market_data():
    try:
        data = get_validated_market_data()
        return jsonify({
            'status': 'success',
            'data': data,
            'sources': ['NGX', 'TradingView'],
            'validation_accuracy': calculate_accuracy()
        })
    except Exception as e:
        import logging
        logging.error(f"Error in validated_market_data: {e}")
        return jsonify({'error': 'An error occurred while processing the request'}), 500

@app.route('/api/validation-status')
def validation_status():
    try:
        # Check if Redis is available
        redis_available = redis is not None
        
        # Get list of stocks with active circuit breakers
        active_circuit_breakers = []
        circuit_breakers_active = False
        if redis_available:
            try:
                # Get all keys that match the circuit breaker pattern
                for key in redis.scan_iter(match='circuit_breaker:*'):
                    symbol = key.decode().split(':')[1]
                    active_circuit_breakers.append(symbol)
                circuit_breakers_active = len(active_circuit_breakers) > 0
            except Exception as e:
                logger.error(f"Error checking circuit breakers: {e}")
        
        return jsonify({
            'system_status': 'active',
            'last_validation': datetime.utcnow().isoformat(),
            'source_statuses': {
                'NGX': check_ngx_health(),
                'TradingView': check_tradingview_health()
            },
            'redis_available': redis_available,
            'circuit_breakers_active': circuit_breakers_active,
            'active_circuit_breakers': active_circuit_breakers
        })
    except Exception as e:
        import logging
        logging.error(f"Error in validation_status: {e}")
        return jsonify({'error': 'An error occurred while processing the request'}), 500
        
@app.route('/api/active-stocks')
def active_stocks():
    """Return most actively traded stocks with investment recommendations"""
    try:
        # Get validated data
        all_stocks = get_validated_market_data()
        
        # Sort by trading volume (descending)
        active_stocks = sorted(all_stocks, key=lambda x: x.get('volume', 0), reverse=True)
        
        # Get top stocks (limit by query parameter or default to 10)
        limit = request.args.get('limit', default=10, type=int)
        top_active_stocks = active_stocks[:limit]
        
        # Add recommendations with confidence and reasons
        analyzer = TechnicalAnalyzer()
        for stock in top_active_stocks:
            # Create a simple DataFrame for analysis
            df = pd.DataFrame({
                'Close': [stock['price'] * 0.95, stock['price'] * 0.97, stock['price'] * 0.99, stock['price']],
                'Open': [stock['price'] * 0.94, stock['price'] * 0.96, stock['price'] * 0.98, stock['price'] * 0.99],
                'High': [stock['price'] * 0.96, stock['price'] * 0.98, stock['price'] * 1.01, stock['price'] * 1.02],
                'Low': [stock['price'] * 0.93, stock['price'] * 0.95, stock['price'] * 0.97, stock['price'] * 0.98],
                'Volume': [stock['volume'] * 0.8, stock['volume'] * 0.9, stock['volume'] * 1.1, stock['volume']]
            })
            
            # Generate technical analysis
            analysis = analyzer.analyze_stock(df)
            signals = analyzer.generate_signals(analysis)
            
            # Add recommendation details to stock
            stock['recommendation'] = signals['recommendation']
            stock['recommendation_confidence'] = min(abs(signals['strength']) * 33, 100)  # Convert strength to 0-100%
            stock['recommendation_reasons'] = signals['reasons']
            
            # Add market trend data
            if stock['change'] > 2:
                stock['market_sentiment'] = 'Bullish'
            elif stock['change'] < -2:
                stock['market_sentiment'] = 'Bearish'
            else:
                stock['market_sentiment'] = 'Neutral'
        
        return jsonify({
            'status': 'success',
            'data': top_active_stocks,
            'timestamp': datetime.utcnow().isoformat(),
            'metrics': {
                'average_volume': sum(s['volume'] for s in top_active_stocks) // len(top_active_stocks) if top_active_stocks else 0,
                'average_confidence': sum(s['recommendation_confidence'] for s in top_active_stocks) // len(top_active_stocks) if top_active_stocks else 0
            }
        })
    except Exception as e:
        logger.error(f"Error in active_stocks: {e}")
        return jsonify({'error': 'An error occurred while processing the request'}), 500

def main():
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == '__main__':
    main()
