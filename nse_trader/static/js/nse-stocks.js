// Nigerian Stock Exchange (NSE) Stocks Data
const NSE_STOCKS = [
    { symbol: "DANGCEM", name: "Dangote Cement Plc", sector: "Industrial Goods", subsector: "Building Materials" },
    { symbol: "ZENITHBA", name: "Zenith Bank Plc", sector: "Financial Services", subsector: "Banking" },
    { symbol: "GTCO", name: "Guaranty Trust Holding Co Plc", sector: "Financial Services", subsector: "Banking" },
    { symbol: "NESTLE", name: "Nestle Nigeria Plc", sector: "Consumer Goods", subsector: "Food Products" },
    { symbol: "MTNN", name: "MTN Nigeria Communications Plc", sector: "ICT", subsector: "Telecommunications" },
    { symbol: "FBNH", name: "FBN Holdings Plc", sector: "Financial Services", subsector: "Banking" },
    { symbol: "AIRTEL", name: "Airtel Africa Plc", sector: "ICT", subsector: "Telecommunications" },
    { symbol: "BUACEMENT", name: "BUA Cement Plc", sector: "Industrial Goods", subsector: "Building Materials" },
    { symbol: "BUAFOODS", name: "BUA Foods Plc", sector: "Consumer Goods", subsector: "Food Products" },
    { symbol: "ACCESSCO", name: "Access Holdings Plc", sector: "Financial Services", subsector: "Banking" },
    { symbol: "UBA", name: "United Bank for Africa Plc", sector: "Financial Services", subsector: "Banking" },
    { symbol: "SEPLAT", name: "Seplat Energy Plc", sector: "Oil & Gas", subsector: "Petroleum and Natural Gas" },
    { symbol: "TRANSCORP", name: "Transcorp Plc", sector: "Conglomerates", subsector: "Diversified" },
    { symbol: "OANDO", name: "Oando Plc", sector: "Oil & Gas", subsector: "Integrated Oil and Gas" },
    { symbol: "GUINNESS", name: "Guinness Nigeria Plc", sector: "Consumer Goods", subsector: "Beverages" },
    { symbol: "NB", name: "Nigerian Breweries Plc", sector: "Consumer Goods", subsector: "Beverages" },
    { symbol: "INTBREW", name: "International Breweries Plc", sector: "Consumer Goods", subsector: "Beverages" },
    { symbol: "WAPCO", name: "Lafarge Africa Plc", sector: "Industrial Goods", subsector: "Building Materials" },
    { symbol: "TOTAL", name: "TotalEnergies Marketing Nigeria Plc", sector: "Oil & Gas", subsector: "Marketing" },
    { symbol: "FLOURMILL", name: "Flour Mills Nigeria Plc", sector: "Consumer Goods", subsector: "Food Products" },
    { symbol: "PRESCO", name: "Presco Plc", sector: "Agriculture", subsector: "Crop Production" },
    { symbol: "OKOMUOIL", name: "Okomu Oil Palm Plc", sector: "Agriculture", subsector: "Crop Production" },
    { symbol: "STANBIC", name: "Stanbic IBTC Holdings Plc", sector: "Financial Services", subsector: "Banking" },
    { symbol: "FIDELITY", name: "Fidelity Bank Plc", sector: "Financial Services", subsector: "Banking" },
    { symbol: "FCMB", name: "FCMB Group Plc", sector: "Financial Services", subsector: "Banking" },
    { symbol: "CUSTODIAN", name: "Custodian Investment Plc", sector: "Financial Services", subsector: "Insurance" },
    { symbol: "UCAP", name: "United Capital Plc", sector: "Financial Services", subsector: "Capital Market" },
    { symbol: "BERGER", name: "Berger Paints Plc", sector: "Industrial Goods", subsector: "Building Materials" },
    { symbol: "CAP", name: "Chemical and Allied Products Plc", sector: "Industrial Goods", subsector: "Building Materials" },
    { symbol: "DANGSUGAR", name: "Dangote Sugar Refinery Plc", sector: "Consumer Goods", subsector: "Food Products" },
    { symbol: "NASCON", name: "NASCON Allied Industries Plc", sector: "Consumer Goods", subsector: "Food Products" },
    { symbol: "CADBURY", name: "Cadbury Nigeria Plc", sector: "Consumer Goods", subsector: "Food Products" },
    { symbol: "UNILEVER", name: "Unilever Nigeria Plc", sector: "Consumer Goods", subsector: "Personal/Household Products" },
    { symbol: "PZ", name: "PZ Cussons Nigeria Plc", sector: "Consumer Goods", subsector: "Personal/Household Products" },
    { symbol: "HONYFLOUR", name: "Honeywell Flour Mill Plc", sector: "Consumer Goods", subsector: "Food Products" },
    { symbol: "NAHCO", name: "Nigerian Aviation Handling Company Plc", sector: "Services", subsector: "Transport-Related Services" },
    { symbol: "JBERGER", name: "Julius Berger Nigeria Plc", sector: "Construction/Real Estate", subsector: "Building Construction" },
    { symbol: "MANSARD", name: "AXA Mansard Insurance Plc", sector: "Financial Services", subsector: "Insurance" },
    { symbol: "NGXGROUP", name: "Nigerian Exchange Group Plc", sector: "Financial Services", subsector: "Capital Market" },
    { symbol: "ARDOVA", name: "Ardova Plc", sector: "Oil & Gas", subsector: "Marketing" }
];

// Function to get stock data by symbol
function getStockBySymbol(symbol) {
    return NSE_STOCKS.find(stock => stock.symbol === symbol) || null;
}

// Function to get stock name by symbol
function getStockName(symbol) {
    const stock = getStockBySymbol(symbol);
    return stock ? stock.name : null;
}

// Function to get stocks by sector
function getStocksBySector(sector) {
    return NSE_STOCKS.filter(stock => stock.sector === sector);
}

// Function to get all sectors
function getAllSectors() {
    const sectors = new Set();
    NSE_STOCKS.forEach(stock => sectors.add(stock.sector));
    return Array.from(sectors).sort();
}

// Function to populate sector dropdown
function populateSectorDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;
    
    // Clear existing options
    dropdown.innerHTML = '<option value="">All Sectors</option>';
    
    // Add sectors
    getAllSectors().forEach(sector => {
        const option = document.createElement('option');
        option.value = sector;
        option.textContent = sector;
        dropdown.appendChild(option);
    });
}

// Function to populate stock dropdown
function populateStockDropdown(dropdownId, sectorFilter = null) {
    const dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;
    
    // Clear existing options
    dropdown.innerHTML = '<option value="">-- Select a stock --</option>';
    
    // Filter stocks by sector if provided
    const stocks = sectorFilter 
        ? NSE_STOCKS.filter(stock => stock.sector === sectorFilter)
        : NSE_STOCKS;
    
    // Sort stocks by name
    stocks.sort((a, b) => a.name.localeCompare(b.name));
    
    // Add stocks to dropdown
    stocks.forEach(stock => {
        const option = document.createElement('option');
        option.value = stock.symbol;
        option.textContent = `${stock.name} (${stock.symbol})`;
        dropdown.appendChild(option);
    });
}

// Initialize dropdowns when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Populate stock dropdown
    populateStockDropdown('stock-dropdown');
    
    // Setup sector filter if it exists
    const sectorDropdown = document.getElementById('sector-dropdown');
    if (sectorDropdown) {
        populateSectorDropdown('sector-dropdown');
        
        // Add event listener to filter stocks by sector
        sectorDropdown.addEventListener('change', function() {
            const selectedSector = sectorDropdown.value;
            populateStockDropdown('stock-dropdown', selectedSector || null);
        });
    }
});
