"""Draw long pyqtgraph curves at the cost of what is on screen, not of every point.

A profit graph over a large database has one point per hand: hundreds of
thousands of points, all drawn on every repaint, zoom and pan. pyqtgraph can
instead draw only the points inside the visible x range (clip to view) and
thin them to about one per pixel column (auto downsampling). The "peak" mode
keeps each column's minimum and maximum, so a swing in the curve stays visible
however far out the view is; the data itself is untouched.

Both rely on the x values rising, which holds for curves drawn against a hand
or tournament count.

After thecrawler1's fork (thecrawler1/fpdb-3, branch ``personal``, commit
abd677c), which set both on its profit graph (#857).
"""

from __future__ import annotations

from typing import Any


def enable_large_curve_rendering(plot: Any) -> None:
    """Clip ``plot``'s curves to the view and downsample them by peaks.

    ``plot`` is a ``PlotWidget`` or its ``PlotItem``; the setting applies to
    every curve plotted on it, before or after this call.
    """
    item = plot.getPlotItem() if hasattr(plot, "getPlotItem") else plot
    item.setClipToView(True)
    item.setDownsampling(auto=True, mode="peak")
