// Handle stock display in TradingView style
document.addEventListener('DOMContentLoaded', function() {
    // Refresh market data when the refresh button is clicked
    const refreshButton = document.getElementById('refresh-market');
    if (refreshButton) {
        refreshButton.addEventListener('click', function() {
            // Show a toast message since market-summary endpoint has been removed
            showToast('Market summary refresh is not available in this version.', 'info');
        });
    }
    
    // Add refresh button for stock list
    const refreshStocksBtn = document.createElement('button');
    refreshStocksBtn.className = 'btn btn-sm btn-outline-primary';
    refreshStocksBtn.title = 'Refresh Stocks';
    refreshStocksBtn.innerHTML = '<i class="bi bi-arrow-repeat"></i> Refresh';
    refreshStocksBtn.addEventListener('click', fetchStocks);
    
    // Find the top stocks title and add the refresh button next to it
    const topStocksTitle = document.querySelector('#top-stocks h2');
    if (topStocksTitle) {
        // Create a container to hold both title and button
        const titleContainer = document.createElement('div');
        titleContainer.className = 'd-flex justify-content-between align-items-center mb-3';
        
        // Replace the existing title with the container
        const titleParent = topStocksTitle.parentNode;
        titleParent.insertBefore(titleContainer, topStocksTitle);
        
        // Move title to container and remove mb-4 class
        topStocksTitle.classList.remove('mb-4');
        topStocksTitle.classList.add('mb-0');
        titleContainer.appendChild(topStocksTitle);
        
        // Add refresh button to container
        titleContainer.appendChild(refreshStocksBtn);
    }
    
    // Initialize UI
    fetchStocks();
});

// Helper function to get recommendation class for badges
function getRecommendationClass(recommendation) {
    switch (recommendation?.toUpperCase()) {
        case 'STRONG_BUY':
        case 'BUY': return 'bg-success';
        case 'STRONG_SELL':
        case 'SELL': return 'bg-danger';
        case 'HOLD': return 'bg-warning';
        default: return 'bg-secondary';
    }
}

// Fetch stocks
async function fetchStocks() {
    showLoading('top-stocks');
    try {
        // First try to get validated data from our new API
        let stocks = [];
        try {
            const response = await fetch('/api/validated-market-data');
            if (response.ok) {
                const data = await response.json();
                if (data && Array.isArray(data.data)) {
                    stocks = data.data;
                    console.log(`Using validated stock data. ${data.meta.validated_count}/${data.meta.total_count} stocks validated.`);
                }
            }
        } catch (validationError) {
            console.warn('Could not fetch validated data:', validationError);
        }
        
        // If we couldn't get validated data, fall back to the original API
        if (stocks.length === 0) {
            const response = await fetch('/api/stocks/top');
            if (!response.ok) {
                throw new Error('Failed to fetch top stocks');
            }
            stocks = await response.json();
            console.log('Using fallback stock data without validation.');
        }
        
        // Update the UI with fetched data
        const topStocksContainer = document.getElementById('top-stocks');
        if (!topStocksContainer) {
            console.error('Top stocks container not found');
            return;
        }
        
        // Find the content portion (after the title container)
        let contentContainer = topStocksContainer.querySelector('.table-responsive');
        if (!contentContainer) {
            contentContainer = document.createElement('div');
            topStocksContainer.appendChild(contentContainer);
        }
        
        // Format stock data
        contentContainer.innerHTML = `
            <div class="card shadow-sm mb-4">
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <div class="stock-table-container">
                            <table class="table table-hover">
                                <thead>
                                    <tr>
                                        <th>Symbol</th>
                                        <th>Name</th>
                                        <th>Market Cap</th>
                                        <th>Price</th>
                                        <th>Change</th>
                                        <th>Volume</th>
                                        <th>Rel. Vol</th>
                                        <th>P/E</th>
                                        <th>EPS</th>
                                        <th>Div Yield</th>
                                        <th>Sector</th>
                                        <th>Signal</th>
                                        <th>Validation</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${stocks.map(stock => {
                                        const relVolume = stock.rel_vol || stock.rel_volume || 'N/A';
                                        const pe = stock.pe || stock.pe_ratio || 'N/A';
                                        const eps = stock.eps || 'N/A';
                                        const divYield = stock.div_yield || stock.dividend_yield || 'N/A';
                                        const sector = stock.sector || 'N/A';
                                        const changeValue = stock.change_percent || (stock.change ? parseFloat(stock.change) * 100 / parseFloat(stock.price) : 0);
                                        
                                        return `
                                        <tr class="stock-row" data-symbol="${stock.symbol}">
                                            <td><strong>${stock.symbol}</strong></td>
                                            <td>${stock.name}</td>
                                            <td>${formatMarketCap(stock.market_cap)}</td>
                                            <td>₦${parseFloat(stock.price).toFixed(2)}</td>
                                            <td class="${parseFloat(stock.change) > 0 ? 'text-success' : 'text-danger'}">
                                                ${parseFloat(stock.change) > 0 ? '+' : ''}${parseFloat(stock.change).toFixed(2)} 
                                                (${parseFloat(changeValue).toFixed(2)}%)
                                            </td>
                                            <td>${formatVolume(stock.volume)}</td>
                                            <td>${relVolume}</td>
                                            <td>${typeof pe === 'number' ? pe.toFixed(2) : pe}</td>
                                            <td>${typeof eps === 'number' ? eps.toFixed(2) : eps}</td>
                                            <td>${typeof divYield === 'number' ? divYield.toFixed(2) + '%' : divYield}</td>
                                            <td>${sector}</td>
                                            <td>${getSignalBadge(stock.recommendation)}</td>
                                            <td>${getValidationBadge(stock)}</td>
                                        </tr>
                                        `;
                                    }).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Add click event listeners to rows for selection
        const rows = document.querySelectorAll('.stock-row');
        rows.forEach(row => {
            row.addEventListener('click', function() {
                const symbol = this.dataset.symbol;
                if (document.getElementById('stock-dropdown')) {
                    document.getElementById('stock-dropdown').value = symbol;
                    document.getElementById('stock-dropdown').dispatchEvent(new Event('change'));
                }
                generateTradingRecommendations(symbol);
            });
            row.style.cursor = 'pointer';
        });
        
        // Also update all stocks for the dropdown
        window.allStocks = stocks;
        hideLoading('top-stocks');
        
        // Initialize tooltips
        const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltips.forEach(tooltip => {
            new bootstrap.Tooltip(tooltip);
        });
        
    } catch (error) {
        hideLoading('top-stocks');
        console.error('Error fetching stocks:', error);
        showError('Failed to load top stocks data');
    }
}

// Function to generate trading recommendations
async function generateTradingRecommendations(symbol) {
    const recommendationPanel = document.getElementById('recommendation-panel');
    if (!recommendationPanel) {
        console.error('Recommendation panel not found');
        return;
    }
    
    try {
        // Show loading state
        recommendationPanel.innerHTML = `
            <div class="text-center py-3">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">Generating recommendations for ${symbol}...</p>
            </div>
        `;
        
        // Fetch the NGX market data
        const ngxData = await fetchNGXMarketData();
        const stockData = ngxData.find(stock => stock.symbol === symbol);
        
        if (!stockData) {
            recommendationPanel.innerHTML = `
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    Stock data not found for ${symbol}. Please select a valid stock.
                </div>
            `;
            return;
        }
        
        // Get stock details and market data
        const stock = {
            ...stockData,
            name: stockData.name,
            sector: stockData.sector,
            price: stockData.price,
            change: stockData.change_percent,
            marketCap: stockData.market_cap,
            pe: stockData.pe,
            eps: stockData.eps,
            dividend: stockData.div_yield,
            recommendation: stockData.recommendation
        };
        
        // Simulate analysis based on the stock sector
        // In a real application, this would fetch data from an API or backend
        const analysisData = analyzeStock(symbol);
        
        // Clear existing recommendations
        const recommendationsTable = document.getElementById('recommendations-table');
        if (!recommendationsTable) return;
        
        recommendationsTable.innerHTML = '';
        
        // Create a new row for the recommendation
        const row = document.createElement('tr');
        
        // Symbol cell
        const symbolCell = document.createElement('td');
        symbolCell.textContent = symbol;
        row.appendChild(symbolCell);
        
        // Name cell
        const nameCell = document.createElement('td');
        nameCell.textContent = stock.name;
        row.appendChild(nameCell);
        
        // Recommendation cell
        const recommendationCell = document.createElement('td');
        recommendationCell.innerHTML = `<span class="badge ${analysisData.recommendation === 'BUY' ? 'bg-success' : analysisData.recommendation === 'SELL' ? 'bg-danger' : 'bg-warning'}">${analysisData.recommendation}</span>`;
        row.appendChild(recommendationCell);
        
        // Entry Price cell
        const entryPriceCell = document.createElement('td');
        entryPriceCell.textContent = `₦${analysisData.entryPrice.toFixed(2)}`;
        row.appendChild(entryPriceCell);
        
        // Exit Price cell
        const exitPriceCell = document.createElement('td');
        exitPriceCell.textContent = `₦${analysisData.exitPrice.toFixed(2)}`;
        row.appendChild(exitPriceCell);
        
        // Stop Loss cell
        const stopLossCell = document.createElement('td');
        stopLossCell.textContent = `₦${analysisData.stopLoss.toFixed(2)}`;
        row.appendChild(stopLossCell);
        
        // Confidence cell
        const confidenceCell = document.createElement('td');
        confidenceCell.innerHTML = generateConfidenceStars(analysisData.confidence);
        row.appendChild(confidenceCell);
        
        // Add the row to the table
        recommendationsTable.appendChild(row);
    } catch (error) {
        console.error('Error generating trading recommendations:', error);
        recommendationPanel.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle-fill me-2"></i>
                Failed to generate trading recommendations. Please try again later.
            </div>
        `;
    }
}

// Function to generate confidence stars (1-5)
function generateConfidenceStars(confidence) {
    const maxStars = 5;
    const filledStars = Math.min(Math.max(Math.round(confidence), 1), maxStars);
    
    let starsHtml = '';
    for (let i = 0; i < maxStars; i++) {
        if (i < filledStars) {
            starsHtml += '<i class="bi bi-star-fill text-warning"></i>';
        } else {
            starsHtml += '<i class="bi bi-star text-muted"></i>';
        }
    }
    
    return starsHtml;
}

// Function to analyze a stock and generate recommendations
function analyzeStock(symbol) {
    // In a real application, this would fetch data from TradingView API
    // For demonstration, we'll generate simulated data based on the stock symbol
    
    // Use the symbol to generate a consistent but seemingly random value
    const hash = symbol.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    
    // Generate base price (between 10 and 500)
    const basePrice = 10 + (hash % 490);
    
    // Determine recommendation (BUY, HOLD, SELL)
    const recommendationOptions = ['BUY', 'HOLD', 'SELL'];
    const recommendationIndex = hash % 3;
    const recommendation = recommendationOptions[recommendationIndex];
    
    // Calculate entry, exit, and stop loss prices based on recommendation
    let entryPrice, exitPrice, stopLoss;
    
    if (recommendation === 'BUY') {
        entryPrice = basePrice;
        exitPrice = basePrice * (1 + (0.05 + (hash % 10) / 100));
        stopLoss = basePrice * (1 - (0.03 + (hash % 5) / 100));
    } else if (recommendation === 'SELL') {
        entryPrice = basePrice;
        exitPrice = basePrice * (1 - (0.05 + (hash % 10) / 100));
        stopLoss = basePrice * (1 + (0.03 + (hash % 5) / 100));
    } else { // HOLD
        entryPrice = basePrice;
        exitPrice = basePrice * (1 + (0.02 + (hash % 5) / 100));
        stopLoss = basePrice * (1 - (0.02 + (hash % 5) / 100));
    }
    
    // Calculate confidence (1-5)
    const confidence = 1 + (hash % 5);
    
    return {
        recommendation,
        entryPrice,
        exitPrice,
        stopLoss,
        confidence
    };
}

// Function to get signal badge HTML
function getSignalBadge(signal) {
    if (!signal) return '<span class="badge bg-secondary">NEUTRAL</span>';
    
    const signalMap = {
        'STRONG_BUY': '<span class="badge bg-success" data-bs-toggle="tooltip" title="Strong Buy Signal">STRONG BUY</span>',
        'BUY': '<span class="badge bg-success" data-bs-toggle="tooltip" title="Buy Signal">BUY</span>',
        'HOLD': '<span class="badge bg-warning" data-bs-toggle="tooltip" title="Hold Signal">HOLD</span>',
        'SELL': '<span class="badge bg-danger" data-bs-toggle="tooltip" title="Sell Signal">SELL</span>',
        'STRONG_SELL': '<span class="badge bg-danger" data-bs-toggle="tooltip" title="Strong Sell Signal">STRONG SELL</span>'
    };
    
    return signalMap[signal] || '<span class="badge bg-secondary">NEUTRAL</span>';
}

// Function to get validation badge HTML
function getValidationBadge(stock) {
    if (!stock) return '<span class="badge bg-secondary">No Validation</span>';
    
    // If we have the getValidationBadge function from the NGX module, use it
    if (typeof window.getValidationBadge === 'function') {
        return window.getValidationBadge(stock);
    }
    
    // Otherwise, use our internal implementation
    let badgeClass = 'bg-secondary';
    let icon = 'shield-exclamation';
    let source = stock.data_source || 'estimated';
    let tooltip = 'Data not validated';
    
    if (stock.validated) {
        // Determine badge style based on accuracy
        const accuracy = stock.accuracy || 0;
        if (accuracy >= 90) {
            badgeClass = 'bg-success';
            tooltip = `Highly accurate data (${accuracy}%)`;
        } else if (accuracy >= 70) {
            badgeClass = 'bg-info';
            tooltip = `Good data accuracy (${accuracy}%)`;
        } else if (accuracy >= 50) {
            badgeClass = 'bg-warning';
            tooltip = `Fair data accuracy (${accuracy}%)`;
        } else {
            badgeClass = 'bg-danger';
            tooltip = `Low data accuracy (${accuracy}%)`;
        }
        icon = 'shield-check';
    }
    
    return `<span class="badge ${badgeClass}" data-bs-toggle="tooltip" title="${tooltip}">
        ${source} <i class="bi bi-${icon}"></i>
    </span>`;
}

// Show loading spinner for a section
function showLoading(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    // Create loading overlay if it doesn't exist
    let loadingOverlay = container.querySelector('.loading-overlay');
    if (!loadingOverlay) {
        loadingOverlay = document.createElement('div');
        loadingOverlay.className = 'loading-overlay';
        loadingOverlay.innerHTML = `
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        `;
        container.appendChild(loadingOverlay);
    } else {
        loadingOverlay.style.display = 'flex';
    }
}

// Hide loading spinner for a section
function hideLoading(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const loadingOverlay = container.querySelector('.loading-overlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = 'none';
    }
}

// Show error message
function showError(message) {
    showToast(message, 'danger');
}

// Show toast message
function showToast(message, type = 'info') {
    // Create toast container if it doesn't exist
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    
    // Create toast element
    const toastId = 'toast-' + Date.now();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type === 'info' ? 'primary' : type} border-0`;
    toast.id = toastId;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    // Toast content
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    // Add to container
    toastContainer.appendChild(toast);
    
    // Initialize and show toast
    const bsToast = new bootstrap.Toast(toast, {
        autohide: true,
        delay: 3000
    });
    bsToast.show();
    
    // Remove after hidden
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}

// Function to populate the top stocks table
async function populateTopStocksTable() {
    const topStocksSection = document.getElementById('top-stocks');
    if (!topStocksSection) {
        console.error('Top stocks section not found');
        return;
    }
    
    // Show loading state
    topStocksSection.innerHTML = '';
    topStocksSection.innerHTML += `
        <h2 class="section-title mb-4">
            <i class="bi bi-table me-2"></i>Top Stocks
        </h2>
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-3">Fetching latest NGX market data...</p>
        </div>
    `;
    
    try {
        // Fetch the latest NGX market data
        const ngxData = await fetchNGXMarketData();
        
        // Sort by market cap (descending)
        const topStocks = ngxData.sort((a, b) => b.market_cap - a.market_cap);
        
        // Format the data for display
        const formattedStocks = topStocks.map(stock => {
            return {
                symbol: stock.symbol,
                name: stock.name,
                market_cap: formatMarketCap(stock.market_cap),
                price: '₦' + stock.price.toFixed(2),
                change: (stock.change_percent >= 0 ? '+' : '') + stock.change_percent.toFixed(2) + '%',
                change_class: stock.change_percent >= 0 ? 'text-success' : 'text-danger',
                volume: formatVolume(stock.volume),
                rel_vol: stock.rel_vol.toFixed(1),
                pe: stock.pe.toFixed(1),
                eps: stock.eps.toFixed(2),
                div_yield: stock.div_yield.toFixed(1) + '%',
                sector: stock.sector,
                subsector: stock.subsector,
                year_high: '₦' + stock.year_high.toFixed(2),
                year_low: '₦' + stock.year_low.toFixed(2),
                recommendation: stock.recommendation
            };
        });
        
        // Create table HTML
        const tableHTML = `
            <div class="card shadow-sm">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0"><i class="bi bi-table me-2"></i>Top Stocks</h5>
                    <button class="btn btn-sm btn-outline-primary" id="refresh-stocks">
                        <i class="bi bi-arrow-clockwise me-1"></i>Refresh
                    </button>
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-hover mb-0">
                            <thead>
                                <tr>
                                    <th>SYMBOL</th>
                                    <th>NAME</th>
                                    <th>MARKET CAP</th>
                                    <th>PRICE</th>
                                    <th>CHANGE</th>
                                    <th>VOLUME</th>
                                    <th>REL. VOL</th>
                                    <th>P/E</th>
                                    <th>EPS</th>
                                    <th>DIV YIELD</th>
                                    <th>SECTOR</th>
                                    <th>SIGNAL</th>
                                    <th>VALIDATION</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${formattedStocks.map(stock => `
                                    <tr data-symbol="${stock.symbol}" data-sector="${stock.sector}" data-subsector="${stock.subsector}">
                                        <td class="fw-bold">${stock.symbol}</td>
                                        <td>${stock.name}</td>
                                        <td>${stock.market_cap}</td>
                                        <td>${stock.price}</td>
                                        <td class="${stock.change_class}">${stock.change}</td>
                                        <td>${stock.volume}</td>
                                        <td>${stock.rel_vol}</td>
                                        <td>${stock.pe}</td>
                                        <td>${stock.eps}</td>
                                        <td>${stock.div_yield}</td>
                                        <td>${stock.sector}</td>
                                        <td>${getSignalBadge(stock.recommendation)}</td>
                                        <td>${getValidationBadge(stock)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="card-footer text-muted small">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>Data source: <a href="https://ngxgroup.com/exchange/data/equities-price-list/" target="_blank">Nigerian Exchange (NGX)</a></div>
                        <div>Last updated: ${new Date().toLocaleString()}</div>
                    </div>
                </div>
            </div>
        `;
        
        // Insert table into container
        topStocksSection.innerHTML = '';
        topStocksSection.innerHTML += `
            <h2 class="section-title mb-4">
                <i class="bi bi-table me-2"></i>Top Stocks
            </h2>
        `;
        topStocksSection.innerHTML += tableHTML;
        
        // Add click event to refresh button
        const refreshButton = document.getElementById('refresh-stocks');
        if (refreshButton) {
            refreshButton.addEventListener('click', function() {
                showToast('Refreshing stock data from NGX...', 'info');
                populateTopStocksTable().then(() => {
                    showToast('Stock data refreshed successfully!', 'success');
                }).catch(error => {
                    console.error('Error refreshing stock data:', error);
                    showToast('Failed to refresh stock data. Please try again.', 'error');
                });
            });
        }
        
        // Add click events to table rows
        const tableRows = topStocksSection.querySelectorAll('tbody tr');
        tableRows.forEach(row => {
            row.addEventListener('click', function() {
                const symbol = this.dataset.symbol;
                document.getElementById('stock-dropdown').value = symbol;
                document.getElementById('stock-dropdown').dispatchEvent(new Event('change'));
                generateTradingRecommendations(symbol);
            });
            row.style.cursor = 'pointer';
            
            // Add tooltip with additional information
            const sector = row.dataset.sector;
            const subsector = row.dataset.subsector;
            row.setAttribute('title', `${sector} > ${subsector}`);
        });
        
    } catch (error) {
        console.error('Error fetching NGX market data:', error);
        topStocksSection.innerHTML = '';
        topStocksSection.innerHTML += `
            <h2 class="section-title mb-4">
                <i class="bi bi-table me-2"></i>Top Stocks
            </h2>
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle-fill me-2"></i>
                Failed to load NGX market data. Please try again later.
            </div>
        `;
    }
}

populateTopStocksTable();
