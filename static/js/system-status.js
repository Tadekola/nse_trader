/**
 * System Status Dashboard Module for NSE Trader
 * Provides detailed visualization of validation system status, cache, circuit breakers, and data sources
 */

// Fetch system status data
async function fetchSystemStatus() {
    try {
        const response = await fetch('/api/validation-status');
        if (!response.ok) {
            throw new Error('Failed to fetch system status');
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching system status:', error);
        return {
            system_status: 'error',
            error: error.message
        };
    }
}

// Fetch validation metrics from market data
async function fetchValidationMetrics() {
    try {
        const response = await fetch('/api/validated-market-data');
        if (!response.ok) {
            throw new Error('Failed to fetch validation metrics');
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching validation metrics:', error);
        return {
            status: 'error',
            error: error.message
        };
    }
}

// Update validation system status panel
function updateValidationSystemStatus(data) {
    const container = document.getElementById('validation-system-status');
    if (!container) return;
    
    const statusClass = data.system_status === 'active' ? 'status-healthy' : 'status-degraded';
    const statusIcon = data.system_status === 'active' ? 'check-circle' : 'exclamation-triangle';
    
    container.innerHTML = `
        <div class="status-item ${statusClass}">
            <i class="fas fa-${statusIcon}"></i>
            <div class="status-details">
                <span class="status-name">System Status</span>
                <span class="status-value">${data.system_status === 'active' ? 'Online' : 'Offline'}</span>
            </div>
        </div>
        <div class="status-item">
            <i class="fas fa-clock"></i>
            <div class="status-details">
                <span class="status-name">Last Validation</span>
                <span class="status-value">${new Date(data.last_validation).toLocaleString()}</span>
            </div>
        </div>
    `;
}

// Update cache status panel
function updateCacheStatus(data) {
    const container = document.getElementById('cache-status');
    if (!container) return;
    
    const statusClass = data.redis_available ? 'status-healthy' : 'status-degraded';
    const statusIcon = data.redis_available ? 'check-circle' : 'exclamation-triangle';
    
    container.innerHTML = `
        <div class="status-item ${statusClass}">
            <i class="fas fa-${statusIcon}"></i>
            <div class="status-details">
                <span class="status-name">Redis Cache</span>
                <span class="status-value">${data.redis_available ? 'Available' : 'Unavailable'}</span>
            </div>
        </div>
        <div class="status-message">
            ${data.redis_available 
                ? 'Data caching is active for improved performance.' 
                : 'Fallback data is being used. Performance may be degraded.'
            }
        </div>
    `;
}

// Update circuit breaker status panel
function updateCircuitBreakerStatus(data) {
    const container = document.getElementById('circuit-breaker-status');
    if (!container) return;
    
    const statusClass = !data.circuit_breakers_active ? 'status-healthy' : 'status-degraded';
    const statusIcon = !data.circuit_breakers_active ? 'check-circle' : 'bolt';
    
    let breakers = '';
    if (data.circuit_breakers_active && data.active_circuit_breakers.length > 0) {
        breakers = `
            <div class="circuit-breakers-list">
                <span class="list-header">Active Circuit Breakers:</span>
                <ul>
                    ${data.active_circuit_breakers.map(symbol => `<li>${symbol}</li>`).join('')}
                </ul>
            </div>
        `;
    }
    
    container.innerHTML = `
        <div class="status-item ${statusClass}">
            <i class="fas fa-${statusIcon}"></i>
            <div class="status-details">
                <span class="status-name">Circuit Breakers</span>
                <span class="status-value">${data.circuit_breakers_active ? 'Active' : 'Inactive'}</span>
            </div>
        </div>
        ${breakers}
        <div class="status-message">
            ${data.circuit_breakers_active
                ? 'Some stock data is protected by circuit breakers due to validation issues.'
                : 'All stocks are operating normally without circuit breakers.'
            }
        </div>
    `;
}

// Update data sources status panel
function updateDataSourcesStatus(data) {
    const container = document.getElementById('data-sources-status');
    if (!container) return;
    
    const ngxStatus = data.source_statuses.NGX === 'healthy' ? 'status-healthy' : 'status-degraded';
    const tvStatus = data.source_statuses.TradingView === 'healthy' ? 'status-healthy' : 'status-degraded';
    
    container.innerHTML = `
        <div class="status-item ${ngxStatus}">
            <div class="source-icon ngx"></div>
            <div class="status-details">
                <span class="status-name">Nigerian Exchange Group (NGX)</span>
                <span class="status-value">${data.source_statuses.NGX}</span>
            </div>
        </div>
        <div class="status-item ${tvStatus}">
            <div class="source-icon tradingview"></div>
            <div class="status-details">
                <span class="status-name">TradingView</span>
                <span class="status-value">${data.source_statuses.TradingView}</span>
            </div>
        </div>
        <div class="status-message">
            ${data.source_statuses.NGX === 'healthy' && data.source_statuses.TradingView === 'healthy'
                ? 'All data sources are operating normally.'
                : 'Some data sources are experiencing issues. Data quality may be affected.'
            }
        </div>
    `;
}

// Update validation metrics section
function updateValidationMetrics(data) {
    const container = document.getElementById('validation-metrics');
    if (!container) return;
    
    if (data.status === 'error') {
        container.innerHTML = `<div class="error">Error loading validation metrics: ${data.error}</div>`;
        return;
    }
    
    // Calculate metrics
    const totalStocks = data.data.length;
    const verifiedStocks = data.data.filter(stock => stock.validation_status === 'verified').length;
    const unverifiedStocks = data.data.filter(stock => stock.validation_status === 'unverified').length;
    const errorStocks = data.data.filter(stock => stock.validation_status === 'error').length;
    const multiSourceStocks = data.data.filter(stock => stock.sources && stock.sources.length > 1).length;
    
    // Calculate average accuracy
    const totalAccuracy = data.data.reduce((sum, stock) => sum + stock.accuracy, 0);
    const avgAccuracy = totalAccuracy / totalStocks;
    
    const metricsHTML = `
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value">${Math.round(data.validation_accuracy * 100)}%</div>
                <div class="metric-name">Overall Validation Accuracy</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">${verifiedStocks} / ${totalStocks}</div>
                <div class="metric-name">Verified Stocks</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">${multiSourceStocks} / ${totalStocks}</div>
                <div class="metric-name">Multi-Source Validated</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">${unverifiedStocks}</div>
                <div class="metric-name">Unverified Stocks</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">${errorStocks}</div>
                <div class="metric-name">Error Status Stocks</div>
            </div>
        </div>
        <div class="last-update">
            Last updated: ${new Date().toLocaleString()}
        </div>
    `;
    
    container.innerHTML = metricsHTML;
}

// Update the stock selector in the Charts tab
function updateChartStockSelector() {
    const selector = document.getElementById('chart-stock-select');
    if (!selector) return;
    
    // Fetch stock data
    fetch('/api/validated-market-data')
        .then(response => response.json())
        .then(data => {
            // Add options for each stock
            data.data.forEach(stock => {
                const option = document.createElement('option');
                option.value = stock.symbol;
                option.textContent = `${stock.symbol} - ${stock.name}`;
                selector.appendChild(option);
            });
            
            // Add change event listener
            selector.addEventListener('change', function() {
                const selectedStock = this.value;
                const chartContainer = document.getElementById('stock-chart-container');
                
                if (selectedStock) {
                    // Clear container
                    chartContainer.innerHTML = '';
                    
                    // Create chart
                    createPriceChart(selectedStock, chartContainer);
                } else {
                    chartContainer.innerHTML = '<div class="default-message">Select a stock to view its chart</div>';
                }
            });
        })
        .catch(error => {
            console.error('Error fetching stocks for chart selector:', error);
            selector.innerHTML = '<option value="">Error loading stocks</option>';
        });
}

// Update all system status panels
async function updateSystemStatusDashboard() {
    try {
        // Fetch status data
        const statusData = await fetchSystemStatus();
        
        // Update individual panels
        updateValidationSystemStatus(statusData);
        updateCacheStatus(statusData);
        updateCircuitBreakerStatus(statusData);
        updateDataSourcesStatus(statusData);
        
        // Fetch and update validation metrics
        const metricsData = await fetchValidationMetrics();
        updateValidationMetrics(metricsData);
        
    } catch (error) {
        console.error('Error updating system status dashboard:', error);
        
        // Show error message in each panel
        const errorMessage = `<div class="error">Error loading status information: ${error.message}</div>`;
        
        document.getElementById('validation-system-status').innerHTML = errorMessage;
        document.getElementById('cache-status').innerHTML = errorMessage;
        document.getElementById('circuit-breaker-status').innerHTML = errorMessage;
        document.getElementById('data-sources-status').innerHTML = errorMessage;
        document.getElementById('validation-metrics').innerHTML = errorMessage;
    }
}

// Add CSS styles for status dashboard
function addStatusDashboardStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .status-dashboard {
            margin-top: 10px;
        }
        
        .dashboard-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .dashboard-header h3 {
            margin: 0;
            color: var(--primary-color);
        }
        
        .status-panels {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 20px;
        }
        
        .status-panel {
            background-color: white;
            border-radius: 8px;
            box-shadow: var(--shadow);
            overflow: hidden;
        }
        
        .panel-header {
            background-color: var(--primary-color);
            color: white;
            padding: 12px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }
        
        .panel-header h4 {
            margin: 0;
            font-size: 16px;
        }
        
        .panel-body {
            padding: 15px;
        }
        
        .status-item {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 12px;
            border-bottom: 1px solid #f0f0f0;
        }
        
        .status-item:last-child {
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }
        
        .status-item i {
            font-size: 18px;
            margin-right: 12px;
        }
        
        .status-item.status-healthy i {
            color: var(--success-color);
        }
        
        .status-item.status-degraded i {
            color: var(--warning-color);
        }
        
        .status-details {
            display: flex;
            flex-direction: column;
        }
        
        .status-name {
            font-size: 14px;
            color: #7f8c8d;
        }
        
        .status-value {
            font-size: 16px;
            font-weight: bold;
        }
        
        .status-message {
            margin-top: 10px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
            font-size: 13px;
        }
        
        .circuit-breakers-list {
            margin: 10px 0;
            padding: 10px;
            background-color: rgba(243, 156, 18, 0.1);
            border-radius: 4px;
        }
        
        .list-header {
            font-weight: bold;
            font-size: 13px;
            display: block;
            margin-bottom: 5px;
        }
        
        .circuit-breakers-list ul {
            margin: 5px 0;
            padding-left: 25px;
        }
        
        .circuit-breakers-list li {
            font-size: 13px;
        }
        
        .system-metrics {
            margin-top: 30px;
        }
        
        .system-metrics h3 {
            color: var(--primary-color);
            font-size: 18px;
            margin-bottom: 15px;
        }
        
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .metric-card {
            background-color: white;
            border-radius: 8px;
            box-shadow: var(--shadow);
            padding: 15px;
            text-align: center;
        }
        
        .metric-value {
            font-size: 24px;
            font-weight: bold;
            color: var(--primary-color);
            margin-bottom: 5px;
        }
        
        .metric-name {
            font-size: 14px;
            color: #7f8c8d;
        }
        
        .last-update {
            text-align: right;
            font-size: 12px;
            color: #95a5a6;
            margin-top: 15px;
        }
        
        .chart-selector {
            margin-bottom: 20px;
            display: flex;
            align-items: center;
        }
        
        .chart-stock-select {
            padding: 8px 12px;
            border-radius: 4px;
            border: 1px solid #ddd;
            margin-left: 10px;
            min-width: 250px;
        }
        
        .default-message {
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
            font-size: 16px;
        }
        
        @media (max-width: 768px) {
            .status-panels {
                grid-template-columns: 1fr;
            }
            
            .metrics-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
    `;
    
    document.head.appendChild(style);
}

// Initialize system status dashboard
function initSystemStatusDashboard() {
    // Add CSS styles for status dashboard
    addStatusDashboardStyles();
    
    // Update dashboard
    updateSystemStatusDashboard();
    
    // Add event listener for refresh button
    const refreshButton = document.getElementById('refresh-status');
    if (refreshButton) {
        refreshButton.addEventListener('click', updateSystemStatusDashboard);
    }
    
    // Set up auto-refresh (every 60 seconds)
    setInterval(updateSystemStatusDashboard, 60000);
}

// Initialize chart selector
function initChartSelector() {
    updateChartStockSelector();
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Initialize components when their tabs are activated
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.getAttribute('data-tab');
            
            if (tabId === 'system-status') {
                // Initialize system status dashboard when tab is activated
                initSystemStatusDashboard();
            } else if (tabId === 'charts') {
                // Initialize chart selector when tab is activated
                initChartSelector();
            }
        });
    });
});
