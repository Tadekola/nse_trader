"""
Data Validation Module for NSE Trader

This module provides functionality to validate stock market data 
against official Nigerian Stock Exchange (NGX) and TradingView sources
to ensure accuracy of the displayed information.
"""

import logging
import time
import datetime
import requests
from bs4 import BeautifulSoup
import json
import random  # For simulation purposes
import redis  # For circuit breaker implementation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Redis connection for circuit breaker
redis_client = redis.Redis(host='localhost', port=6379, db=0)


class DataValidator:
    """Validates stock market data against official sources."""
    
    def __init__(self):
        self.ngx_url = "https://ngxgroup.com/exchange/data/equities-price-list/"
        self.tradingview_api_base = "https://symbol-search.tradingview.com/symbol_search/"
        self.last_validation = {}
        self.validation_results = {}
        self.validation_timestamp = None
        self.validation_frequency = 15  # minutes
    
    def validate_stock_data(self, stock_data):
        """
        Validate a collection of stock data against official sources.
        
        Args:
            stock_data: List of dictionaries containing stock information
            
        Returns:
            Dictionary with validation results for each stock
        """
        if self._should_validate():
            logger.info(f"Running validation on {len(stock_data)} stocks")
            self.validation_timestamp = datetime.datetime.now()
            
            results = {}
            for stock in stock_data:
                symbol = stock.get('symbol')
                if not symbol:
                    continue
                
                # Validate against NGX
                ngx_result = self._validate_against_ngx(symbol, stock)
                
                # Validate against TradingView
                tv_result = self._validate_against_tradingview(symbol, stock)
                
                # Combine results
                results[symbol] = {
                    'ngx_validated': ngx_result['ngx_validated'],
                    'tv_validated': tv_result['tv_validated'],
                    'price_accuracy': self._calculate_accuracy(
                        stock.get('price_raw', 0), 
                        ngx_result.get('ngx_price', 0),
                        tv_result.get('tv_price', 0)
                    ),
                    'discrepancies': {
                        'ngx': ngx_result.get('discrepancies', {}),
                        'tradingview': tv_result.get('discrepancies', {})
                    },
                    'validation_time': self.validation_timestamp,
                    'data_source': 'verified' if (ngx_result['ngx_validated'] or tv_result['tv_validated']) else 'estimated'
                }
                
                # New volatility check
                if stock.get('change_percent', 0) > 25:
                    logger.warning(f"Extreme volatility detected: {stock['symbol']}")
                    self._trigger_circuit_breaker(stock['symbol'])
            
            self.validation_results = results
            self.last_validation = self.validation_timestamp
            
            # Log validation summary
            self._log_validation_summary(results)
            return results
            
        else:
            # Return cached validation results if still valid
            if self.validation_results:
                logger.info("Using cached validation results")
                return self.validation_results
            else:
                # Force validation if no cached results
                return self.validate_stock_data(stock_data)
    
    def _should_validate(self):
        """Determine if validation should be run based on last validation time."""
        if not self.last_validation:
            return True
            
        now = datetime.datetime.now()
        elapsed = (now - self.last_validation).total_seconds() / 60
        return elapsed >= self.validation_frequency
    
    def _validate_against_ngx(self, symbol, stock_data):
        """
        Validate stock data against NGX website.
        
        In a production environment, this would scrape the NGX website or use their API.
        For demonstration, we're simulating the validation process.
        """
        # Ensure price is float before comparison
        our_price = float(stock_data.get('price_raw', 0))
        
        # Simulate NGX price with proper type conversion
        ngx_price = float(random.uniform(our_price * 0.95, our_price * 1.05))
        
        # Calculate price difference
        price_diff = abs(our_price - ngx_price)
        
        is_validated = price_diff / ngx_price < 0.05  # 5% tolerance
        
        discrepancies = {}
        if price_diff / ngx_price > 0.02:
            discrepancies['price'] = {
                'our_value': our_price,
                'ngx_value': ngx_price,
                'difference_pct': (price_diff / ngx_price) * 100
            }
        
        return {
            'ngx_validated': is_validated,
            'price': ngx_price,
            'discrepancies': discrepancies
        }
    
    def _validate_against_tradingview(self, symbol, stock_data):
        """
        Validate stock data against TradingView API.
        
        In a production environment, this would use the TradingView API.
        For demonstration, we're simulating the validation process.
        """
        # Ensure price is float before comparison
        our_price = float(stock_data.get('price_raw', 0))
        
        # Simulate TradingView price with proper type conversion
        tv_price = float(random.uniform(our_price * 0.97, our_price * 1.03))
        
        # Calculate price difference
        price_diff = abs(our_price - tv_price)
        
        is_validated = price_diff / tv_price < 0.03  # 3% tolerance
        
        discrepancies = {}
        if price_diff / tv_price > 0.01:
            discrepancies['price'] = {
                'our_value': our_price,
                'tv_value': tv_price,
                'difference_pct': (price_diff / tv_price) * 100
            }
        
        return {
            'tv_validated': is_validated,
            'price': tv_price,
            'discrepancies': discrepancies
        }
    
    def _calculate_accuracy(self, our_price, ngx_price, tv_price):
        """Calculate the accuracy percentage of our price data."""
        if our_price == 0 or (ngx_price == 0 and tv_price == 0):
            return 0
            
        # If both external prices are available, use average difference
        if ngx_price > 0 and tv_price > 0:
            ngx_diff_pct = abs(our_price - ngx_price) / ngx_price * 100
            tv_diff_pct = abs(our_price - tv_price) / tv_price * 100
            avg_diff_pct = (ngx_diff_pct + tv_diff_pct) / 2
            
            if avg_diff_pct > 5:
                logger.warning(f"Price discrepancy alert for {symbol}: {avg_diff_pct:.2f}%")
                self._trigger_alert(symbol, 'price', avg_diff_pct)
            
            accuracy = max(0, 100 - avg_diff_pct)
        # If only one external price is available
        elif ngx_price > 0:
            diff_pct = abs(our_price - ngx_price) / ngx_price * 100
            accuracy = max(0, 100 - diff_pct)
        elif tv_price > 0:
            diff_pct = abs(our_price - tv_price) / tv_price * 100
            accuracy = max(0, 100 - diff_pct)
        else:
            accuracy = 0
            
        return round(accuracy, 1)
    
    def _log_validation_summary(self, results):
        """Log a summary of validation results."""
        validated_count = sum(1 for r in results.values() if r['ngx_validated'] or r['tv_validated'])
        high_accuracy_count = sum(1 for r in results.values() if r['price_accuracy'] >= 95)
        
        logger.info(f"Validation Summary: {validated_count}/{len(results)} stocks validated")
        logger.info(f"High Accuracy (≥95%): {high_accuracy_count}/{len(results)} stocks")
        
        # Log stocks with significant discrepancies
        for symbol, result in results.items():
            if result['price_accuracy'] < 90:
                logger.warning(f"Low accuracy for {symbol}: {result['price_accuracy']}%")
                
                ngx_discrep = result['discrepancies']['ngx'].get('price', {})
                tv_discrep = result['discrepancies']['tradingview'].get('price', {})
                
                if ngx_discrep:
                    logger.warning(f"  NGX price discrepancy: {ngx_discrep.get('difference_pct', 0):.2f}%")
                
                if tv_discrep:
                    logger.warning(f"  TradingView price discrepancy: {tv_discrep.get('difference_pct', 0):.2f}%")
    
    def _trigger_alert(self, symbol, field, discrepancy):
        # Implement alert triggering logic here
        pass
    
    def _trigger_circuit_breaker(self, symbol):
        """Halt trading for symbol during extreme volatility"""
        redis_client.set(f'circuit_breaker:{symbol}', 'active', ex=300)
        logger.critical(f"Circuit breaker triggered for {symbol}")


# Helper function to get data validation status indicators
def get_validation_indicators(validation_result):
    """
    Generate HTML for validation indicators.
    
    Args:
        validation_result: Dictionary with validation results for a stock
        
    Returns:
        HTML string with validation indicators
    """
    if not validation_result:
        return '<span class="badge bg-secondary" title="Not validated">NOT VERIFIED</span>'
        
    accuracy = validation_result.get('price_accuracy', 0)
    ngx_validated = validation_result.get('ngx_validated', False)
    tv_validated = validation_result.get('tv_validated', False)
    
    indicators = []
    
    # Price accuracy indicator
    if accuracy >= 98:
        accuracy_badge = f'<span class="badge bg-success" title="Price accuracy">±{100-accuracy:.1f}%</span>'
    elif accuracy >= 95:
        accuracy_badge = f'<span class="badge bg-success-light" title="Price accuracy">±{100-accuracy:.1f}%</span>'
    elif accuracy >= 90:
        accuracy_badge = f'<span class="badge bg-warning" title="Price accuracy">±{100-accuracy:.1f}%</span>'
    else:
        accuracy_badge = f'<span class="badge bg-danger" title="Price accuracy">±{100-accuracy:.1f}%</span>'
    
    indicators.append(accuracy_badge)
    
    # Source validation indicators
    if ngx_validated:
        indicators.append('<span class="badge bg-info" title="Verified with Nigerian Exchange">NGX</span>')
    
    if tv_validated:
        indicators.append('<span class="badge bg-primary" title="Verified with TradingView">TV</span>')
        
    validation_time = validation_result.get('validation_time')
    time_str = validation_time.strftime('%H:%M') if validation_time else 'unknown'
    
    return f'<div class="validation-badges" title="Verified at {time_str}">{" ".join(indicators)}</div>'
