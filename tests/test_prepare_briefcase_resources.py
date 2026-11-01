"""Packaging contracts for generated Briefcase translation resources."""

import gettext
from pathlib import Path

from tools.prepare_briefcase_resources import prepare_resources


def test_prepare_resources_preserves_gettext_locale_layout(tmp_path: Path) -> None:
    locale_dir = tmp_path / "source-locale"
    locale_dir.mkdir()
    (locale_dir / "fpdb-fr_FR.po").write_text(
        'msgid ""\nmsgstr "Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "Hello"\nmsgstr "Bonjour"\n',
        encoding="utf-8",
    )
    output_root = tmp_path / "briefcase"

    outputs = prepare_resources(locale_dir, output_root)

    assert outputs == [output_root / "locale" / "fr_FR" / "LC_MESSAGES" / "fpdb.mo"]
    with outputs[0].open("rb") as handle:
        assert gettext.GNUTranslations(handle).gettext("Hello") == "Bonjour"


def test_prepare_resources_replaces_stale_generated_tree(tmp_path: Path) -> None:
    locale_dir = tmp_path / "source-locale"
    locale_dir.mkdir()
    (locale_dir / "fpdb-es_ES.po").write_text('msgid "Hello"\nmsgstr "Hola"\n', encoding="utf-8")
    output_root = tmp_path / "briefcase"
    stale = output_root / "stale.txt"
    stale.parent.mkdir()
    stale.write_text("obsolete", encoding="utf-8")

    outputs = prepare_resources(locale_dir, output_root)

    assert not stale.exists()
    assert len(outputs) == 1
