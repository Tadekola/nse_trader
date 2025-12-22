// TradingView Chart Widget for NSE Trader
document.addEventListener('DOMContentLoaded', function() {
    // Function to create and load TradingView chart widget
    window.createTradingViewWidget = function(symbol = 'DANGCEM') {
        const container = document.getElementById('tradingview-chart');
        if (!container) return;
        
        // Clear previous widget if any
        container.innerHTML = '';
        
        // Show loading indicator
        const loading = document.createElement('div');
        loading.className = 'text-center my-5';
        loading.innerHTML = '<div class="spinner-border text-primary" role="status"></div><p class="mt-2">Loading chart...</p>';
        container.appendChild(loading);
        
        // Create new widget with the selected symbol
        try {
            new TradingView.widget({
                "width": "100%",
                "height": 500,
                "symbol": `NSENG:${symbol}`,
                "interval": "D",
                "timezone": "Africa/Lagos",
                "theme": "light",
                "style": "1",
                "locale": "en",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "hide_top_toolbar": false,
                "save_image": true,
                "container_id": "tradingview-chart"
            });
        } catch (error) {
            console.error('Error loading TradingView widget:', error);
            container.innerHTML = `<div class="alert alert-danger">Failed to load chart. Please try again.</div>`;
        }
    };
    
    // Initialize with default symbol
    if (document.getElementById('tradingview-chart')) {
        createTradingViewWidget();
    }
});
