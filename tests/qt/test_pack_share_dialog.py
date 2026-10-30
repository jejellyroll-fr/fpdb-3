"""Tools ▸ Share a HUD or pack: the window over pack_share (#449)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

import defusedxml.minidom  # noqa: E402 - after the Qt availability probe

from fpdb_3_legacy import pack_share_dialog, stat_packs  # noqa: E402
from fpdb_3_legacy.pack_share import ENTRY_NAME  # noqa: E402
from fpdb_3_legacy.pack_share_dialog import HUD, STATS, SharePackDialog, suggested_id  # noqa: E402
from tests.helpers.pack_gallery import LICENSE, stat_pack  # noqa: E402

pytestmark = pytest.mark.qt


@pytest.fixture
def messages(monkeypatch):
    """What the window told the user, without showing a modal box."""
    shown: list[tuple[str, str]] = []
    box = pack_share_dialog.QMessageBox
    monkeypatch.setattr(box, "information", lambda _parent, _title, text: shown.append(("information", text)))
    monkeypatch.setattr(box, "warning", lambda _parent, _title, text: shown.append(("warning", text)))
    return shown


@pytest.fixture
def window(qtbot, tmp_path):
    config = SimpleNamespace(
        doc=defusedxml.minidom.parseString(
            '<FreePokerToolsConfig><stat_sets><ss name="My HUD" rows="1" cols="1">'
            '<stat _rowcol="(1,1)" _stat_name="vpip"/></ss></stat_sets></FreePokerToolsConfig>'
        )
    )
    packs_dir = tmp_path / "packs"
    stat_packs.install_pack(stat_pack(tmp_path, "example.steals", version="1.2.0"), packs_dir)
    dialog = SharePackDialog(config, packs_dir=packs_dir)
    qtbot.addWidget(dialog)
    return dialog


def choose(dialog: SharePackDialog, kind: str) -> None:
    dialog.kind.setCurrentIndex(dialog.kind.findData(kind))


def test_an_id_is_suggested_from_the_author_and_the_profile_until_one_is_typed(window) -> None:
    assert suggested_id("Zoë Dupré", "My HUD!") == "zoe_dupre.my_hud"
    assert window.pack_id.text() == "yourname.my_hud"

    window.author.setText("alice")
    window.author.textEdited.emit("alice")
    assert window.pack_id.text() == "alice.my_hud"

    window.pack_id.setText("alice.special")
    window.author.textEdited.emit("bob")
    assert window.pack_id.text() == "alice.special"


def test_a_stat_pack_is_shared_under_its_own_id_and_version(window, tmp_path, messages) -> None:
    choose(window, STATS)

    assert (window.pack_id.text(), window.version.text()) == ("example.steals", "1.2.0")
    assert window.pack_id.isReadOnly() and window.version.isReadOnly()

    window.license.setText(LICENSE)
    assert window.share(tmp_path) is True

    entry = json.loads((tmp_path / "example.steals" / ENTRY_NAME).read_text(encoding="utf-8"))
    assert (entry["id"], entry["version"], entry["license"]) == ("example.steals", "1.2.0", LICENSE)
    assert messages[0][0] == "information" and "pull request" in messages[0][1]


def test_a_hud_is_written_with_what_the_window_says(window, tmp_path, messages) -> None:
    choose(window, HUD)
    window.pack_id.setText("alice.my_hud")
    window.license.setText(LICENSE)
    window.author.setText("alice")

    assert window.share(tmp_path) is True

    assert window.written == tmp_path / "alice.my_hud"
    assert (tmp_path / "alice.my_hud" / "hud" / "alice.my_hud.fpdbhud").is_file()


def test_what_the_gallery_would_refuse_is_said_and_nothing_is_written(window, tmp_path, messages) -> None:
    out = tmp_path / "out"
    out.mkdir()
    # No licence: the gallery requires one.
    assert window.share(out) is False

    assert messages and messages[0][0] == "warning" and "license is missing" in messages[0][1]
    assert list(out.iterdir()) == []
