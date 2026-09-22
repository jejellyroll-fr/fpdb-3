"""Screen-aware sizing and reflow shared by the research tabs and HUD preferences.

Why this module exists
----------------------
The macOS report showed windows taller than the screen, with the controls at
the bottom of a form cut off, and sections compressed until their own widgets
were hidden. Two causes were common to every screen:

* a window asked for a fixed size (``setMinimumSize(1200, 800)`` followed by
  ``resize(1400, 900)``) without consulting ``QScreen.availableGeometry()``,
  which is the area left once the menu bar and the Dock are accounted for;
* a long form lived in a plain ``QVBoxLayout`` whose stretch was given to the
  rows themselves, so every field grew taller instead of the form scrolling,
  and the last rows were pushed past the bottom of the window.

The helpers below make the answers uniform across those screens: a window
opens inside the screen, a long form scrolls with its content aligned to the
top, a grid reflows to fewer columns, and a splitter changes orientation when
the width no longer fits its panes.

Nothing here reads a global: ``available`` can be passed in, which is what
makes the sizing decisions testable without a real screen.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

__all__ = [
    "SCREEN_MARGIN",
    "CollapsibleSection",
    "ReflowGrid",
    "ResponsiveSplitter",
    "available_screen_size",
    "column_count",
    "fit_window",
    "labelled_field",
    "wrap_in_scroll",
]

#: Room kept around a window for the menu bar, the Dock and window decorations.
SCREEN_MARGIN = 48

#: Below this a screen cannot show a useful window; used as the floor when the
#: reported available geometry is smaller than the margin allows for.
MIN_USABLE_WIDTH = 640
MIN_USABLE_HEIGHT = 480


def available_screen_size(widget: QWidget | None = None) -> QSize:
    """The usable area of the screen ``widget`` is on, or an empty size.

    ``QScreen.availableGeometry()`` is the area a window may occupy without
    hiding behind the menu bar or the Dock -- the measurement the fixed sizes
    this module replaces never made. An empty result means there is no screen
    to measure (headless run, or Qt not fully initialised), and callers then
    keep their preferred size rather than shrinking to nothing.
    """
    screen = None
    if widget is not None:
        try:
            screen = widget.screen()
        except (AttributeError, RuntimeError):  # pragma: no cover - defensive
            screen = None
    if screen is None:
        app = QGuiApplication.instance()
        screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return QSize()
    return screen.availableGeometry().size()


def fit_window(
    window: QWidget,
    preferred_width: int,
    preferred_height: int,
    *,
    margin: int = SCREEN_MARGIN,
    available: QSize | None = None,
) -> QSize:
    """Open ``window`` inside the screen, never larger than the screen.

    The window keeps its preferred size when the screen can hold it and is
    clamped to ``available - margin`` when it cannot. Its minimum is lowered
    to the same limit so the window manager is never told a window must be
    larger than the screen -- which is what made the dialog un-resizable on a
    laptop. Returns the size the window was resized to.
    """
    if available is None:
        available = available_screen_size(window)
    if available.isEmpty():
        window.resize(preferred_width, preferred_height)
        return QSize(preferred_width, preferred_height)

    limit_width = max(MIN_USABLE_WIDTH, available.width() - margin)
    limit_height = max(MIN_USABLE_HEIGHT, available.height() - margin)
    size = QSize(min(preferred_width, limit_width), min(preferred_height, limit_height))

    # Only an explicit minimum that cannot fit the screen is lowered. A window
    # that insists on being wider or taller than the display cannot be resized
    # at all -- which is how the reported dialog behaved. A window with no
    # explicit minimum keeps the layout's own (``minimumSizeHint``), which is
    # the honest floor for its content; raising it to the screen limit here
    # would make a small screen forbid a small window.
    explicit = window.minimumSize()
    window.setMinimumSize(min(explicit.width(), limit_width), min(explicit.height(), limit_height))
    window.resize(size)
    return size


def wrap_in_scroll(
    content: QWidget,
    *,
    horizontal: bool = False,
    frame: bool = False,
    top_aligned: bool = True,
) -> QScrollArea:
    """Put ``content`` in a scroll area that does not stretch it vertically.

    The default Qt behaviour is to resize the content to the viewport, which
    is what turned a form's rows into tall bands. Here the content keeps its
    natural height and is pinned to the top of the viewport, so a window too
    short for the form scrolls instead of compressing the fields. Horizontal
    scrolling stays off unless the caller asks for it: wrapping labels and
    forms read badly when they can be dragged sideways.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.StyledPanel if frame else QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded if horizontal else Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
    )
    if top_aligned:
        # ``Expanding`` vertically would hand the leftover room to the form
        # itself; ``Maximum`` keeps it at its natural height, top-aligned.
        content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    area.setWidget(content)
    return area


def labelled_field(label: str, widget: QWidget, muted: str) -> QWidget:
    """A field with its caption above it, so it can be reflowed in a grid.

    A ``QFormLayout`` puts the caption in a column of its own and cannot be
    re-laid out: the caption above the field is what lets the same field be
    one of four on a wide window and alone on a narrow one. The caption is
    drawn in the theme's muted colour so it reads as a caption rather than as
    another value.
    """
    box = QWidget()
    box_layout = QVBoxLayout(box)
    box_layout.setContentsMargins(0, 0, 0, 0)
    box_layout.setSpacing(2)
    caption = QLabel(label)
    caption.setStyleSheet(f"color: {muted}; font-size: 11px;")
    box_layout.addWidget(caption)
    box_layout.addWidget(widget)
    return box


def column_count(width: int, breakpoints: Sequence[tuple[int, int]], *, default: int = 1) -> int:
    """How many columns fit in ``width``.

    ``breakpoints`` is a sequence of ``(minimum_width, columns)`` pairs read in
    order, so the caller states the widths it has actually measured rather
    than a single arbitrary threshold.
    """
    for minimum_width, columns in breakpoints:
        if width >= minimum_width:
            return columns
    return default


class ReflowGrid(QGridLayout):
    """A grid of equal-width items that re-lays itself out at a given width.

    Categories and selectors are the same widget at every width; only how many
    fit on a row changes. Reflowing instead of hiding keeps every control
    reachable, which is the point of the change: the report showed sections
    whose contents had been squeezed out of view.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self._items: list[QWidget] = []
        self._columns = 0

    def items(self) -> list[QWidget]:
        return list(self._items)

    def columns(self) -> int:
        """How many columns the last reflow used; 0 before the first one."""
        return self._columns

    def set_items(self, items: Iterable[QWidget]) -> None:
        """Replace the managed items, leaving any item not passed in place."""
        self._items = [item for item in items]

    def reflow(self, columns: int) -> int:
        """Lay the items out in ``columns`` columns; returns the count used."""
        columns = max(1, int(columns))
        if columns == self._columns and self.count() == len(self._items):
            return columns
        self._columns = columns
        while self.count():
            item = self.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
        for index, widget in enumerate(self._items):
            row, column = divmod(index, columns)
            self.addWidget(widget, row, column)
        for column in range(columns):
            self.setColumnStretch(column, 1)
        for column in range(columns, self.columnCount()):
            self.setColumnStretch(column, 0)
        return columns


class ResponsiveSplitter(QSplitter):
    """A splitter that stacks its panes when the width runs out.

    Three panes side by side stop being readable before they stop fitting: at
    some width the narrowest pane is all scrollbar. Below the width the caller
    measured, the panes are stacked instead, which keeps every pane usable on
    a laptop screen. Sizes are remembered so returning to a wide window
    restores the arrangement the user had.

    ``stacked_changed`` says which of the two arrangements is in force, so a
    caller can change what it shows with it -- the research browser shows one
    stacked pane at a time, which it can only do if it knows the panes are
    stacked. The signal is emitted on a change of arrangement, not on every
    resize.
    """

    stacked_changed = Signal(bool)

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Horizontal, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._wide_orientation = orientation
        self._narrow_orientation = (
            Qt.Orientation.Vertical if orientation == Qt.Orientation.Horizontal else Qt.Orientation.Horizontal
        )
        self._narrow_below = 0
        self._wide_sizes: list[int] = []
        self._narrow_sizes: list[int] = []
        self._laid_out = False

    def narrow_below(self) -> int:
        return self._narrow_below

    def set_narrow_below(self, width: int) -> None:
        """Stack the panes whenever the splitter is narrower than ``width``."""
        self._narrow_below = max(0, int(width))
        self._apply(self._extent())

    def set_narrow_sizes(self, sizes: Sequence[int]) -> None:
        """The pane sizes to use once the panes are stacked."""
        self._narrow_sizes = [int(size) for size in sizes]

    def is_stacked(self) -> bool:
        return self.orientation() == self._narrow_orientation

    def _extent(self) -> int:
        size = self.size()
        if self._wide_orientation == Qt.Orientation.Horizontal:
            return size.width()
        return size.height()

    def resizeEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        super().resizeEvent(event)
        self._laid_out = True
        self._apply(self._extent())

    def _apply(self, extent: int) -> None:
        if not self._narrow_below:
            return
        # Before the first layout the splitter has no extent, and a zero width
        # would read as "stack the panes": the arrangement would then change
        # twice before the widget is ever seen, and a caller listening for the
        # change would be told about an arrangement that never was.
        if not self._laid_out:
            return
        stacked = extent < self._narrow_below
        wanted = self._narrow_orientation if stacked else self._wide_orientation
        if wanted == self.orientation():
            return
        if wanted == self._narrow_orientation:
            self._wide_sizes = self.sizes()
        self.setOrientation(wanted)
        if wanted == self._wide_orientation and self._wide_sizes:
            self.setSizes(self._wide_sizes)
            self._wide_sizes = []
        elif wanted == self._narrow_orientation and self._narrow_sizes:
            self.setSizes(self._narrow_sizes)
        self.stacked_changed.emit(wanted == self._narrow_orientation)


class CollapsibleSection(QWidget):
    """A titled block whose body folds away to give its room to something else.

    A landing page that lists seven context fields before the thing the reader
    came for is a page whose action is below the fold. Folding the advanced
    fields keeps them one click away while the summary in the header still
    says what is set -- a folded section must not hide that a filter is active.
    """

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        expanded: bool = True,
        tooltip: str = "",
    ) -> None:
        super().__init__(parent)
        self._toggle = QToolButton()
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setStyleSheet("QToolButton{border:none;font-weight:bold;}")
        if tooltip:
            self._toggle.setToolTip(tooltip)

        self._summary = QLabel("")
        self._summary.setStyleSheet("color: #a0aec0; font-size: 11px;")
        self._summary.setVisible(False)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self._toggle)
        header.addWidget(self._summary, 1)

        self._body = QWidget()
        self._body.setVisible(expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(header)
        layout.addWidget(self._body)

        self._toggle.toggled.connect(self._on_toggled)

    def body(self) -> QWidget:
        return self._body

    def toggle_button(self) -> QToolButton:
        return self._toggle

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.setChecked(bool(expanded))

    def set_summary(self, text: str) -> None:
        """State, next to the title, what the folded body currently holds."""
        self._summary.setText(text)
        self._summary.setVisible(bool(text))

    def summary(self) -> str:
        return self._summary.text()

    def _on_toggled(self, expanded: bool) -> None:
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._body.setVisible(expanded)
