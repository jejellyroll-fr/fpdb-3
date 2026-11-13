#!/usr/bin/env python
from __future__ import annotations

import html as html_lib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.stats_guide_data import GUIDE

CUSTOM_NOTE = (
    "Stat packs and stats.d files you install yourself are extensible: they are not part of this bundled list, "
    "and each one documents itself in the pack gallery."
)

ORIGIN_LABELS = {
    "native": "Native HUD stat",
    "registry": "Declarative stat (stats.d)",
    "analytics": "Analytics definition",
}

STATUS_LABELS = {
    "deprecated": "Deprecated: kept so old layouts load; it shows no data.",
    "estimate": "Estimate: not a direct count (see the note).",
    "input-missing": "An input is not selected by the HUD queries (see the note).",
}


def _meta_rows(stat: dict) -> list[tuple[str, str]]:
    """The label/value rows above a stat's description, already escaped."""

    def esc(value: object) -> str:
        return html_lib.escape(str(value))

    origin = ORIGIN_LABELS.get(stat["origin"], stat["origin"])
    rows = [
        ("Code identifier", f"<code>{esc(stat['name'])}</code>"),
        ("HUD abbreviation", esc(stat["abbr"]) or "-"),
        ("Origin", esc(origin)),
    ]
    if stat["detail_label"] and stat["detail_label"] != stat["abbr"]:
        rows.append(("Detailed HUD text", esc(stat["detail_label"])))
    if stat["description"] != stat["detail"]:
        rows.append(("HUD tooltip", esc(stat["description"])))
    if stat.get("xml_titles"):
        rows.append(("Legacy XML titles", ", ".join(esc(t) for t in stat["xml_titles"])))
    if stat.get("alias_of"):
        rows.append(("Alias of", f"<code>{esc(stat['alias_of'])}</code>"))
    rows += [(esc(label), esc(value)) for label, value in _applies_rows(stat)]
    pt4 = stat.get("pt4")
    if pt4:
        rows.append(
            ("PT4 equivalent", f"{esc(pt4['stat'])}: <code>{esc(pt4['formula'])}</code> ({esc(pt4['parity'])})")
        )
        if pt4.get("note"):
            rows.append(("PT4 difference", esc(pt4["note"])))
    if stat.get("pt4_tests"):
        rows.append(("PT4 derivation tests", ", ".join(esc(t) for t in stat["pt4_tests"])))
    return rows


BASE_LABELS = {
    "hold": "Hold'em / Omaha",
    "stud": "Stud / Razz",
    "draw": "Draw",
}


def _applies_rows(stat: dict) -> list[tuple[str, str]]:
    """Where the stat has data: the game types, then one row per game family."""
    applies = stat.get("applies") or {}
    games = applies.get("games") or ["none: the stat shows no data"]
    rows = [("Games", "; ".join(games))]
    hands = GUIDE.get("corpus", {}).get("hands", {})
    for base, label in BASE_LABELS.items():
        value = applies.get("variants", {}).get(base, "")
        if not value:
            count = sum(n for kind, n in hands.items() if kind.endswith(":" + base))
            value = (
                "no data"
                if stat["status"] in ("deprecated", "input-missing")
                else f"no data (empty on all {count} test hands)"
            )
        rows.append((label, value))
    return rows


def _grouped_stats() -> dict[str, list[dict]]:
    """The generated guide, grouped by category in the editor's order."""
    categories = GUIDE["categories"]
    grouped: dict[str, list[dict]] = {}
    for entry in GUIDE["stats"]:
        grouped.setdefault(categories.get(entry["category"], entry["category"]), []).append(entry)
    return grouped


def _matches(entry: dict, text: str) -> bool:
    haystack = " ".join(
        [
            entry["name"],
            entry["title"],
            entry["abbr"],
            entry["detail_label"],
            entry["description"],
            *entry.get("xml_titles", []),
        ]
    ).casefold()
    return all(word in haystack for word in text.casefold().split())


class GuiStatsInfo(QSplitter):
    def __init__(self, config, parent) -> None:
        super().__init__(parent)
        self.config = config
        self.parent = parent

        # Color fallbacks
        self.accent_color = "#b64fd8"
        self.fg_color = "#ffffff"

        # Left sidebar layout
        self.sidebar_widget = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget)
        self.sidebar_layout.setContentsMargins(10, 10, 10, 10)
        self.sidebar_layout.setSpacing(8)

        # Search filter field
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search statistics, abbreviations and XML titles...")
        self.search_box.textChanged.connect(self.filter_stats)
        self.sidebar_layout.addWidget(self.search_box)

        # Sidebar list widget
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("statsListWidget")
        self.list_widget.currentItemChanged.connect(self.display_stat_detail)
        self.sidebar_layout.addWidget(self.list_widget)

        self.addWidget(self.sidebar_widget)

        # Right detail area
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("filterSidebar")
        self.scroll_area.setWidgetResizable(True)

        self.statsInfoFrame = QFrame()
        self.statsInfoFrame.setObjectName("statsInfoFrame")
        self.detail_layout = QVBoxLayout(self.statsInfoFrame)
        self.detail_layout.setContentsMargins(20, 20, 20, 20)
        self.detail_layout.setSpacing(15)

        # Rich Text Browser for documentation rendering
        self.text_browser = QTextBrowser()
        self.text_browser.setObjectName("statDetailsBrowser")
        self.text_browser.setOpenExternalLinks(True)
        self.detail_layout.addWidget(self.text_browser)

        self.scroll_area.setWidget(self.statsInfoFrame)
        self.addWidget(self.scroll_area)

        # Splitter sizing
        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 3)
        self.setSizes([300, 900])

        # Initial population of stats list
        self.populate_list()

        # Select first item by default if any
        self.select_first_valid_item()

    def populate_list(self, filter_text: str = "") -> None:
        self.list_widget.clear()

        for category, stats in _grouped_stats().items():
            category_added = False
            for stat in stats:
                if filter_text and not _matches(stat, filter_text):
                    continue

                # Add category header if not added yet
                if not category_added and not filter_text:
                    header = QListWidgetItem()
                    header.setFlags(Qt.ItemFlag.NoItemFlags)
                    header.setData(Qt.ItemDataRole.UserRole, None)
                    self.list_widget.addItem(header)

                    label = QLabel(category.upper())
                    label.setStyleSheet(
                        f"color: {self.accent_color}; "
                        f"font-weight: bold; "
                        f"font-size: 12px; "
                        f"background-color: transparent; "
                        f"padding: 12px 4px 4px 4px;"
                    )
                    self.list_widget.setItemWidget(header, label)
                    header.setSizeHint(label.sizeHint())
                    category_added = True

                # The code identifier is what a layout stores; the abbreviation is what the HUD draws.
                shown = f"{stat['title']}  ({stat['name']})" if stat["title"] != stat["name"] else stat["name"]
                item = QListWidgetItem(shown if filter_text else f"  {shown}")
                item.setData(Qt.ItemDataRole.UserRole, stat)
                self.list_widget.addItem(item)

    def select_first_valid_item(self) -> None:
        if self.list_widget.count() > 0:
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.data(Qt.ItemDataRole.UserRole) is not None:
                    self.list_widget.setCurrentRow(i)
                    break

    def filter_stats(self, text: str) -> None:
        self.populate_list(text)
        self.select_first_valid_item()

    def display_stat_detail(self, current: QListWidgetItem, previous: QListWidgetItem | None = None) -> None:
        if current is None:
            self.text_browser.clear()
            return

        stat = current.data(Qt.ItemDataRole.UserRole)
        if stat is None:
            # Category header selected, ignore
            return

        def esc(value: object) -> str:
            return html_lib.escape(str(value))

        name = esc(stat["name"])
        title = esc(stat["title"])
        abbr = esc(stat["abbr"])
        meta = "".join(
            f"<tr><td style='color:#94a3b8; padding-right:14px;'>{label}</td><td>{value}</td></tr>"
            for label, value in _meta_rows(stat)
        )
        status = STATUS_LABELS.get(stat["status"])
        status_html = f"<p style='color:#f87171;'><b>{esc(status)}</b></p>" if status else ""
        note_html = f"<p style='color:#cbd5e1;'>{esc(stat['note'])}</p>" if stat["note"] else ""
        words_html = (
            f"<p style='color:#e2e8f0; font-size: 14px; margin-top: 0;'>{esc(stat['formula_words'])}</p>"
            if stat.get("formula_words")
            else ""
        )

        html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; margin: 10px;">
            <h1 style="color: #60a5fa; font-size: 24px; font-weight: bold; margin-bottom: 5px; border-bottom: 2px solid #2d3748; padding-bottom: 10px;">
                {title} <span style="color: #94a3b8; font-size: 16px; font-weight: normal;">({abbr or name})</span>
            </h1>
            <table style="margin: 10px 0;">{meta}</table>
            {status_html}

            <div style="margin: 20px 0;">
                <h3 style="color: #38bdf8; font-size: 14px; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">Description</h3>
                <p style="color: #e2e8f0; font-size: 14px; margin-top: 0;">{esc(stat["detail"])}</p>
                {note_html}
            </div>

            <div style="margin: 20px 0; background-color: #1e293b; border-left: 4px solid #10b981; border-radius: 4px; padding: 15px;">
                <h3 style="color: #10b981; font-size: 14px; font-weight: bold; text-transform: uppercase; margin-top: 0; margin-bottom: 8px; letter-spacing: 0.5px;">Formula</h3>
                {words_html}
                <code style="color: #a7f3d0; font-family: 'Courier New', Courier, monospace; font-size: 13px; font-weight: bold;">
                    {esc(stat["formula"])}
                </code>
            </div>

            <div style="margin: 20px 0; background-color: #0f172a; border-radius: 6px; padding: 15px; border: 1px solid #1e293b;">
                <h3 style="color: #f59e0b; font-size: 13px; font-weight: bold; text-transform: uppercase; margin-top: 0; margin-bottom: 8px; letter-spacing: 0.5px;">SQL Database Field / Logic</h3>
                <code style="color: #fde047; font-family: 'Courier New', Courier, monospace; font-size: 12px;">
                    {esc(stat["sql"])}
                </code>
            </div>

            <p style="color: #94a3b8; font-size: 12px;">{esc(CUSTOM_NOTE)}</p>
        </div>
        """
        self.text_browser.setHtml(html)

    def refresh_theme(self, colors: dict[str, str], theme_colors: dict[str, str]) -> None:
        """Called by ThemeManager when application theme changes."""
        bg_color = theme_colors.get("background", "#222b32")
        fg_color = theme_colors.get("foreground", "#ffffff")
        self.accent_color = colors.get("accent", "#b64fd8")
        self.fg_color = fg_color

        # Apply clean dark blue background to details browser
        self.statsInfoFrame.setStyleSheet(f"background-color: {bg_color};")
        self.text_browser.setStyleSheet(f"background-color: {bg_color}; border: 0; color: {fg_color};")

        # Apply sidebar and search colors
        self.sidebar_widget.setStyleSheet(f"background-color: {colors.get('sidebar', '#1a1e24')};")
        self.search_box.setStyleSheet(
            f"background-color: {colors.get('input', '#20262b')}; "
            f"color: {colors.get('text', '#ffffff')}; "
            f"border: 1px solid {colors.get('border', '#46505a')};"
        )
        self.list_widget.setStyleSheet(
            f"background-color: {colors.get('input', '#20262b')}; "
            f"color: {colors.get('text', '#ffffff')}; "
            f"border: 1px solid {colors.get('border', '#46505a')};"
        )

        # Repopulate list to apply the new category header colors
        current_text = self.search_box.text()
        self.populate_list(current_text)
