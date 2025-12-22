/**
 * Stock Charts Module for NSE Trader
 * Provides interactive charts for stock price visualization and technical analysis
 * Uses Chart.js for rendering
 */

// Generate sample historical data based on current price
function generateHistoricalData(stock, days = 30) {
    const data = [];
    const today = new Date();
    const startPrice = stock.price * 0.9; // Start about 10% lower than current
    let currentPrice = startPrice;
    
    // Create price trend with some randomness
    for (let i = 0; i < days; i++) {
        const date = new Date(today);
        date.setDate(today.getDate() - (days - i));
        
        // Add some randomness to price movement
        const change = (Math.random() - 0.48) * 0.02 * currentPrice;
        currentPrice += change;
        
        // Ensure we end at the current price on the last day
        if (i === days - 1) {
            currentPrice = stock.price;
        }
        
        data.push({
            date: date.toISOString().split('T')[0],
            price: currentPrice,
            volume: Math.floor(stock.volume * (0.5 + Math.random() * 0.7))
        });
    }
    
    return data;
}

// Calculate technical indicators
function calculateIndicators(priceData) {
    // Simple Moving Averages
    const prices = priceData.map(d => d.price);
    
    // 7-day SMA
    const sma7 = [];
    for (let i = 0; i < prices.length; i++) {
        if (i < 6) {
            sma7.push(null);
        } else {
            const sum = prices.slice(i-6, i+1).reduce((acc, val) => acc + val, 0);
            sma7.push(sum / 7);
        }
    }
    
    // 21-day SMA
    const sma21 = [];
    for (let i = 0; i < prices.length; i++) {
        if (i < 20) {
            sma21.push(null);
        } else {
            const sum = prices.slice(i-20, i+1).reduce((acc, val) => acc + val, 0);
            sma21.push(sum / 21);
        }
    }
    
    // RSI (14-day)
    const rsi = [];
    let avgGain = 0;
    let avgLoss = 0;
    
    for (let i = 0; i < prices.length; i++) {
        if (i < 14) {
            rsi.push(null);
            
            // Calculate first average gain/loss
            if (i > 0) {
                const change = prices[i] - prices[i-1];
                if (change >= 0) {
                    avgGain += change;
                } else {
                    avgLoss += Math.abs(change);
                }
                
                if (i === 13) {
                    avgGain = avgGain / 14;
                    avgLoss = avgLoss / 14;
                }
            }
        } else {
            const change = prices[i] - prices[i-1];
            let gain = 0;
            let loss = 0;
            
            if (change >= 0) {
                gain = change;
            } else {
                loss = Math.abs(change);
            }
            
            avgGain = (avgGain * 13 + gain) / 14;
            avgLoss = (avgLoss * 13 + loss) / 14;
            
            if (avgLoss === 0) {
                rsi.push(100);
            } else {
                const rs = avgGain / avgLoss;
                rsi.push(100 - (100 / (1 + rs)));
            }
        }
    }
    
    return {
        sma7,
        sma21,
        rsi
    };
}

// Create price chart for a stock
function createPriceChart(stockSymbol, container) {
    if (!container) return;
    
    // Show loading state
    container.innerHTML = '<div class="loading">Loading chart data...</div>';
    
    // Fetch stock data
    fetch('/api/validated-market-data')
        .then(response => response.json())
        .then(data => {
            // Find the stock
            const stock = data.data.find(s => s.symbol === stockSymbol);
            if (!stock) {
                container.innerHTML = '<div class="error">Stock data not found</div>';
                return;
            }
            
            // Generate historical data
            const historicalData = generateHistoricalData(stock);
            
            // Calculate technical indicators
            const indicators = calculateIndicators(historicalData);
            
            // Create chart container
            container.innerHTML = '';
            
            // Create tabs for different chart types
            const tabsContainer = document.createElement('div');
            tabsContainer.className = 'chart-tabs';
            tabsContainer.innerHTML = `
                <div class="chart-tab active" data-chart="price">Price</div>
                <div class="chart-tab" data-chart="volume">Volume</div>
                <div class="chart-tab" data-chart="rsi">RSI</div>
            `;
            container.appendChild(tabsContainer);
            
            // Create canvas for chart
            const canvas = document.createElement('canvas');
            canvas.id = `chart-${stockSymbol}`;
            canvas.height = 300;
            container.appendChild(canvas);
            
            // Add chart legend
            const legendContainer = document.createElement('div');
            legendContainer.className = 'chart-legend';
            legendContainer.innerHTML = `
                <div class="legend-item">
                    <span class="legend-color" style="background-color: #2c3e50"></span>
                    <span class="legend-label">Price</span>
                </div>
                <div class="legend-item">
                    <span class="legend-color" style="background-color: #3498db"></span>
                    <span class="legend-label">7-day SMA</span>
                </div>
                <div class="legend-item">
                    <span class="legend-color" style="background-color: #e74c3c"></span>
                    <span class="legend-label">21-day SMA</span>
                </div>
            `;
            container.appendChild(legendContainer);
            
            // Create the chart
            const ctx = canvas.getContext('2d');
            const labels = historicalData.map(d => d.date);
            const priceData = historicalData.map(d => d.price);
            
            // Create initial price chart
            let chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Price',
                            data: priceData,
                            borderColor: '#2c3e50',
                            backgroundColor: 'rgba(44, 62, 80, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.2
                        },
                        {
                            label: '7-day SMA',
                            data: indicators.sma7,
                            borderColor: '#3498db',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            tension: 0.4,
                            pointRadius: 0
                        },
                        {
                            label: '21-day SMA',
                            data: indicators.sma21,
                            borderColor: '#e74c3c',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            tension: 0.4,
                            pointRadius: 0
                        }
                    ]
                },
                options: {
                    responsive: true,
                    plugins: {
                        title: {
                            display: true,
                            text: `${stock.symbol} - ${stock.name} (₦${stock.price.toFixed(2)})`,
                            font: {
                                size: 16
                            }
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                display: false
                            }
                        },
                        y: {
                            beginAtZero: false,
                            grid: {
                                color: 'rgba(0, 0, 0, 0.05)'
                            }
                        }
                    }
                }
            });
            
            // Add tab switching functionality
            const chartTabs = tabsContainer.querySelectorAll('.chart-tab');
            chartTabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    // Remove active class from all tabs
                    chartTabs.forEach(t => t.classList.remove('active'));
                    
                    // Add active class to clicked tab
                    tab.classList.add('active');
                    
                    // Update chart based on selected tab
                    const chartType = tab.getAttribute('data-chart');
                    
                    // Destroy existing chart
                    chart.destroy();
                    
                    // Create new chart based on selection
                    if (chartType === 'price') {
                        // Update legend
                        legendContainer.innerHTML = `
                            <div class="legend-item">
                                <span class="legend-color" style="background-color: #2c3e50"></span>
                                <span class="legend-label">Price</span>
                            </div>
                            <div class="legend-item">
                                <span class="legend-color" style="background-color: #3498db"></span>
                                <span class="legend-label">7-day SMA</span>
                            </div>
                            <div class="legend-item">
                                <span class="legend-color" style="background-color: #e74c3c"></span>
                                <span class="legend-label">21-day SMA</span>
                            </div>
                        `;
                        
                        // Create price chart
                        chart = new Chart(ctx, {
                            type: 'line',
                            data: {
                                labels: labels,
                                datasets: [
                                    {
                                        label: 'Price',
                                        data: priceData,
                                        borderColor: '#2c3e50',
                                        backgroundColor: 'rgba(44, 62, 80, 0.1)',
                                        borderWidth: 2,
                                        fill: true,
                                        tension: 0.2
                                    },
                                    {
                                        label: '7-day SMA',
                                        data: indicators.sma7,
                                        borderColor: '#3498db',
                                        backgroundColor: 'transparent',
                                        borderWidth: 2,
                                        tension: 0.4,
                                        pointRadius: 0
                                    },
                                    {
                                        label: '21-day SMA',
                                        data: indicators.sma21,
                                        borderColor: '#e74c3c',
                                        backgroundColor: 'transparent',
                                        borderWidth: 2,
                                        tension: 0.4,
                                        pointRadius: 0
                                    }
                                ]
                            },
                            options: {
                                responsive: true,
                                plugins: {
                                    title: {
                                        display: true,
                                        text: `${stock.symbol} - ${stock.name} (₦${stock.price.toFixed(2)})`,
                                        font: {
                                            size: 16
                                        }
                                    },
                                    tooltip: {
                                        mode: 'index',
                                        intersect: false
                                    }
                                },
                                scales: {
                                    x: {
                                        grid: {
                                            display: false
                                        }
                                    },
                                    y: {
                                        beginAtZero: false,
                                        grid: {
                                            color: 'rgba(0, 0, 0, 0.05)'
                                        }
                                    }
                                }
                            }
                        });
                    } else if (chartType === 'volume') {
                        // Update legend
                        legendContainer.innerHTML = `
                            <div class="legend-item">
                                <span class="legend-color" style="background-color: #3498db"></span>
                                <span class="legend-label">Volume</span>
                            </div>
                        `;
                        
                        // Create volume chart
                        chart = new Chart(ctx, {
                            type: 'bar',
                            data: {
                                labels: labels,
                                datasets: [
                                    {
                                        label: 'Volume',
                                        data: historicalData.map(d => d.volume),
                                        backgroundColor: 'rgba(52, 152, 219, 0.7)',
                                        borderWidth: 0
                                    }
                                ]
                            },
                            options: {
                                responsive: true,
                                plugins: {
                                    title: {
                                        display: true,
                                        text: `${stock.symbol} - Trading Volume`,
                                        font: {
                                            size: 16
                                        }
                                    },
                                    tooltip: {
                                        mode: 'index',
                                        intersect: false,
                                        callbacks: {
                                            label: function(context) {
                                                return `Volume: ${context.raw.toLocaleString()}`;
                                            }
                                        }
                                    }
                                },
                                scales: {
                                    x: {
                                        grid: {
                                            display: false
                                        }
                                    },
                                    y: {
                                        beginAtZero: true,
                                        grid: {
                                            color: 'rgba(0, 0, 0, 0.05)'
                                        }
                                    }
                                }
                            }
                        });
                    } else if (chartType === 'rsi') {
                        // Update legend
                        legendContainer.innerHTML = `
                            <div class="legend-item">
                                <span class="legend-color" style="background-color: #9b59b6"></span>
                                <span class="legend-label">RSI (14-day)</span>
                            </div>
                            <div class="legend-item">
                                <span class="legend-color" style="background-color: #e74c3c"></span>
                                <span class="legend-label">Overbought (70)</span>
                            </div>
                            <div class="legend-item">
                                <span class="legend-color" style="background-color: #2ecc71"></span>
                                <span class="legend-label">Oversold (30)</span>
                            </div>
                        `;
                        
                        // Create RSI chart
                        chart = new Chart(ctx, {
                            type: 'line',
                            data: {
                                labels: labels,
                                datasets: [
                                    {
                                        label: 'RSI (14-day)',
                                        data: indicators.rsi,
                                        borderColor: '#9b59b6',
                                        backgroundColor: 'rgba(155, 89, 182, 0.1)',
                                        borderWidth: 2,
                                        fill: true,
                                        tension: 0.2
                                    },
                                    {
                                        label: 'Overbought (70)',
                                        data: Array(labels.length).fill(70),
                                        borderColor: '#e74c3c',
                                        borderDash: [5, 5],
                                        backgroundColor: 'transparent',
                                        borderWidth: 1,
                                        pointRadius: 0
                                    },
                                    {
                                        label: 'Oversold (30)',
                                        data: Array(labels.length).fill(30),
                                        borderColor: '#2ecc71',
                                        borderDash: [5, 5],
                                        backgroundColor: 'transparent',
                                        borderWidth: 1,
                                        pointRadius: 0
                                    }
                                ]
                            },
                            options: {
                                responsive: true,
                                plugins: {
                                    title: {
                                        display: true,
                                        text: `${stock.symbol} - Relative Strength Index`,
                                        font: {
                                            size: 16
                                        }
                                    },
                                    tooltip: {
                                        mode: 'index',
                                        intersect: false
                                    }
                                },
                                scales: {
                                    x: {
                                        grid: {
                                            display: false
                                        }
                                    },
                                    y: {
                                        min: 0,
                                        max: 100,
                                        grid: {
                                            color: 'rgba(0, 0, 0, 0.05)'
                                        }
                                    }
                                }
                            }
                        });
                    }
                });
            });
        })
        .catch(error => {
            console.error('Error fetching stock data for chart:', error);
            container.innerHTML = `<div class="error">Error loading chart: ${error.message}</div>`;
        });
}

// Make chart function available globally
window.createPriceChart = createPriceChart;
