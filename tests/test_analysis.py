"""Unit tests for technical analysis module."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from nse_trader.technical_analysis import TechnicalAnalyzer

@pytest.fixture
def sample_data():
    """Create sample price data for testing."""
    dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='D')
    n = len(dates)
    
    # Generate synthetic price data
    np.random.seed(42)
    prices = np.random.randn(n).cumsum() + 100  # Random walk starting at 100
    
    df = pd.DataFrame({
        'Open': prices + np.random.randn(n) * 0.1,
        'High': prices + np.random.randn(n) * 0.2,
        'Low': prices - np.random.randn(n) * 0.2,
        'Close': prices,
        'Volume': np.random.randint(1000, 100000, n)
    }, index=dates)
    
    return df

def test_analyze_stock(sample_data):
    """Test technical analysis calculations."""
    analyzer = TechnicalAnalyzer()
    analysis = analyzer.analyze_stock(sample_data)
    
    # Check if all expected indicators are present
    assert 'sma_50' in analysis
    assert 'sma_200' in analysis
    assert 'ema_50' in analysis
    assert 'ema_200' in analysis
    assert 'rsi' in analysis
    assert 'bb_upper' in analysis
    assert 'bb_middle' in analysis
    assert 'bb_lower' in analysis
    
    # Check if values are within expected ranges
    assert 0 <= analysis['rsi'] <= 100
    assert analysis['bb_lower'] <= analysis['bb_middle'] <= analysis['bb_upper']

def test_generate_signals(sample_data):
    """Test trading signal generation."""
    analyzer = TechnicalAnalyzer()
    analysis = analyzer.analyze_stock(sample_data)
    signals = analyzer.generate_signals(analysis)
    
    # Check signal structure
    assert 'recommendation' in signals
    assert 'strength' in signals
    assert 'reasons' in signals
    
    # Check signal values
    assert signals['recommendation'] in ['STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL']
    assert -3 <= signals['strength'] <= 3
    assert isinstance(signals['reasons'], list)

def test_empty_data():
    """Test handling of empty data."""
    analyzer = TechnicalAnalyzer()
    empty_df = pd.DataFrame()
    
    analysis = analyzer.analyze_stock(empty_df)
    signals = analyzer.generate_signals(analysis)
    
    assert analysis == {}
    assert signals['recommendation'] == 'HOLD'
    assert signals['strength'] == 0
    assert len(signals['reasons']) == 1
    assert signals['reasons'][0] == 'Error generating signals'

def test_missing_data(sample_data):
    """Test handling of missing data."""
    analyzer = TechnicalAnalyzer()
    
    # Create gaps in the data
    sample_data.loc[sample_data.index[10:20], :] = np.nan
    
    analysis = analyzer.analyze_stock(sample_data)
    signals = analyzer.generate_signals(analysis)
    
    # Should still produce results
    assert analysis != {}
    assert signals['recommendation'] in ['STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL']
