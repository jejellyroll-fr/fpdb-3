#!/usr/bin/env python3
"""Regression test: converter modules import correctly from the fpdb_3_legacy package.

The legacy importer used bare-name ``__import__("PokerStarsToFpdb")`` calls,
which broke after the migration into the ``fpdb_3_legacy`` package — IdentifySite
loaded zero sites ("Could not find module ..., skipping"). They now resolve via
``import_fpdb_module()``, which imports the package-qualified module.
"""


import pytest

import fpdb_3_legacy.Configuration as Configuration
from fpdb_3_legacy.IdentifySite import IdentifySite, import_fpdb_module
from fpdb_3_legacy.parser_registry import get_parser_class, get_summary_class


def test_import_fpdb_module_resolves_converter() -> None:
    """import_fpdb_module() returns the converter module itself, not the package."""
    mod = import_fpdb_module("PokerStarsToFpdb")
    assert hasattr(mod, "PokerStars")


def test_import_fpdb_module_resolves_summary() -> None:
    mod = import_fpdb_module("PokerStarsSummary")
    assert hasattr(mod, "PokerStarsSummary")


def test_import_fpdb_module_unknown_raises() -> None:
    with pytest.raises(ModuleNotFoundError):
        import_fpdb_module("DefinitelyNotAConverter")


def test_import_fpdb_module_rejects_non_module_names() -> None:
    with pytest.raises(ModuleNotFoundError, match="Unsupported fpdb module name"):
        import_fpdb_module("../PokerStarsToFpdb")


def test_typed_registries_resolve_parser_and_summary_classes() -> None:
    assert get_parser_class("PokerStars").__name__ == "PokerStars"
    assert get_summary_class("BovadaSummary").__name__ == "BovadaSummary"


def test_typed_registries_report_unknown_names() -> None:
    with pytest.raises(KeyError, match="Unknown parser filter_name"):
        get_parser_class("MissingRoom")
    with pytest.raises(KeyError, match="Unknown summary importer"):
        get_summary_class("MissingSummary")


def test_identify_site_loads_converters() -> None:
    """IdentifySite must load the bundled site converters (was 0 before the fix)."""
    ids = IdentifySite(Configuration.Config())

    assert len(ids.sitelist) >= 10
    # sitelist is keyed by the converter's site_id, so every site sharing a
    # converter (e.g. all PokerStars skins, the whole iPoker/PartyPoker network)
    # collapses to a single entry whose display name is the last one configured.
    # Assert on the loaded converter (filter_name), which is stable, rather than
    # on whichever skin's display name happened to survive.
    converters = {site.filter_name for site in ids.sitelist.values()}
    assert "PokerStars" in converters
    assert "Winamax" in converters
    # PokerTracker identification regexes are loaded separately.
    assert ids.re_Identify_PT is not None
    assert ids.re_SumIdentify_PT is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
