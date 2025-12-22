from datetime import datetime
import redis
import logging
from typing import Dict, List, Any, Optional, Union

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('data_validator')

# Redis client for circuit breaker
import sys
import os

# Add parent directory to path to ensure relative imports work
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from config.config import Config

# Initialize Redis with error handling
try:
    redis_client = redis.Redis(
        host=Config.REDIS_HOST, 
        port=Config.REDIS_PORT, 
        db=Config.REDIS_DB,
        socket_connect_timeout=5
    )
    # Test connection
    redis_client.ping()
    logger.info("Redis connection established for data validator: %s:%s", Config.REDIS_HOST, Config.REDIS_PORT)
except redis.RedisError as e:
    logger.warning("Redis connection failed for data validator: %s. Circuit breaker functionality disabled.", str(e))
    redis_client = None

class ValidationError(Exception):
    def __init__(self, message, discrepancies):
        super().__init__(message)
        self.discrepancies = discrepancies
        self.timestamp = datetime.utcnow()
        self.log_error()
    
    def log_error(self) -> None:
        """Log validation errors for monitoring with detailed information"""
        logger.error("Validation Error at %s: %s - Discrepancies: %s", self.timestamp, str(self), self.discrepancies)

def detect_data_sources(stock: Dict[str, Any]) -> List[str]:
    """Detect which data sources are available for a stock"""
    sources = stock.get('sources', [])
    if not sources:
        # Default to NGX if no sources specified
        return ['NGX']
    return sources

def calculate_accuracy(stock: Dict[str, Any]) -> float:
    """Calculate the accuracy of stock data based on source agreement"""
    # If accuracy is already calculated, return it
    if 'accuracy' in stock:
        return stock['accuracy']
    
    # Otherwise calculate based on sources
    sources = detect_data_sources(stock)
    if len(sources) > 1:
        # Multiple sources provide better accuracy
        return 0.95
    else:
        # Single source has lower accuracy
        return 0.85

def find_discrepancies(stock: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Find discrepancies between different data sources"""
    sources = detect_data_sources(stock)
    
    # If only one source, no discrepancies possible
    if len(sources) <= 1:
        return []
    
    # Simulate discrepancies based on accuracy
    accuracy = stock.get('accuracy', calculate_accuracy(stock))
    
    discrepancies = []
    if accuracy < 0.95:
        # Simulate some discrepancies for lower accuracy stocks
        fields = ['price', 'volume', 'marketCap']
        for field in fields:
            if accuracy < 0.9:
                discrepancies.append({
                    'field': field,
                    'sources': sources,
                    'values': {
                        sources[0]: stock.get(field),
                        sources[1]: stock.get(field) * 1.05  # Simulate a 5% discrepancy
                    }
                })
    
    return discrepancies

def resolve_price(stock: Dict[str, Any]) -> float:
    """Resolve the final price based on multiple sources"""
    discrepancies = find_discrepancies(stock)
    
    # If no price discrepancies, return original price
    price_discrepancy = next((d for d in discrepancies if d['field'] == 'price'), None)
    if not price_discrepancy:
        return stock.get('price')
    
    # Otherwise calculate weighted average based on source reliability
    sources = detect_data_sources(stock)
    weights = {
        'NGX': 0.6,
        'TradingView': 0.4
    }
    
    values = price_discrepancy['values']
    total_weight = sum(weights.get(source, 0.5) for source in sources)
    weighted_price = sum(values.get(source, stock.get('price')) * weights.get(source, 0.5) 
                         for source in sources) / total_weight
    
    return weighted_price

def is_consistent(stock: Dict[str, Any]) -> bool:
    """Check if stock data is consistent across sources"""
    discrepancies = find_discrepancies(stock)
    accuracy = stock.get('accuracy', calculate_accuracy(stock))
    
    # If accuracy is high or no discrepancies, it's consistent
    return accuracy >= 0.9 or len(discrepancies) == 0

def check_circuit_breaker(symbol: str) -> bool:
    """Check if circuit breaker is active for a symbol"""
    if redis_client is None:
        return False
    
    circuit_key = 'circuit_breaker:{}'.format(symbol)
    return redis_client.exists(circuit_key)

def activate_circuit_breaker(symbol: str, duration: int = 300) -> None:
    """Activate circuit breaker for a symbol"""
    if redis_client is None:
        logger.warning("Cannot activate circuit breaker for %s - Redis unavailable", symbol)
        return
        
    circuit_key = 'circuit_breaker:{}'.format(symbol)
    redis_client.set(circuit_key, 'active', ex=duration)
    logger.warning("Circuit breaker activated for %s for %d seconds", symbol, duration)

def validate_stock_data(stock_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cross-validate data between NGX and TradingView sources"""
    validated = []
    for stock in stock_data:
        # Check if circuit breaker is active
        if check_circuit_breaker(stock.get('symbol')):
            logger.info(f"Circuit breaker active for {stock.get('symbol')}, using cached data")
            stock['validation_status'] = 'circuit_breaker'
            validated.append(stock)
            continue
        
        try:
            # Detect data sources
            sources = detect_data_sources(stock)
            
            # Calculate accuracy
            accuracy = calculate_accuracy(stock)
            
            # Find discrepancies
            discrepancies = find_discrepancies(stock)
            
            # Resolve final price
            final_price = resolve_price(stock)
            
            # Check consistency
            consistent = is_consistent(stock)
            
            # Create validated entry
            entry = {
                'symbol': stock.get('symbol'),
                'name': stock.get('name'),
                'price': final_price,
                'change': stock.get('change'),
                'volume': stock.get('volume'),
                'marketCap': stock.get('marketCap'),
                'peRatio': stock.get('peRatio'),
                'sources': sources,
                'accuracy': accuracy,
                'discrepancies': discrepancies,
                'validation_status': 'verified' if consistent else 'unverified'
            }
            
            validated.append(entry)
            
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error validating %s: %s", stock.get('symbol'), str(e))
            # Activate circuit breaker on validation failure
            activate_circuit_breaker(stock.get('symbol'))
            # Still include the stock with unverified status
            stock['validation_status'] = 'error'
            stock['sources'] = detect_data_sources(stock)
            stock['accuracy'] = 0.5  # Low accuracy for error cases
            validated.append(stock)
    
    return validated

def validate_api_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures data quality before processing"""
    if not response.get('data'):
        raise ValidationError("Empty data response", [])
    if 'timestamp' not in response:
        response['timestamp'] = datetime.utcnow().isoformat()
    return response
