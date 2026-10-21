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


def test_parse_po_ignores_orphan_continuation(tmp_path):
    po = tmp_path / "fpdb-xx_XX.po"
    po.write_text('"orphan"\nmsgid "A"\nmsgstr "a"\n', encoding="utf-8")

    assert i18n_compile.parse_po(po) == {"A": "a"}


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


FUZZY_PO = (
    'msgid ""\nmsgstr "Content-Type: text/plain; charset=UTF-8\\n"\n\n'
    'msgid "Checked"\nmsgstr "Checké"\n\n'
    "#, fuzzy, python-format\n"
    "#| msgid \"Mucked\"\n"
    'msgid "Folded"\nmsgstr "Dossier"\n\n'
    'msgid "Invert"\nmsgstr ""\n\n'
    '#~ msgid "Gone"\n#~ msgstr "Parti"\n'
)


def test_a_fuzzy_translation_is_not_shown(tmp_path):
    """msgmerge marks a guess from a similar string fuzzy: like msgfmt, it is left out (#444)."""
    po = tmp_path / "fpdb-xx_XX.po"
    po.write_text(FUZZY_PO, encoding="utf-8")

    messages = i18n_compile.parse_po(po)

    assert messages.get("Checked") == "Checké"
    assert "Folded" not in messages
    assert "Invert" not in messages
    assert "Gone" not in messages, "an obsolete entry is not a translation"


def test_completion_counts_what_is_shown(tmp_path):
    po = tmp_path / "fpdb-xx_XX.po"
    po.write_text(FUZZY_PO, encoding="utf-8")

    assert i18n_compile.completion(po) == (1, 3)


def test_the_french_catalogue_has_no_fuzzy_entry_left():
    """Its fuzzy entries were reviewed when the catalogues were merged with the source (#444)."""
    fuzzy = [entry.msgid for entry in i18n_compile.read_entries(LOCALE_DIR / "fpdb-fr_FR.po") if entry.fuzzy]

    assert fuzzy == []


@pytest.mark.parametrize(
    ("completion", "label"),
    [((611, 1275), "Français (47 %)"), ((0, 1275), "Français (0 %)"), (None, "Français"), ((0, 0), "Français")],
)
def test_the_language_menu_shows_completion(completion, label):
    assert menu_layout.language_label("Français", completion) == label


@pytest.mark.skipif(not all(map(__import__("shutil").which, ("xgettext", "msgmerge"))), reason="GNU gettext missing")
def test_the_catalogues_are_merged_with_the_source():
    """What CI runs: locale/fpdb.pot and every catalogue follow the source (#444)."""
    from tools import update_pot

    assert update_pot.check() == 0


@pytest.mark.skipif(not all(map(__import__("shutil").which, ("xgettext", "msgmerge"))), reason="GNU gettext missing")
def test_a_catalogue_that_lags_the_template_is_reported(tmp_path, monkeypatch):
    from tools import update_pot

    locale = tmp_path / "locale"
    locale.mkdir()
    (locale / "fpdb.pot").write_bytes((LOCALE_DIR / "fpdb.pot").read_bytes())
    lagging = (LOCALE_DIR / "fpdb-de_DE.po").read_text(encoding="utf-8")
    lagging = lagging.replace('msgid "Configure"\n', 'msgid "Configure the past"\n', 1)
    (locale / "fpdb-de_DE.po").write_text(lagging, encoding="utf-8")
    monkeypatch.setattr(update_pot, "LOCALE", locale)
    monkeypatch.setattr(update_pot, "POT", locale / "fpdb.pot")

    assert update_pot.check() == 1


@pytest.mark.skipif(not __import__("shutil").which("msgmerge"), reason="GNU gettext missing")
def test_a_new_source_string_missing_from_the_template_is_reported(monkeypatch, capsys):
    from tools import update_pot

    strings = update_pot.source_strings()
    monkeypatch.setattr(update_pot, "source_strings", lambda: strings | {"A string nobody merged"})

    assert update_pot.check() == 1
    assert "'A string nobody merged'" in capsys.readouterr().out
