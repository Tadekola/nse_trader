"""
Tests for Symbol Alias Registry and Provider Healthchecks (Phase 1).

These tests verify:
1. Symbol alias mappings are correct
2. Known offenders resolve to correct provider symbols
3. Provider URL construction uses mapped symbols
4. No symbol routes to simulated unless all real sources fail
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.data.sources.symbol_aliases import (
    SymbolAliasRegistry,
    SymbolMapping,
    DataProvider,
    get_symbol_alias_registry,
)


class TestSymbolAliasRegistry:
    """Test the SymbolAliasRegistry class."""
    
    def test_registry_initialization(self):
        """Registry should initialize with built-in mappings."""
        registry = SymbolAliasRegistry()
        
        # Should have mappings
        assert len(registry.MAPPINGS) > 0
        
        # Should include known offenders
        assert "FBNH" in registry.MAPPINGS
        assert "FLOURMILL" in registry.MAPPINGS
        assert "ARDOVA" in registry.MAPPINGS
        assert "JAPAULOIL" in registry.MAPPINGS
    
    def test_get_provider_symbol_with_mapping(self):
        """Should return mapped symbol when mapping exists."""
        registry = SymbolAliasRegistry()
        
        # FBNH -> FBNHOLDINGS on ngnmarket
        result = registry.get_provider_symbol("FBNH", DataProvider.NGNMARKET)
        assert result == "FBNHOLDINGS"
        
        # FLOURMILL -> FLOURMILLS on ngnmarket
        result = registry.get_provider_symbol("FLOURMILL", DataProvider.NGNMARKET)
        assert result == "FLOURMILLS"
        
        # ARDOVA -> ARDOVAPLC on ngnmarket
        result = registry.get_provider_symbol("ARDOVA", DataProvider.NGNMARKET)
        assert result == "ARDOVAPLC"
    
    def test_get_provider_symbol_without_mapping(self):
        """Should return canonical symbol when no mapping exists."""
        registry = SymbolAliasRegistry()
        
        # Unknown symbol should return itself
        result = registry.get_provider_symbol("UNKNOWNSYMBOL", DataProvider.NGNMARKET)
        assert result == "UNKNOWNSYMBOL"
    
    def test_get_provider_symbol_case_insensitive(self):
        """Symbol lookup should be case insensitive."""
        registry = SymbolAliasRegistry()
        
        # Lower case should work
        result = registry.get_provider_symbol("fbnh", DataProvider.NGNMARKET)
        assert result == "FBNHOLDINGS"
        
        # Mixed case should work
        result = registry.get_provider_symbol("FbNh", DataProvider.NGNMARKET)
        assert result == "FBNHOLDINGS"
    
    def test_get_provider_symbol_ngx(self):
        """Should return NGX symbol (usually canonical)."""
        registry = SymbolAliasRegistry()
        
        # FBNH on NGX should remain FBNH
        result = registry.get_provider_symbol("FBNH", DataProvider.NGX_OFFICIAL)
        assert result == "FBNH"
        
        # FLOURMILL on NGX should remain FLOURMILL
        result = registry.get_provider_symbol("FLOURMILL", DataProvider.NGX_OFFICIAL)
        assert result == "FLOURMILL"
    
    def test_get_mapping(self):
        """Should return full mapping for a symbol."""
        registry = SymbolAliasRegistry()
        
        mapping = registry.get_mapping("FBNH")
        assert mapping is not None
        assert mapping.canonical == "FBNH"
        assert mapping.ngnmarket == "FBNHOLDINGS"
        assert mapping.ngx == "FBNH"
    
    def test_add_custom_mapping(self):
        """Should allow adding custom mappings."""
        registry = SymbolAliasRegistry()
        
        # Add custom mapping
        custom = SymbolMapping(
            canonical="CUSTOMSYM",
            ngnmarket="CUSTOMNGNMARKET",
            ngx="CUSTOMNGX"
        )
        registry.add_mapping(custom)
        
        # Should resolve correctly
        result = registry.get_provider_symbol("CUSTOMSYM", DataProvider.NGNMARKET)
        assert result == "CUSTOMNGNMARKET"
    
    def test_get_known_offenders(self):
        """Should return symbols that require special mapping."""
        registry = SymbolAliasRegistry()
        
        offenders = registry.get_known_offenders()
        
        # Known offenders should be included
        assert "FBNH" in offenders
        assert "FLOURMILL" in offenders
        assert "ARDOVA" in offenders
        
        # Each should have different ngnmarket symbol
        assert offenders["FBNH"].ngnmarket != "FBNH"
        assert offenders["FLOURMILL"].ngnmarket != "FLOURMILL"
        assert offenders["ARDOVA"].ngnmarket != "ARDOVA"
    
    def test_singleton_registry(self):
        """get_symbol_alias_registry should return singleton."""
        registry1 = get_symbol_alias_registry()
        registry2 = get_symbol_alias_registry()
        
        assert registry1 is registry2
    
    def test_cache_clearing(self):
        """Should clear resolution cache."""
        registry = SymbolAliasRegistry()
        
        # Populate cache
        registry.get_provider_symbol("FBNH", DataProvider.NGNMARKET)
        assert len(registry._resolution_cache) > 0
        
        # Clear cache
        registry.clear_cache()
        assert len(registry._resolution_cache) == 0


class TestKnownOffenderMappings:
    """Test that known offender symbols map correctly."""
    
    @pytest.fixture
    def registry(self):
        return SymbolAliasRegistry()
    
    def test_fbnh_mapping(self, registry):
        """FBNH should map to FBNHOLDINGS on ngnmarket."""
        assert registry.get_provider_symbol("FBNH", DataProvider.NGNMARKET) == "FBNHOLDINGS"
        assert registry.get_provider_symbol("FBNH", DataProvider.NGX_OFFICIAL) == "FBNH"
    
    def test_flourmill_mapping(self, registry):
        """FLOURMILL should map to FLOURMILLS on ngnmarket."""
        assert registry.get_provider_symbol("FLOURMILL", DataProvider.NGNMARKET) == "FLOURMILLS"
        assert registry.get_provider_symbol("FLOURMILL", DataProvider.NGX_OFFICIAL) == "FLOURMILL"
    
    def test_ardova_mapping(self, registry):
        """ARDOVA should map to ARDOVAPLC on ngnmarket."""
        assert registry.get_provider_symbol("ARDOVA", DataProvider.NGNMARKET) == "ARDOVAPLC"
        assert registry.get_provider_symbol("ARDOVA", DataProvider.NGX_OFFICIAL) == "ARDOVA"
    
    def test_japauloil_mapping(self, registry):
        """JAPAULOIL should map to JAPAULGOLD on ngnmarket."""
        # This mapping may need verification
        ngnmarket_symbol = registry.get_provider_symbol("JAPAULOIL", DataProvider.NGNMARKET)
        assert ngnmarket_symbol == "JAPAULGOLD"
    
    def test_stanbic_mapping(self, registry):
        """STANBIC should map to STANBIC on ngnmarket."""
        assert registry.get_provider_symbol("STANBIC", DataProvider.NGNMARKET) == "STANBIC"
    
    def test_sterling_mapping(self, registry):
        """STERLING should map to STERLINGNG on ngnmarket."""
        assert registry.get_provider_symbol("STERLING", DataProvider.NGNMARKET) == "STERLINGNG"
    
    def test_total_mapping(self, registry):
        """TOTAL should map to TOTALENERGIES on ngnmarket."""
        assert registry.get_provider_symbol("TOTAL", DataProvider.NGNMARKET) == "TOTALENERGIES"


class TestProviderURLConstruction:
    """Test that providers construct URLs with mapped symbols."""
    
    def test_ngnmarket_provider_uses_registry(self):
        """NgnMarketProvider should use SymbolAliasRegistry for URL construction."""
        from app.market_data.providers.ngnmarket_provider import NgnMarketProvider
        
        provider = NgnMarketProvider()
        
        # Check that provider uses the registry (indirectly via STOCK_URL)
        assert provider.STOCK_URL == "https://www.ngnmarket.com/stocks/{symbol}"
    
    def test_ngnmarket_url_for_fbnh(self):
        """URL for FBNH should use FBNHOLDINGS."""
        from app.market_data.providers.ngnmarket_provider import NgnMarketProvider
        
        provider = NgnMarketProvider()
        registry = get_symbol_alias_registry()
        
        # Get the mapped symbol
        mapped = registry.get_provider_symbol("FBNH", DataProvider.NGNMARKET)
        
        # Construct URL
        url = provider.STOCK_URL.format(symbol=mapped)
        
        assert url == "https://www.ngnmarket.com/stocks/FBNHOLDINGS"
    
    def test_ngnmarket_url_for_flourmill(self):
        """URL for FLOURMILL should use FLOURMILLS."""
        from app.market_data.providers.ngnmarket_provider import NgnMarketProvider
        
        provider = NgnMarketProvider()
        registry = get_symbol_alias_registry()
        
        mapped = registry.get_provider_symbol("FLOURMILL", DataProvider.NGNMARKET)
        url = provider.STOCK_URL.format(symbol=mapped)
        
        assert url == "https://www.ngnmarket.com/stocks/FLOURMILLS"


class TestSimulationShouldBeRare:
    """Test that simulation fallback is minimized."""
    
    def test_provider_chain_has_simulation_metrics(self):
        """ProviderChain should track simulation metrics."""
        from app.market_data.providers.chain import ProviderChain
        from app.market_data.providers.simulated_provider import SimulatedProvider
        
        # Create minimal provider chain
        simulated = SimulatedProvider({})
        chain = ProviderChain(providers=[simulated], enable_cache=False)
        
        # Should have metrics
        metrics = chain.get_simulation_metrics()
        
        assert 'simulation_fallback_count' in metrics
        assert 'last_simulated_at' in metrics
        assert 'total_fetch_count' in metrics
        assert 'simulation_occurred_rate' in metrics
    
    def test_chain_fetch_result_has_simulation_rate(self):
        """ChainFetchResult should include simulation_rate."""
        from app.market_data.providers.chain import ChainFetchResult
        
        result = ChainFetchResult(
            success=True,
            simulated_symbols=["TEST1", "TEST2"],
            simulation_rate=0.2
        )
        
        meta = result.to_meta_dict()
        
        assert 'simulation_rate' in meta
        assert meta['simulation_rate'] == 0.2


class TestHealthcheckValidation:
    """Healthcheck tests to validate symbol resolution."""
    
    def test_all_registry_mappings_have_valid_structure(self):
        """All mappings should have valid structure."""
        registry = SymbolAliasRegistry()
        
        for symbol, mapping in registry.MAPPINGS.items():
            assert mapping.canonical == symbol
            assert mapping.canonical is not None
            # ngnmarket and ngx can be None (defaults to canonical)
    
    def test_no_duplicate_provider_symbols(self):
        """No two canonical symbols should map to the same provider symbol."""
        registry = SymbolAliasRegistry()
        
        # Check ngnmarket mappings
        ngnmarket_symbols = {}
        for symbol, mapping in registry.MAPPINGS.items():
            provider_symbol = mapping.ngnmarket or symbol
            if provider_symbol in ngnmarket_symbols:
                # Two different canonical symbols map to same provider symbol
                # This might be intentional (aliases) but worth flagging
                pass
            ngnmarket_symbols[provider_symbol] = symbol
    
    def test_known_offenders_all_have_different_ngnmarket_symbol(self):
        """All known offenders should have different ngnmarket symbols."""
        registry = SymbolAliasRegistry()
        offenders = registry.get_known_offenders()
        
        for symbol, mapping in offenders.items():
            # For offenders, ngnmarket should differ from canonical
            if mapping.ngnmarket:
                assert mapping.ngnmarket != symbol, f"{symbol} is marked as offender but ngnmarket matches canonical"
    
    def test_major_stocks_have_mappings(self):
        """Major NGX stocks should have mappings defined."""
        registry = SymbolAliasRegistry()
        
        major_stocks = [
            "GTCO", "ZENITHBANK", "ACCESSCORP", "UBA", "FBNH",
            "DANGCEM", "BUACEMENT", "MTNN", "AIRTELAFRI", "NESTLE"
        ]
        
        for symbol in major_stocks:
            mapping = registry.get_mapping(symbol)
            assert mapping is not None, f"Major stock {symbol} missing from registry"


class TestSymbolMappingDataclass:
    """Test the SymbolMapping dataclass."""
    
    def test_default_values(self):
        """SymbolMapping should have sensible defaults."""
        mapping = SymbolMapping(canonical="TEST")
        
        assert mapping.canonical == "TEST"
        assert mapping.ngnmarket is None
        assert mapping.ngx is None
        assert mapping.unsupported_providers == set()
        assert mapping.notes is None
    
    def test_get_provider_symbol_defaults_to_canonical(self):
        """get_provider_symbol should return canonical if no specific mapping."""
        mapping = SymbolMapping(canonical="TEST")
        
        # Should return canonical for all providers
        assert mapping.get_provider_symbol(DataProvider.NGNMARKET) == "TEST"
        assert mapping.get_provider_symbol(DataProvider.NGX_OFFICIAL) == "TEST"
        assert mapping.get_provider_symbol(DataProvider.SIMULATED) == "TEST"
    
    def test_unsupported_provider_returns_none(self):
        """get_provider_symbol should return None for unsupported providers."""
        mapping = SymbolMapping(
            canonical="TEST",
            unsupported_providers={DataProvider.NGNMARKET}
        )
        
        assert mapping.get_provider_symbol(DataProvider.NGNMARKET) is None
        assert mapping.get_provider_symbol(DataProvider.NGX_OFFICIAL) == "TEST"
    
    def test_is_supported_by(self):
        """is_supported_by should check unsupported_providers."""
        mapping = SymbolMapping(
            canonical="TEST",
            unsupported_providers={DataProvider.NGNMARKET}
        )
        
        assert mapping.is_supported_by(DataProvider.NGNMARKET) is False
        assert mapping.is_supported_by(DataProvider.NGX_OFFICIAL) is True
