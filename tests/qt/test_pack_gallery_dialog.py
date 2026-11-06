"""Tools ▸ Get packs: the gallery's packs listed, installed, updated and uninstalled (#449)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

import defusedxml.minidom  # noqa: E402 - after the Qt availability probe

from fpdb_3_legacy import pack_gallery_dialog  # noqa: E402
from fpdb_3_legacy.pack_gallery import read_record  # noqa: E402
from fpdb_3_legacy.pack_gallery_dialog import INSTALLED, NOT_INSTALLED, TOO_NEW, UPDATE, PackGalleryDialog  # noqa: E402
from tests.helpers.pack_gallery import build_gallery  # noqa: E402

pytestmark = pytest.mark.qt


class FakeConfig(SimpleNamespace):
    def save(self) -> None:
        self.saved += 1


def fake_config() -> FakeConfig:
    return FakeConfig(doc=defusedxml.minidom.parseString("<FreePokerToolsConfig/>"), general={}, saved=0)


@pytest.fixture
def dialog(qtbot, tmp_path):
    def make(config=None, **kwargs) -> PackGalleryDialog:
        window = PackGalleryDialog(
            config or fake_config(),
            source=str(kwargs.pop("source", tmp_path / "gallery")),
            cache_dir=tmp_path / "cache",
            record=tmp_path / "profile" / "pack-gallery.json",
            packs_dir=tmp_path / "profile" / "stat-definitions.d",
            **kwargs,
        )
        qtbot.addWidget(window)
        return window

    build_gallery(tmp_path / "gallery")
    return make


def select(window: PackGalleryDialog, pack_id: str) -> None:
    window.table.selectRow(next(i for i, row in enumerate(window.rows) if row[0].id == pack_id))


def statuses(window: PackGalleryDialog) -> dict[str, str]:
    return {entry.id: status for entry, _installed, status in window.rows}


def test_the_gallery_lists_every_pack_as_not_installed(dialog) -> None:
    window = dialog()

    assert set(statuses(window).values()) == {NOT_INSTALLED}
    assert len(window.rows) == 5 and window.table.rowCount() == 5
    assert window.install_button.isEnabled() and not window.uninstall_button.isEnabled()


def test_installing_a_hud_saves_the_configuration_and_marks_it_installed(dialog) -> None:
    config = fake_config()
    window = dialog(config)
    select(window, "fpdb-3.nlhe_6max_basic")

    assert window.install_selected() is True

    assert config.saved == 1
    assert "nlhe_6max_basic" in {node.getAttribute("name") for node in config.doc.getElementsByTagName("ss")}
    assert statuses(window)["fpdb-3.nlhe_6max_basic"] == INSTALLED
    assert "Restart fpdb" in window.notice.text()
    assert window.uninstall_button.isEnabled() and not window.install_button.isEnabled()


def test_a_newer_version_in_the_gallery_offers_an_update(dialog, tmp_path) -> None:
    config = fake_config()
    window = dialog(config)
    select(window, "example.steals")
    window.install_selected()
    index = tmp_path / "gallery" / "index.json"
    document = json.loads(index.read_text(encoding="utf-8"))
    document["packs"][0]["min_fpdb_version"] = "99.0"  # the first HUD now needs a newer fpdb
    record = tmp_path / "profile" / "pack-gallery.json"
    record.write_text(
        json.dumps(
            {"installed": {**read_record(record), "fpdb-3.nlhe_6max_advanced": {"kind": "hud", "version": "0.1"}}}
        ),
        encoding="utf-8",
    )
    index.write_text(json.dumps(document), encoding="utf-8")

    window.load()

    found = statuses(window)
    assert found["fpdb-3.nlhe_6max_basic"] == TOO_NEW
    assert found["fpdb-3.nlhe_6max_advanced"] == UPDATE
    assert found["example.steals"] == INSTALLED
    select(window, "fpdb-3.nlhe_6max_advanced")
    assert window.install_button.text() == "Update"
    select(window, "fpdb-3.nlhe_6max_basic")
    assert not window.install_button.isEnabled()


def test_a_refused_package_is_reported_and_nothing_is_saved(dialog, tmp_path, monkeypatch) -> None:
    shown = []
    monkeypatch.setattr(pack_gallery_dialog.QMessageBox, "warning", lambda _p, _t, text: shown.append(text))
    package = tmp_path / "gallery" / "hud" / "nlhe_6max_basic.fpdbhud"
    package.write_bytes(package.read_bytes().replace(b"vpip", b"vpix", 1))
    config = fake_config()
    window = dialog(config)
    select(window, "fpdb-3.nlhe_6max_basic")

    assert window.install_selected() is False

    assert config.saved == 0 and "checksum" in shown[0]


def test_a_configuration_that_cannot_be_saved_leaves_the_pack_not_installed(dialog, monkeypatch) -> None:
    # Codex (#641): the save comes before the record, inside the action's error handling.
    shown = []
    monkeypatch.setattr(pack_gallery_dialog.QMessageBox, "warning", lambda _p, _t, text: shown.append(text))
    config = fake_config()

    def full_disk() -> None:
        raise OSError("disk full")

    config.save = full_disk
    window = dialog(config)
    select(window, "fpdb-3.nlhe_6max_basic")

    assert window.install_selected() is False

    assert "disk full" in shown[0]
    assert statuses(window)["fpdb-3.nlhe_6max_basic"] == NOT_INSTALLED
    assert not config.doc.getElementsByTagName("ss")


def test_uninstalling_from_the_gallery(dialog, monkeypatch) -> None:
    config = fake_config()
    window = dialog(config)
    select(window, "fpdb-3.nlhe_6max_basic")
    window.install_selected()

    assert window.uninstall_selected(confirm=False) is True

    assert statuses(window)["fpdb-3.nlhe_6max_basic"] == NOT_INSTALLED and config.saved == 2


def test_an_unreachable_gallery_with_no_cache_says_so(dialog, tmp_path) -> None:
    window = dialog(source=tmp_path / "nowhere")

    assert window.rows == [] and "could not be read" in window.source_label.text()


def test_the_gallery_can_be_pointed_elsewhere_in_the_configuration() -> None:
    assert (
        pack_gallery_dialog.gallery_source(SimpleNamespace(general={"pack_gallery": "https://x.test/p"}))
        == "https://x.test/p"
    )
    assert pack_gallery_dialog.gallery_source(SimpleNamespace(general={})).startswith("https://")


def test_a_pack_with_a_screenshot_shows_it_and_keeps_it_for_offline(dialog, tmp_path) -> None:
    from PySide6.QtGui import QColor, QPixmap  # noqa: PLC0415

    gallery = tmp_path / "gallery"
    (gallery / "screens").mkdir()
    picture = QPixmap(40, 20)
    picture.fill(QColor("darkgreen"))
    assert picture.save(str(gallery / "screens" / "basic.png"))
    index = gallery / "index.json"
    document = json.loads(index.read_text(encoding="utf-8"))
    document["packs"][0]["screenshot"] = "screens/basic.png"
    index.write_text(json.dumps(document), encoding="utf-8")

    window = dialog()
    select(window, "fpdb-3.nlhe_6max_basic")

    assert not window.screenshot.pixmap().isNull()
    assert (tmp_path / "cache" / "screens" / "fpdb-3.nlhe_6max_basic" / "1.0.0" / "basic.png").is_file()
