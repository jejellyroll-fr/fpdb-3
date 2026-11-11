"""The Available Stats widget: search, categories, count, activation and drag."""

from __future__ import annotations

import os

import pytest

from fpdb_3_legacy.modern_hud_preferences import stat_catalog as sc

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.qt


def _entry(origin: str, name: str, description: str, attributes=None) -> sc.CatalogEntry:
    return sc.CatalogEntry(
        key=sc.make_key(origin, name),
        name=name,
        description=description,
        category=sc.category_for(name),
        origin=origin,
        attributes=attributes or {},
    )


CATALOG = sc.StatCatalog(
    [
        _entry(sc.ORIGIN_CLASSIC, "vpip", "Voluntarily put in preflop"),
        _entry(sc.ORIGIN_CLASSIC, "pfr", "Preflop raise"),
        _entry(sc.ORIGIN_CLASSIC, "cb1", "Continuation bet flop"),
        _entry(sc.ORIGIN_CLASSIC, "fold_to_cbet_flop", "Fold to c-bet"),
        _entry(sc.ORIGIN_ANALYTICS, "fold_to_cbet_flop", "Fold to flop c-bet", {"data_source": "analytics"}),
        _entry(sc.ORIGIN_REGISTRY, "chipev_hu_sb", "ChipEV heads-up SB"),
    ]
)


@pytest.fixture
def widget(qtbot):
    from fpdb_3_legacy.modern_hud_preferences.stat_catalog_widget import StatCatalogWidget

    view = StatCatalogWidget(CATALOG)
    qtbot.addWidget(view)
    return view


def _groups(widget) -> list[tuple[str, list[str]]]:
    tree = widget.tree
    out = []
    for index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(index)
        out.append((group.text(0), [group.child(i).text(0) for i in range(group.childCount())]))
    return out


def test_the_tree_groups_stats_by_category(widget) -> None:
    assert _groups(widget) == [
        ("Preflop (2)", ["pfr", "vpip"]),
        ("Flop / 4th street (3)", ["cb1", "fold_to_cbet_flop", "fold_to_cbet_flop (analytics)"]),
        ("Tournament and stack (1)", ["chipev_hu_sb (stats.d)"]),
    ]
    assert widget.tree.topLevelItem(1).child(0).text(1) == "Continuation bet flop"
    assert widget.count_label.text() == "Showing 6 of 6 stats"
    # The full list opens with its groups closed.
    assert not widget.tree.topLevelItem(0).isExpanded()


def test_the_search_filters_and_recounts(widget) -> None:
    widget.set_filter("fold")
    assert _groups(widget) == [("Flop / 4th street (2)", ["fold_to_cbet_flop", "fold_to_cbet_flop (analytics)"])]
    assert widget.count_label.text() == "Showing 2 of 6 stats"
    assert widget.tree.topLevelItem(0).isExpanded()
    assert [entry.key for entry in widget.shown_entries()] == [
        "classic:fold_to_cbet_flop",
        "analytics:fold_to_cbet_flop",
    ]

    widget.search.setText("preflop")
    assert [name for _group, names in _groups(widget) for name in names] == ["pfr", "vpip"]

    widget.set_filter("no such stat")
    assert not _groups(widget)
    assert widget.count_label.text() == "Showing 0 of 6 stats"

    widget.set_filter("")
    assert len(widget.shown_entries()) == 6


def test_the_selection_survives_a_search_that_keeps_it(widget) -> None:
    assert widget.current_key() is None
    assert widget.select_key("classic:vpip")
    widget.set_filter("v")
    assert widget.current_key() == "classic:vpip"
    assert not widget.select_key("classic:nonexistent")


def test_a_category_row_is_not_a_stat(widget, qtbot) -> None:
    group = widget.tree.topLevelItem(0)
    widget.tree.setCurrentItem(group)
    assert widget.current_key() is None
    with qtbot.assertNotEmitted(widget.stat_activated):
        widget.tree.itemActivated.emit(group, 0)
        widget.activate_current()
    from fpdb_3_legacy.modern_hud_preferences.stat_catalog_widget import keys_from_mime

    assert not group.flags() & group.flags().ItemIsDragEnabled
    assert keys_from_mime(widget.tree.mimeData([group])) == []


def test_double_click_emits_the_key(widget, qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    widget.set_filter("chipev")
    widget.show()
    item = widget.tree.topLevelItem(0).child(0)
    rect = widget.tree.visualItemRect(item)
    assert rect.isValid()
    with qtbot.waitSignal(widget.stat_activated, timeout=1000) as blocker:
        QTest.mouseClick(widget.tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        QTest.mouseDClick(widget.tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert blocker.args == ["registry:chipev_hu_sb"]


def test_activate_current_emits_the_selected_key(widget, qtbot) -> None:
    widget.select_key("analytics:fold_to_cbet_flop")
    with qtbot.waitSignal(widget.stat_activated, timeout=1000) as blocker:
        widget.activate_current()
    assert blocker.args == ["analytics:fold_to_cbet_flop"]


def test_the_drag_carries_the_catalogue_key(widget) -> None:
    from fpdb_3_legacy.modern_hud_preferences.stat_catalog_widget import keys_from_mime

    widget.set_filter("fold")
    analytics = widget.tree.topLevelItem(0).child(1)
    assert analytics.flags() & analytics.flags().ItemIsDragEnabled
    assert widget.tree.mimeTypes() == [sc.MIME_TYPE]
    assert widget.tree.dragEnabled()

    mime = widget.tree.mimeData([analytics])
    assert mime.hasFormat(sc.MIME_TYPE)
    assert bytes(mime.data(sc.MIME_TYPE).data()) == b"analytics:fold_to_cbet_flop"
    assert keys_from_mime(mime) == ["analytics:fold_to_cbet_flop"]
    assert CATALOG.get(keys_from_mime(mime)[0]).attributes == {"data_source": "analytics"}


@pytest.mark.usefixtures("qapp")
def test_a_foreign_drop_carries_no_key() -> None:
    from PySide6.QtCore import QMimeData

    from fpdb_3_legacy.modern_hud_preferences.stat_catalog_widget import keys_from_mime, mime_data_for

    plain = QMimeData()
    plain.setText("vpip")
    assert keys_from_mime(plain) == []
    assert keys_from_mime(mime_data_for(["classic:vpip", "classic:pfr"])) == ["classic:vpip", "classic:pfr"]


def test_set_catalog_keeps_the_search(widget) -> None:
    widget.set_filter("pfr")
    widget.set_catalog(sc.StatCatalog([_entry(sc.ORIGIN_CLASSIC, "pfr", "Preflop raise")]))
    assert widget.count_label.text() == "Showing 1 of 1 stats"
    assert widget.search.text() == "pfr"


def test_without_a_catalogue_the_widget_builds_the_running_one(qtbot) -> None:
    from fpdb_3_legacy import Stats
    from fpdb_3_legacy.modern_hud_preferences.stat_catalog_widget import StatCatalogWidget

    view = StatCatalogWidget()
    qtbot.addWidget(view)
    assert len(view.catalog) >= len(Stats.get_valid_stats()) - 1
    assert len(view.shown_entries()) == len(view.catalog)
