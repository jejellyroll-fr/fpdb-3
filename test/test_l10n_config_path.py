#!/usr/bin/env python3
"""Regression tests for L10n.set_locale_translation() — GitHub issue #139.

On a fresh Linux install ``~/.fpdb/HUD_config.xml`` does not exist yet, and
``set_locale_translation()`` used to crash with ``FileNotFoundError`` because
it read ``CONFIG_PATH/HUD_config.xml`` directly. It must now resolve the config
path gracefully and never crash startup.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import L10n

MINIMAL_CONFIG = '<config><general ui_language="en"></general></config>'


def test_get_translation_falls_back_without_gettext_install(monkeypatch) -> None:
    """The translation accessor remains callable before gettext is installed."""
    monkeypatch.delattr(L10n.builtins, "_", raising=False)

    assert L10n.get_translation()("unchanged") == "unchanged"


def test_get_translation_uses_gettext_installed_callable(monkeypatch) -> None:
    """The translation accessor returns the process-wide gettext function."""
    def translate(message: str) -> str:
        return f"translated:{message}"

    monkeypatch.setattr(L10n.builtins, "_", translate, raising=False)

    assert L10n.get_translation() is translate


def test_explicit_valid_config_path(tmp_path) -> None:
    """A valid explicit config path is used and does not raise."""
    cfg = tmp_path / "HUD_config.xml"
    cfg.write_text(MINIMAL_CONFIG)

    L10n.set_locale_translation(str(cfg))  # must not raise


def test_missing_config_is_graceful(tmp_path, monkeypatch) -> None:
    """A config that cannot be found is logged and skipped, not crashed on."""
    missing = tmp_path / "nope" / "HUD_config.xml"
    monkeypatch.setattr(L10n, "get_config", lambda _name: (str(missing), False, ""))

    L10n.set_locale_translation()  # FileNotFoundError must be swallowed


def test_invalid_config_xml_is_graceful(tmp_path, monkeypatch) -> None:
    """A malformed config file is logged and skipped, not crashed on."""
    bad = tmp_path / "HUD_config.xml"
    bad.write_text("<not-valid-xml")
    monkeypatch.setattr(L10n, "get_config", lambda _name: (str(bad), False, ""))

    L10n.set_locale_translation()  # ET.ParseError must be swallowed


def test_explicit_missing_path_falls_back_to_get_config(tmp_path, monkeypatch) -> None:
    """A non-existent explicit path falls back to get_config()'s resolution."""
    resolved = tmp_path / "resolved.xml"
    resolved.write_text(MINIMAL_CONFIG)
    monkeypatch.setattr(L10n, "get_config", lambda _name: (str(resolved), False, ""))

    L10n.set_locale_translation(str(tmp_path / "does-not-exist.xml"))  # must not raise


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
