"""Third-party widget — the universal fallback in action.

Real apps rarely stick to pysideweb's own widget set: they pull in PySide6-based
libraries from PyPI or GitHub (a plotting widget, a custom control kit, ...) that
use Qt classes pysideweb hasn't implemented. This example simulates that: a tiny
stand-in for a library like pyqtgraph, using `QGraphicsView` (unimplemented) and
`PySide6.QtCharts` (an unimplemented submodule pysideweb has never even stubbed).

Nothing here is pysideweb-aware — it's written exactly the way a third-party
library would be. Run it and watch the console: every unimplemented name gets a
one-time note instead of crashing, and the unrendered widget shows up in the
browser as a dashed placeholder box rather than disappearing or blowing up the
whole app.

    uv run python examples/third_party_widget.py

Then open http://localhost:8765.
"""

import pysideweb  # noqa: F401  Must come before any PySide6 import!

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# `PySide6.QtCharts` has no stub in pysideweb at all — pyqtgraph, PyQtChart-style
# libraries, and similar all lean on submodules like this. It still imports fine.
from PySide6.QtCharts import QChart, QLineSeries

BG = "#f4f5f7"
SURFACE = "#ffffff"
BORDER = "#dfe3e8"
TEXT = "#1a2029"
MUTED = "#697586"
ACCENT = "#3b5bdb"


class FakePlotWidget(QGraphicsView):
    """Stand-in for a third-party plotting widget (think pyqtgraph's PlotWidget).

    Subclasses an unimplemented Qt class and calls a batch of methods on it —
    `QGraphicsScene`, `setRenderHint`, `setDragMode`, `scale` — exactly like a
    real charting library would during setup. None of it is implemented by
    pysideweb; none of it raises.
    """

    def __init__(self, points):
        super().__init__()
        scene = QGraphicsScene()
        self.setScene(scene)
        self.setRenderHint(1)  # QPainter.Antialiasing, if it existed here
        self.setDragMode(QGraphicsView.ScrollHandDrag)  # a class-level constant
        self.setMinimumHeight(220)

        # A chart built the way QtCharts code normally looks. `QChart`/
        # `QLineSeries` come from the unstubbed submodule above.
        series = QLineSeries()
        for x, y in points:
            series.append(x, y)
        self.chart = QChart()
        self.chart.addSeries(series)
        self.chart.setTitle("Signal (unrendered — no QtCharts renderer yet)")
        self.scale(1.0, 1.0)


class ThirdPartyDemo(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Third-party widget demo")

        root = QWidget()
        root.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(40, 32, 40, 32)
        outer.setSpacing(16)

        title = QLabel("Third-party widget")
        title.setStyleSheet(f"color: {TEXT}; font-size: 24px; font-weight: 600;")
        subtitle = QLabel(
            "The dashed box below is a QGraphicsView-based plotting widget — "
            "unimplemented, but it didn't crash the app."
        )
        subtitle.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        self.plot = FakePlotWidget([(0, 0), (1, 3), (2, 1), (3, 4), (4, 2)])
        outer.addWidget(self.plot)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        outer.addWidget(self.status)

        poke = QPushButton("Call an unimplemented method on it")
        poke.setStyleSheet(
            f"background-color: {ACCENT}; color: #ffffff; font-size: 14px; "
            f"font-weight: 600; padding: 9px 18px; border: none; border-radius: 6px;"
        )
        poke.clicked.connect(self._poke_plot)
        outer.addWidget(poke, alignment=Qt.AlignLeft)
        outer.addStretch()

    def _poke_plot(self):
        # A method no real library would expect pysideweb to handle correctly —
        # absorbed and returns a placeholder instead of raising AttributeError.
        result = self.plot.mapToScene(10, 10)
        self.status.setText(
            f"plot.mapToScene(10, 10) -> {result!r} (no crash; see the console)"
        )
        self.status.setStyleSheet(f"color: {ACCENT}; font-size: 13px;")


def main():
    app = QApplication([])
    window = ThirdPartyDemo()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
