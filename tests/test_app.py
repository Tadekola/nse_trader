"""Unit tests for the Flask application."""
import pytest
import json
from nse_trader.app import create_app

@pytest.fixture
def client():
    """Create and configure a new app instance for each test."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_market_summary_api(client):
    """Test the /api/market-summary endpoint."""
    response = client.get('/api/market-summary')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    
    # Check for expected keys in the response
    # Based on nse_trader/app.py, these are the keys returned,
    # including fallback default values.
    expected_keys = [
        'asi', 'change', 'change_percent', 'market_cap', 
        'volume', 'value', 'last_update'
    ]
    for key in expected_keys:
        assert key in data

    # Optional: Check types or specific values if consistent defaults are important
    assert isinstance(data['asi'], str) # Formatted number
    if data.get('change_raw') is not None: # if 'change_raw' exists, check it
      assert isinstance(data['change_raw'], (float, int))
    elif 'change' in data : # else, check 'change' if it's not None
      assert isinstance(data['change'], (float, int))


    assert isinstance(data['market_cap'], str) # Formatted currency

    # Check that last_update is a valid ISO format string (or similar)
    # For simplicity, just checking it's a string here.
    # from datetime import datetime
    # datetime.fromisoformat(data['last_update']) # This would validate more strictly
    assert isinstance(data['last_update'], str)
