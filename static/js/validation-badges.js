/**
 * Creates a validation badge element for a stock
 * @param {Object} stock - The stock object with validation information
 * @param {string[]} stock.sources - Array of data sources (e.g. 'NGX', 'TradingView')
 * @param {number} stock.accuracy - Validation accuracy as a decimal (0-1)
 * @param {string} stock.validation_status - Status ('verified', 'unverified', 'error', 'circuit_breaker', etc.)
 * @returns {HTMLElement} - The badge element
 */
function createValidationBadge(stock) {
    const badge = document.createElement('div');
    badge.className = `validation-badge ${stock.validation_status}`;
    
    // Add circuit breaker indicator if applicable
    if (stock.validation_status === 'circuit_breaker') {
        badge.innerHTML = `
            <span class="circuit-breaker-indicator"><i class="fas fa-bolt"></i></span>
            <span class="source-indicators">
                ${stock.sources.includes('NGX') ? '<i class="ngx-indicator"></i>' : ''}
                ${stock.sources.includes('TradingView') ? '<i class="tv-indicator"></i>' : ''}
            </span>
            <span class="accuracy">${Math.round(stock.accuracy*100)}%</span>
        `;
        badge.title = `Circuit Breaker Active\nValidation: ${stock.validation_status}\nAccuracy: ${Math.round(stock.accuracy*100)}%\nSources: ${stock.sources.join(', ')}`;
    } else {
        badge.innerHTML = `
            <span class="source-indicators">
                ${stock.sources.includes('NGX') ? '<i class="ngx-indicator"></i>' : ''}
                ${stock.sources.includes('TradingView') ? '<i class="tv-indicator"></i>' : ''}
            </span>
            <span class="accuracy">${Math.round(stock.accuracy*100)}%</span>
        `;
        badge.title = `Validation: ${stock.validation_status}\nAccuracy: ${Math.round(stock.accuracy*100)}%\nSources: ${stock.sources.join(', ')}`;
    }
    
    return badge;
}

/**
 * Updates the validation status widget in the header
 * Shows detailed information about system status, data sources, and caching
 */
async function updateValidationStatusWidget() {
    const widget = document.getElementById('validation-status-widget');
    if (!widget) return;
    
    try {
        // Fetch validation status from the API
        const response = await fetch('/api/validation-status');
        const data = await response.json();
        
        // Create status display with detailed information
        let statusHTML = `
            <div class="status-indicator ${data.system_status === 'active' ? 'active' : 'inactive'}"></div>
            <div class="status-details">
                <span class="status-main">Validation System: ${data.system_status === 'active' ? 'Online' : 'Offline'}</span>
                <div class="status-sources">
                    <span class="source ${data.source_statuses.NGX === 'healthy' ? 'healthy' : 'degraded'}">
                        <i class="ngx-indicator"></i> NGX: ${data.source_statuses.NGX}
                    </span>
                    <span class="source ${data.source_statuses.TradingView === 'healthy' ? 'healthy' : 'degraded'}">
                        <i class="tv-indicator"></i> TradingView: ${data.source_statuses.TradingView}
                    </span>
                </div>
                <span class="status-time">Last validated: ${new Date(data.last_validation).toLocaleTimeString()}</span>
            </div>
            <button id="status-details-btn" class="btn-small"><i class="fas fa-info-circle"></i></button>
        `;
        
        widget.innerHTML = statusHTML;
        
        // Add event listener for the details button
        const detailsBtn = document.getElementById('status-details-btn');
        if (detailsBtn) {
            detailsBtn.addEventListener('click', showValidationDetails);
        }
        
    } catch (error) {
        console.error('Error updating validation status widget:', error);
        widget.innerHTML = `
            <div class="status-indicator error"></div>
            <span>Validation System: Error</span>
        `;
    }
}

/**
 * Shows a modal with detailed validation system information
 */
function showValidationDetails() {
    // Check if modal already exists
    let modal = document.getElementById('validation-details-modal');
    
    if (!modal) {
        // Create modal if it doesn't exist
        modal = document.createElement('div');
        modal.id = 'validation-details-modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Validation System Details</h3>
                    <span class="close-modal">&times;</span>
                </div>
                <div class="modal-body">
                    <div class="loading">Loading details...</div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        // Add event listener to close button
        const closeBtn = modal.querySelector('.close-modal');
        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });
        
        // Close when clicking outside the modal
        window.addEventListener('click', (event) => {
            if (event.target === modal) {
                modal.style.display = 'none';
            }
        });
    }
    
    // Show modal
    modal.style.display = 'block';
    
    // Fetch and display detailed information
    updateValidationDetailsModal();
}

/**
 * Updates the validation details modal with current information
 */
async function updateValidationDetailsModal() {
    const modalBody = document.querySelector('#validation-details-modal .modal-body');
    if (!modalBody) return;
    
    try {
        // Fetch validation status
        const statusResponse = await fetch('/api/validation-status');
        const statusData = await statusResponse.json();
        
        // Fetch market data for validation accuracy
        const marketResponse = await fetch('/api/validated-market-data');
        const marketData = await marketResponse.json();
        
        // Create detailed info display
        const detailsHTML = `
            <div class="details-section">
                <h4>System Status</h4>
                <p><strong>Status:</strong> <span class="${statusData.system_status === 'active' ? 'status-active' : 'status-inactive'}">${statusData.system_status}</span></p>
                <p><strong>Last Validation:</strong> ${new Date(statusData.last_validation).toLocaleString()}</p>
            </div>
            
            <div class="details-section">
                <h4>Data Sources</h4>
                <div class="source-status">
                    <div class="source-icon ngx"></div>
                    <strong>Nigerian Exchange Group (NGX):</strong> 
                    <span class="status-badge ${statusData.source_statuses.NGX === 'healthy' ? 'status-healthy' : 'status-degraded'}">                        ${statusData.source_statuses.NGX}
                    </span>
                </div>
                <div class="source-status">
                    <div class="source-icon tradingview"></div>
                    <strong>TradingView:</strong> 
                    <span class="status-badge ${statusData.source_statuses.TradingView === 'healthy' ? 'status-healthy' : 'status-degraded'}">                        ${statusData.source_statuses.TradingView}
                    </span>
                </div>
            </div>
            
            <div class="details-section">
                <h4>Cache Status</h4>
                <div class="cache-status ${statusData.redis_available ? 'cache-available' : 'cache-unavailable'}">
                    <i class="${statusData.redis_available ? 'fas fa-database' : 'fas fa-exclamation-triangle'}"></i>
                    <span>Redis Cache: ${statusData.redis_available ? 'Available' : 'Unavailable'}</span>
                </div>
                <p>${statusData.redis_available ? 'Data caching is active for improved performance.' : 'Fallback data is being used. Cache unavailable.'}</p>
            </div>
            
            <div class="details-section">
                <h4>Circuit Breaker Status</h4>
                <p><strong>Status:</strong> ${statusData.circuit_breakers_active ? 'Active for some stocks' : 'Inactive'}</p>
                ${statusData.circuit_breakers_active ? `<p><strong>Active circuit breakers:</strong> ${statusData.active_circuit_breakers.join(', ')}</p>` : ''}
            </div>
            
            <div class="details-section">
                <h4>Data Validation Summary</h4>
                <p><strong>Overall Accuracy:</strong> ${Math.round(marketData.validation_accuracy * 100)}%</p>
                <p><strong>Stocks with Multiple Sources:</strong> ${marketData.data.filter(stock => stock.sources.length > 1).length} of ${marketData.data.length}</p>
                <p><strong>Verified Stocks:</strong> ${marketData.data.filter(stock => stock.validation_status === 'verified').length} of ${marketData.data.length}</p>
            </div>
        `;
        
        modalBody.innerHTML = detailsHTML;
        
    } catch (error) {
        console.error('Error updating validation details modal:', error);
        modalBody.innerHTML = `<div class="error">Error loading validation details: ${error.message}</div>`;
    }
}

// Make the functions available globally
window.createValidationBadge = createValidationBadge;
window.updateValidationStatusWidget = updateValidationStatusWidget;
window.showValidationDetails = showValidationDetails;

// Initialize validation status widget when DOM is loaded
document.addEventListener('DOMContentLoaded', updateValidationStatusWidget);

// Update status every 30 seconds
setInterval(updateValidationStatusWidget, 30000);
