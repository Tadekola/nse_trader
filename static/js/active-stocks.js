/**
 * Active Stocks Module for NSE Trader
 * Displays most actively traded stocks with investment recommendations
 */

// Function to fetch the most actively traded stocks with recommendations
async function fetchActiveStocks(limit = 10) {
    try {
        const response = await fetch(`/api/active-stocks?limit=${limit}`);
        if (!response.ok) {
            throw new Error('Failed to fetch active stocks data');
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching active stocks:', error);
        // Return empty data structure in case of error
        return {
            status: 'error',
            data: [],
            timestamp: new Date().toISOString(),
            metrics: {
                average_volume: 0,
                average_confidence: 0
            }
        };
    }
}

// Function to render the active stocks table
async function renderActiveStocksTable(limit = 10) {
    const container = document.getElementById('active-stocks-container');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">Loading actively traded stocks...</div>';
    
    try {
        const data = await fetchActiveStocks(limit);
        
        if (data.status === 'error' || !data.data || data.data.length === 0) {
            container.innerHTML = `<div class="error">Error: Unable to load actively traded stocks</div>`;
            return;
        }
        
        // Create metrics summary
        const metricsSummary = document.createElement('div');
        metricsSummary.className = 'metrics-summary';
        metricsSummary.innerHTML = `
            <div class="metric">
                <span class="metric-title">Average Volume</span>
                <span class="metric-value">${data.metrics.average_volume.toLocaleString()}</span>
            </div>
            <div class="metric">
                <span class="metric-title">Average Confidence</span>
                <span class="metric-value">${data.metrics.average_confidence}%</span>
            </div>
            <div class="metric">
                <span class="metric-title">Last Updated</span>
                <span class="metric-value">${new Date(data.timestamp).toLocaleString()}</span>
            </div>
        `;
        
        // Create table
        const table = document.createElement('table');
        table.className = 'active-stocks-table';
        
        // Create table header
        const thead = document.createElement('thead');
        thead.innerHTML = `
            <tr>
                <th>Symbol</th>
                <th>Name</th>
                <th>Price (₦)</th>
                <th>Change</th>
                <th>Volume</th>
                <th>Recommendation</th>
                <th>Confidence</th>
                <th>Market Sentiment</th>
            </tr>
        `;
        table.appendChild(thead);
        
        // Create table body
        const tbody = document.createElement('tbody');
        data.data.forEach((stock, index) => {
            const row = document.createElement('tr');
            row.className = stock.change >= 0 ? 'positive' : 'negative';
            row.setAttribute('data-stock-index', index);
            
            // Get recommendation class
            let recommendationClass = '';
            if (stock.recommendation === 'STRONG BUY' || stock.recommendation === 'BUY') {
                recommendationClass = 'recommendation-buy';
            } else if (stock.recommendation === 'STRONG SELL' || stock.recommendation === 'SELL') {
                recommendationClass = 'recommendation-sell';
            } else {
                recommendationClass = 'recommendation-hold';
            }
            
            // Create confidence level visual indicator
            const confidenceBar = `
                <div class="confidence-bar-container">
                    <div class="confidence-bar" style="width: ${stock.recommendation_confidence}%"></div>
                </div>
            `;
            
            row.innerHTML = `
                <td>${stock.symbol}</td>
                <td>${stock.name}</td>
                <td>${stock.price.toFixed(2)}</td>
                <td>${stock.change >= 0 ? '+' : ''}${stock.change.toFixed(2)}%</td>
                <td>${stock.volume.toLocaleString()}</td>
                <td class="${recommendationClass}">${stock.recommendation}</td>
                <td>${confidenceBar} ${stock.recommendation_confidence}%</td>
                <td>${stock.market_sentiment}</td>
            `;
            
            tbody.appendChild(row);
        });
        table.appendChild(tbody);
        
        // Clear container and add content
        container.innerHTML = '';
        container.appendChild(metricsSummary);
        container.appendChild(table);
        
        // Add event listeners for expanded details
        document.querySelectorAll('.active-stocks-table tbody tr').forEach(row => {
            row.addEventListener('click', () => {
                const index = parseInt(row.getAttribute('data-stock-index'));
                const stock = data.data[index];
                
                // Check if details row already exists
                const nextRow = row.nextElementSibling;
                if (nextRow && nextRow.classList.contains('details-row')) {
                    nextRow.remove();
                    row.classList.remove('expanded');
                    return;
                }
                
                // Remove any existing details rows
                document.querySelectorAll('.details-row').forEach(dr => dr.remove());
                document.querySelectorAll('.expanded').forEach(er => er.classList.remove('expanded'));
                
                // Create details row
                const detailsRow = document.createElement('tr');
                detailsRow.className = 'details-row';
                
                // Create recommendation reasons list
                const reasonsList = stock.recommendation_reasons.map(reason => 
                    `<li>${reason}</li>`
                ).join('');
                
                detailsRow.innerHTML = `
                    <td colspan="8">
                        <div class="stock-details">
                            <div class="details-section">
                                <h3>Recommendation Details</h3>
                                <p><strong>Recommendation:</strong> ${stock.recommendation}</p>
                                <p><strong>Confidence:</strong> ${stock.recommendation_confidence}%</p>
                                <h4>Reasons:</h4>
                                <ul>${reasonsList}</ul>
                            </div>
                            <div class="details-section">
                                <h3>Stock Information</h3>
                                <p><strong>Market Cap:</strong> ${stock.marketCap}</p>
                                <p><strong>P/E Ratio:</strong> ${stock.peRatio.toFixed(2)}</p>
                                <p><strong>Data Sources:</strong> ${stock.sources.join(', ')}</p>
                                <p><strong>Data Accuracy:</strong> ${Math.round(stock.accuracy * 100)}%</p>
                            </div>
                        </div>
                    </td>
                `;
                
                // Insert details row after current row
                row.parentNode.insertBefore(detailsRow, row.nextSibling);
                row.classList.add('expanded');
            });
        });
        
    } catch (error) {
        container.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

// Function to initialize active stocks view
function initActiveStocksView() {
    const stocksLimit = 10; // Default limit
    
    // Render the initial view
    renderActiveStocksTable(stocksLimit);
    
    // Set up refresh button if it exists
    const refreshButton = document.getElementById('refresh-active-stocks');
    if (refreshButton) {
        refreshButton.addEventListener('click', () => {
            renderActiveStocksTable(stocksLimit);
        });
    }
    
    // Set up auto-refresh (every 60 seconds)
    setInterval(() => renderActiveStocksTable(stocksLimit), 60000);
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    initActiveStocksView();
});
