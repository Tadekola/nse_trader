"""Unit tests for technical analysis module."""
import pytest
import numpy as np
from nse_trader.technical_analysis import TechnicalAnalyzer

@pytest.fixture
def sample_prices():
    """Create sample price data (list of floats) for testing."""
    np.random.seed(42)
    # Generate enough data points for indicators to compute (e.g., MACD needs ~35 for signal line)
    prices = (np.random.randn(100).cumsum() + 100).tolist() 
    return prices

@pytest.fixture
def short_prices():
    """Create short price data (list of floats) for testing default/edge cases."""
    np.random.seed(42)
    prices = (np.random.randn(10).cumsum() + 100).tolist()
    return prices

def test_analyze_stock_structure_and_values(sample_prices):
    """Test technical analysis calculations and structure from analyze_stock."""
    analyzer = TechnicalAnalyzer()
    # The actual analyze_stock method expects a list of closing prices
    analysis = analyzer.analyze_stock(sample_prices) 
    
    assert 'recommendation' in analysis
    assert 'confidence' in analysis
    assert 'indicators' in analysis
    
    indicators = analysis['indicators']
    assert 'rsi' in indicators
    assert 'macd' in indicators
    assert 'bollinger' in indicators
    assert 'momentum' in indicators
    
    # Check if RSI values are within expected ranges
    assert 0 <= indicators['rsi'] <= 100
    
    # Check recommendation and confidence values (example, can be more specific)
    assert analysis['recommendation'] in ['buy', 'sell', 'neutral']
    assert analysis['confidence'] in ['low', 'medium', 'high']
    
    # Check that indicator signals are in expected format
    assert indicators['macd'] in ['buy', 'sell', 'neutral']
    assert indicators['bollinger'] in ['buy', 'sell', 'neutral']
    # Momentum is a float value, not a buy/sell string signal here
    assert isinstance(indicators['momentum'], float)

def test_empty_data_handling(short_prices): # Using short_prices for default case test
    """Test handling of insufficient data."""
    analyzer = TechnicalAnalyzer()
    
    # Test with very short data (less than 30, which is the threshold in analyze_stock)
    analysis = analyzer.analyze_stock(short_prices) 
    
    assert analysis['recommendation'] == 'neutral'
    assert analysis['confidence'] == 'low'
    assert analysis['indicators']['rsi'] == 50
    assert analysis['indicators']['macd'] == 'neutral'
    assert analysis['indicators']['bollinger'] == 'neutral'
    assert analysis['indicators']['momentum'] == 0

    # Test with completely empty list
    analysis_empty = analyzer.analyze_stock([])
    assert analysis_empty['recommendation'] == 'neutral'
    assert analysis_empty['confidence'] == 'low'
    assert analysis_empty['indicators']['rsi'] == 50
    assert analysis_empty['indicators']['macd'] == 'neutral'
    assert analysis_empty['indicators']['bollinger'] == 'neutral'
    assert analysis_empty['indicators']['momentum'] == 0

# Individual indicator tests can be added for more detailed checks
def test_calculate_rsi(sample_prices, short_prices):
    analyzer = TechnicalAnalyzer()
    rsi = analyzer.calculate_rsi(sample_prices)
    assert 0 <= rsi <= 100
    
    rsi_short = analyzer.calculate_rsi(short_prices) # Not enough data for full calculation
    assert rsi_short == 50 # Default for insufficient data

def test_calculate_macd(sample_prices, short_prices):
    analyzer = TechnicalAnalyzer()
    macd_data = analyzer.calculate_macd(sample_prices)
    assert 'macd_line' in macd_data
    assert 'signal_line' in macd_data
    assert 'histogram' in macd_data
    assert macd_data['signal'] in ['buy', 'sell', 'neutral']

    macd_short = analyzer.calculate_macd(short_prices) # Uses default for insufficient data
    assert macd_short['signal'] == 'neutral'
    assert macd_short['macd_line'] == 0

def test_calculate_bollinger_bands(sample_prices, short_prices):
    analyzer = TechnicalAnalyzer()
    bb_data = analyzer.calculate_bollinger_bands(sample_prices)
    assert 'upper_band' in bb_data
    assert 'middle_band' in bb_data
    assert 'lower_band' in bb_data
    assert bb_data['signal'] in ['buy', 'sell', 'neutral']
    if bb_data['middle_band'] != 0: # avoid division by zero if middle band is zero
      assert bb_data['lower_band'] <= bb_data['middle_band'] <= bb_data['upper_band']

    bb_short = analyzer.calculate_bollinger_bands(short_prices) # Uses default for insufficient data
    assert bb_short['signal'] == 'neutral'
    # Check if default values are based on the last price of short_prices
    if short_prices:
        assert bb_short['middle_band'] == short_prices[-1]

def test_calculate_momentum(sample_prices, short_prices):
    analyzer = TechnicalAnalyzer()
    momentum = analyzer.calculate_momentum(sample_prices)
    assert isinstance(momentum, float)

    momentum_short = analyzer.calculate_momentum(short_prices) # period is 14, len(short_prices) is 10
    assert momentum_short == 0 # Default for insufficient data
