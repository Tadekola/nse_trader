"""
Symbol Alias Registry for NSE Trader.

Provides centralized mapping between canonical (internal) symbols and
provider-specific symbols. This ensures consistent symbol resolution
across all data providers.

Phase 1 Audit: Created to minimize simulated data by fixing symbol mappings.
"""
from typing import Dict, Optional, List, Set
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DataProvider(str, Enum):
    """Supported data providers."""
    NGNMARKET = "ngnmarket"
    NGX_OFFICIAL = "ngx"
    KWAYISI = "kwayisi"
    APT_SECURITIES = "apt"  # Disabled but kept for reference
    SIMULATED = "simulated"


@dataclass
class SymbolMapping:
    """
    Mapping entry for a single canonical symbol.
    
    Attributes:
        canonical: The internal/canonical symbol used by NSE Trader
        ngnmarket: Symbol on ngnmarket.com (None if unsupported)
        ngx: Symbol on NGX official (usually same as canonical)
        unsupported_providers: Set of providers that don't support this symbol
        notes: Optional notes about the mapping
    """
    canonical: str
    ngnmarket: Optional[str] = None
    ngx: Optional[str] = None
    kwayisi: Optional[str] = None
    unsupported_providers: Set[DataProvider] = field(default_factory=set)
    notes: Optional[str] = None
    
    def get_provider_symbol(self, provider: DataProvider) -> Optional[str]:
        """Get the symbol for a specific provider."""
        if provider in self.unsupported_providers:
            return None
        
        if provider == DataProvider.NGNMARKET:
            return self.ngnmarket or self.canonical
        elif provider == DataProvider.NGX_OFFICIAL:
            return self.ngx or self.canonical
        elif provider == DataProvider.KWAYISI:
            return self.kwayisi or self.canonical
        elif provider == DataProvider.SIMULATED:
            return self.canonical
        
        return self.canonical
    
    def is_supported_by(self, provider: DataProvider) -> bool:
        """Check if symbol is supported by a provider."""
        return provider not in self.unsupported_providers


class SymbolAliasRegistry:
    """
    Centralized registry for symbol aliases across all providers.
    
    This registry ensures that:
    1. All providers use correct symbol mappings
    2. Unsupported symbols are clearly marked
    3. Symbol resolution is consistent across the application
    
    Usage:
        registry = get_symbol_alias_registry()
        ngnmarket_symbol = registry.get_provider_symbol("FBNH", DataProvider.NGNMARKET)
        # Returns "FBNHOLDINGS"
    """
    
    # Known symbol mappings
    # Format: canonical_symbol -> SymbolMapping
    # Verified mappings based on ngnmarket.com URL structure
    MAPPINGS: Dict[str, SymbolMapping] = {
        # === KNOWN OFFENDERS (Phase 1 fixes) ===
        
        # FBNH -> FBNHOLDINGS on ngnmarket.com
        "FBNH": SymbolMapping(
            canonical="FBNH",
            ngnmarket="FBNHOLDINGS",
            ngx="FBNH",
            notes="FBN Holdings - ngnmarket uses FBNHOLDINGS"
        ),
        
        # FLOURMILL -> FLOURMILLS on ngnmarket.com
        "FLOURMILL": SymbolMapping(
            canonical="FLOURMILL",
            ngnmarket="FLOURMILLS",
            ngx="FLOURMILL",
            notes="Flour Mills of Nigeria - ngnmarket uses FLOURMILLS"
        ),
        
        # ARDOVA -> ARDOVAPLC on ngnmarket.com
        "ARDOVA": SymbolMapping(
            canonical="ARDOVA",
            ngnmarket="ARDOVAPLC",
            ngx="ARDOVA",
            notes="Ardova Plc - ngnmarket uses ARDOVAPLC"
        ),
        
        # JAPAULOIL - needs verification
        "JAPAULOIL": SymbolMapping(
            canonical="JAPAULOIL",
            ngnmarket="JAPAULGOLD",  # May be JAPAULGOLD or similar
            ngx="JAPAULOIL",
            notes="Japaul Gold & Ventures - verify ngnmarket symbol"
        ),
        
        # === Additional mappings discovered ===
        
        # GTCO variations
        "GTCO": SymbolMapping(
            canonical="GTCO",
            ngnmarket="GTCO",
            ngx="GTCO",
            notes="Guaranty Trust Holding Company"
        ),
        
        # ACCESSCORP variations
        "ACCESSCORP": SymbolMapping(
            canonical="ACCESSCORP",
            ngnmarket="ACCESSCORP",
            ngx="ACCESSCORP",
            kwayisi="ACCESS",
            notes="Access Holdings Plc - kwayisi uses old ticker ACCESS"
        ),
        
        # ZENITHBANK - standard
        "ZENITHBANK": SymbolMapping(
            canonical="ZENITHBANK",
            ngnmarket="ZENITHBANK",
            ngx="ZENITHBANK",
            notes="Zenith Bank Plc"
        ),
        
        # UBA - standard
        "UBA": SymbolMapping(
            canonical="UBA",
            ngnmarket="UBA",
            ngx="UBA",
            notes="United Bank for Africa"
        ),
        
        # DANGCEM - standard
        "DANGCEM": SymbolMapping(
            canonical="DANGCEM",
            ngnmarket="DANGCEM",
            ngx="DANGCEM",
            notes="Dangote Cement Plc"
        ),
        
        # BUACEMENT - standard
        "BUACEMENT": SymbolMapping(
            canonical="BUACEMENT",
            ngnmarket="BUACEMENT",
            ngx="BUACEMENT",
            notes="BUA Cement Plc"
        ),
        
        # SEPLAT - standard
        "SEPLAT": SymbolMapping(
            canonical="SEPLAT",
            ngnmarket="SEPLAT",
            ngx="SEPLAT",
            notes="Seplat Energy Plc"
        ),
        
        # MTNN - standard
        "MTNN": SymbolMapping(
            canonical="MTNN",
            ngnmarket="MTNN",
            ngx="MTNN",
            notes="MTN Nigeria Communications Plc"
        ),
        
        # AIRTELAFRI - standard
        "AIRTELAFRI": SymbolMapping(
            canonical="AIRTELAFRI",
            ngnmarket="AIRTELAFRI",
            ngx="AIRTELAFRI",
            notes="Airtel Africa Plc"
        ),
        
        # NESTLE - standard
        "NESTLE": SymbolMapping(
            canonical="NESTLE",
            ngnmarket="NESTLE",
            ngx="NESTLE",
            notes="Nestle Nigeria Plc"
        ),
        
        # STANBIC - ngnmarket uses same symbol
        "STANBIC": SymbolMapping(
            canonical="STANBIC",
            ngnmarket="STANBIC",
            ngx="STANBIC",
            notes="Stanbic IBTC Holdings"
        ),
        
        # OANDO - standard
        "OANDO": SymbolMapping(
            canonical="OANDO",
            ngnmarket="OANDO",
            ngx="OANDO",
            notes="Oando Plc"
        ),
        
        # TRANSCORP - standard
        "TRANSCORP": SymbolMapping(
            canonical="TRANSCORP",
            ngnmarket="TRANSCORP",
            ngx="TRANSCORP",
            notes="Transnational Corporation of Nigeria Plc"
        ),
        
        # WAPCO -> LAFARGE on ngnmarket?
        "WAPCO": SymbolMapping(
            canonical="WAPCO",
            ngnmarket="WAPCO",
            ngx="WAPCO",
            notes="Lafarge Africa Plc (WAPCO)"
        ),
        
        # GUINNESS - standard
        "GUINNESS": SymbolMapping(
            canonical="GUINNESS",
            ngnmarket="GUINNESS",
            ngx="GUINNESS",
            notes="Guinness Nigeria Plc"
        ),
        
        # NB - Nigerian Breweries
        "NB": SymbolMapping(
            canonical="NB",
            ngnmarket="NB",
            ngx="NB",
            notes="Nigerian Breweries Plc"
        ),
        
        # PRESCO - standard
        "PRESCO": SymbolMapping(
            canonical="PRESCO",
            ngnmarket="PRESCO",
            ngx="PRESCO",
            notes="Presco Plc"
        ),
        
        # TOTAL -> TOTALENERGIES on ngnmarket
        "TOTAL": SymbolMapping(
            canonical="TOTAL",
            ngnmarket="TOTALENERGIES",
            ngx="TOTAL",
            notes="TotalEnergies Marketing Nigeria - ngnmarket uses TOTALENERGIES"
        ),
        
        # CONOIL - standard
        "CONOIL": SymbolMapping(
            canonical="CONOIL",
            ngnmarket="CONOIL",
            ngx="CONOIL",
            notes="Conoil Plc"
        ),
        
        # FIDELITYBK - standard
        "FIDELITYBK": SymbolMapping(
            canonical="FIDELITYBK",
            ngnmarket="FIDELITYBK",
            ngx="FIDELITYBK",
            notes="Fidelity Bank Plc"
        ),
        
        # FCMB - standard
        "FCMB": SymbolMapping(
            canonical="FCMB",
            ngnmarket="FCMB",
            ngx="FCMB",
            notes="FCMB Group Plc"
        ),
        
        # STERLING -> STERLINGNG on ngnmarket
        "STERLING": SymbolMapping(
            canonical="STERLING",
            ngnmarket="STERLINGNG",
            ngx="STERLING",
            notes="Sterling Bank Plc - ngnmarket uses STERLINGNG"
        ),
        
        # WEMABANK - standard
        "WEMABANK": SymbolMapping(
            canonical="WEMABANK",
            ngnmarket="WEMABANK",
            ngx="WEMABANK",
            notes="Wema Bank Plc"
        ),
        
        # UNITYBNK - Unity Bank
        "UNITYBNK": SymbolMapping(
            canonical="UNITYBNK",
            ngnmarket="UNITYBNK",
            ngx="UNITYBNK",
            notes="Unity Bank Plc"
        ),
        
        # CADBURY - standard
        "CADBURY": SymbolMapping(
            canonical="CADBURY",
            ngnmarket="CADBURY",
            ngx="CADBURY",
            notes="Cadbury Nigeria Plc"
        ),
        
        # UNILEVER - standard
        "UNILEVER": SymbolMapping(
            canonical="UNILEVER",
            ngnmarket="UNILEVER",
            ngx="UNILEVER",
            notes="Unilever Nigeria Plc"
        ),
        
        # INTBREW - International Breweries
        "INTBREW": SymbolMapping(
            canonical="INTBREW",
            ngnmarket="INTBREW",
            ngx="INTBREW",
            notes="International Breweries Plc"
        ),
        
        # CHAMPION - Champion Breweries
        "CHAMPION": SymbolMapping(
            canonical="CHAMPION",
            ngnmarket="CHAMPION",
            ngx="CHAMPION",
            notes="Champion Breweries Plc"
        ),
        
        # PZ - PZ Cussons
        "PZ": SymbolMapping(
            canonical="PZ",
            ngnmarket="PZ",
            ngx="PZ",
            notes="PZ Cussons Nigeria Plc"
        ),
        
        # MAYBAKER - May & Baker
        "MAYBAKER": SymbolMapping(
            canonical="MAYBAKER",
            ngnmarket="MAYBAKER",
            ngx="MAYBAKER",
            notes="May & Baker Nigeria Plc"
        ),
        
        # FIDSON - Fidson Healthcare
        "FIDSON": SymbolMapping(
            canonical="FIDSON",
            ngnmarket="FIDSON",
            ngx="FIDSON",
            notes="Fidson Healthcare Plc"
        ),
        
        # GLAXOSMITH - GlaxoSmithKline
        "GLAXOSMITH": SymbolMapping(
            canonical="GLAXOSMITH",
            ngnmarket="GLAXOSMITH",
            ngx="GLAXOSMITH",
            notes="GlaxoSmithKline Consumer Nigeria Plc"
        ),
    }
    
    def __init__(self):
        """Initialize the registry."""
        self._custom_mappings: Dict[str, SymbolMapping] = {}
        self._resolution_cache: Dict[str, Dict[DataProvider, Optional[str]]] = {}
    
    def get_mapping(self, canonical_symbol: str) -> Optional[SymbolMapping]:
        """Get the full mapping for a canonical symbol."""
        symbol = canonical_symbol.upper()
        
        # Check custom mappings first
        if symbol in self._custom_mappings:
            return self._custom_mappings[symbol]
        
        # Check built-in mappings
        return self.MAPPINGS.get(symbol)
    
    def get_provider_symbol(
        self, 
        canonical_symbol: str, 
        provider: DataProvider
    ) -> str:
        """
        Get the provider-specific symbol for a canonical symbol.
        
        Args:
            canonical_symbol: The internal/canonical symbol
            provider: The data provider to get symbol for
            
        Returns:
            The provider-specific symbol, or the canonical symbol if no mapping
        """
        symbol = canonical_symbol.upper()
        
        # Check cache first
        cache_key = symbol
        if cache_key in self._resolution_cache:
            cached = self._resolution_cache[cache_key].get(provider)
            if cached is not None:
                return cached
        
        # Get mapping
        mapping = self.get_mapping(symbol)
        
        if mapping:
            result = mapping.get_provider_symbol(provider)
            if result:
                # Cache the result
                if cache_key not in self._resolution_cache:
                    self._resolution_cache[cache_key] = {}
                self._resolution_cache[cache_key][provider] = result
                return result
        
        # Default: use canonical symbol
        return symbol
    
    def is_supported_by_provider(
        self, 
        canonical_symbol: str, 
        provider: DataProvider
    ) -> bool:
        """Check if a symbol is supported by a specific provider."""
        symbol = canonical_symbol.upper()
        mapping = self.get_mapping(symbol)
        
        if not mapping:
            # No explicit mapping means we assume it's supported
            return True
        
        return mapping.is_supported_by(provider)
    
    def get_unsupported_symbols(self, provider: DataProvider) -> List[str]:
        """Get all symbols that are explicitly marked as unsupported by a provider."""
        unsupported = []
        
        for symbol, mapping in self.MAPPINGS.items():
            if not mapping.is_supported_by(provider):
                unsupported.append(symbol)
        
        for symbol, mapping in self._custom_mappings.items():
            if not mapping.is_supported_by(provider):
                unsupported.append(symbol)
        
        return unsupported
    
    def add_mapping(self, mapping: SymbolMapping) -> None:
        """Add or update a custom mapping."""
        self._custom_mappings[mapping.canonical.upper()] = mapping
        # Clear cache for this symbol
        if mapping.canonical.upper() in self._resolution_cache:
            del self._resolution_cache[mapping.canonical.upper()]
    
    def get_all_provider_symbols(self, provider: DataProvider) -> Dict[str, str]:
        """Get all canonical -> provider symbol mappings for a provider."""
        result = {}
        
        # Combine built-in and custom mappings
        all_mappings = {**self.MAPPINGS, **self._custom_mappings}
        
        for canonical, mapping in all_mappings.items():
            provider_symbol = mapping.get_provider_symbol(provider)
            if provider_symbol:
                result[canonical] = provider_symbol
        
        return result
    
    def get_known_offenders(self) -> Dict[str, SymbolMapping]:
        """
        Get symbols that require special mapping (offenders).
        
        These are symbols where canonical != provider symbol for at least one provider.
        """
        offenders = {}
        
        for canonical, mapping in self.MAPPINGS.items():
            # Check if any provider needs a different symbol
            if (mapping.ngnmarket and mapping.ngnmarket != canonical) or \
               (mapping.ngx and mapping.ngx != canonical) or \
               mapping.unsupported_providers:
                offenders[canonical] = mapping
        
        return offenders
    
    def clear_cache(self) -> None:
        """Clear the resolution cache."""
        self._resolution_cache.clear()


# Singleton instance
_registry_instance: Optional[SymbolAliasRegistry] = None


def get_symbol_alias_registry() -> SymbolAliasRegistry:
    """Get the singleton symbol alias registry."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = SymbolAliasRegistry()
    return _registry_instance
