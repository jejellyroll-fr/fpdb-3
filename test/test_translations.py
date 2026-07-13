#!/usr/bin/env python3
"""Tests for the gettext compile chain (fpdb_3_legacy/i18n_compile.py) and the
menu translate() hook, proving translations actually load end to end.
"""

from __future__ import annotations

import builtins
import gettext
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy")))

import menu_layout

from fpdb_3_legacy import i18n_compile

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALE_DIR = REPO_ROOT / "locale"


@pytest.fixture
def _restore_gettext():
    """Restore the process-wide gettext ``_`` after a test installs a catalog."""
    saved = getattr(builtins, "_", None)
    yield
    if saved is None:
        if hasattr(builtins, "_"):
            del builtins._
    else:
        builtins._ = saved


def test_parse_po_reads_known_french_entry():
    messages = i18n_compile.parse_po(LOCALE_DIR / "fpdb-fr_FR.po")
    assert messages["Bulk Import"] == "Importation en Masse"
    assert messages["Graphs"] == "Graphiques"


def test_french_covers_new_ui_strings():
    """The menu/database strings introduced in Vague 1-2 are translated in fr."""
    messages = i18n_compile.parse_po(LOCALE_DIR / "fpdb-fr_FR.po")
    assert messages["Create database"] == "Créer la base de données"
    assert messages["Migrate to..."] == "Migrer vers…"
    assert messages["Language"] == "Langue"
    # Re-validated: was wrongly "Fichier de configuration".
    assert messages["Configure"] == "Configurer"


def test_compile_produces_a_loadable_catalog(tmp_path):
    # Stage a single .po in an isolated locale dir and compile it.
    (tmp_path / "fpdb-fr_FR.po").write_bytes((LOCALE_DIR / "fpdb-fr_FR.po").read_bytes())
    i18n_compile.compile_locale(tmp_path, "fr_FR")

    catalog = gettext.translation("fpdb", str(tmp_path), languages=["fr_FR"])
    assert catalog.gettext("Bulk Import") == "Importation en Masse"


def test_empty_translations_fall_back_to_source(tmp_path):
    """A msgid with an empty msgstr must return the English source, not ''."""
    (tmp_path / "fpdb-xx_XX.po").write_text(
        'msgid ""\nmsgstr "Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "Translated"\nmsgstr "Traduit"\n\n'
        'msgid "Cash"\nmsgstr ""\n',  # empty translation
        encoding="utf-8",
    )
    i18n_compile.compile_locale(tmp_path, "xx_XX")
    catalog = gettext.translation("fpdb", str(tmp_path), languages=["xx_XX"])
    assert catalog.gettext("Translated") == "Traduit"
    assert catalog.gettext("Cash") == "Cash"  # empty msgstr -> source, not ""


def test_parse_po_drops_empty_but_keeps_the_header(tmp_path):
    po = tmp_path / "fpdb-xx_XX.po"
    po.write_text('msgid ""\nmsgstr "X"\n\nmsgid "A"\nmsgstr ""\n\nmsgid "B"\nmsgstr "b"\n', encoding="utf-8")
    messages = i18n_compile.parse_po(po)
    assert messages == {"": "X", "B": "b"}  # empty "A" dropped, header kept


def test_ensure_compiled_is_idempotent(tmp_path):
    (tmp_path / "fpdb-fr_FR.po").write_bytes((LOCALE_DIR / "fpdb-fr_FR.po").read_bytes())

    first = i18n_compile.ensure_compiled(tmp_path)
    assert "fr_FR" in first  # compiled on the first pass
    assert (tmp_path / "fr_FR" / "LC_MESSAGES" / "fpdb.mo").exists()

    second = i18n_compile.ensure_compiled(tmp_path)
    assert second == []  # up-to-date catalog is skipped


def test_ensure_compiled_missing_dir_is_noop():
    assert i18n_compile.ensure_compiled(Path("/no/such/locale/dir")) == []


def test_available_locales_includes_core_languages():
    locales = i18n_compile.available_locales(LOCALE_DIR)
    assert {"fr_FR", "es_ES", "de_DE"}.issubset(set(locales))


def test_menu_translate_honours_installed_catalog(tmp_path, _restore_gettext):
    (tmp_path / "fpdb-fr_FR.po").write_bytes((LOCALE_DIR / "fpdb-fr_FR.po").read_bytes())
    i18n_compile.compile_locale(tmp_path, "fr_FR")

    assert menu_layout.translate("Bulk Import") == "Bulk Import"  # nothing installed yet
    gettext.translation("fpdb", str(tmp_path), languages=["fr_FR"]).install()
    assert menu_layout.translate("Bulk Import") == "Importation en Masse"
    assert menu_layout.translate("Graphs") == "Graphiques"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
