"""Custom painting — a QWidget that draws itself with QPainter.

A small resource monitor: a circular gauge and a scrolling sparkline, both
drawn in ``paintEvent`` with ``QPainter`` primitives (arcs, a polyline, a
gradient fill, text). A ``QTimer`` feeds it new samples and calls
``update()``; PySideWeb records each frame's painter calls and replays them
on an HTML5 ``<canvas>`` in the browser.

    uv run python examples/custom_paint.py

Then open http://localhost:8765.
"""

import math
import random

import pysideweb  # noqa: F401  Must come before any PySide6 import!

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPolygon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

BG = "#0f1420"
SURFACE = "#1a2233"
ACCENT = QColor(91, 141, 239)
GOOD = QColor(66, 189, 131)
WARN = QColor(232, 168, 56)
TEXT = QColor(226, 232, 240)
MUTED = QColor(129, 140, 160)


class Gauge(QWidget):
    """A 270-degree circular gauge for a single 0..100 value."""

    def __init__(self, label: str):
        super().__init__()
        self.setFixedSize(220, 200)
        self._label = label
        self._value = 0.0

    def set_value(self, v: float):
        self._value = max(0.0, min(100.0, v))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cx, cy, r = 110, 105, 78
        start = -225 * 16          # 7:30 position, Qt uses 1/16-degree units
        full_span = 270 * 16

        # Track
        p.setPen(QPen(QColor(255, 255, 255, 28), 14, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(cx - r, cy - r, 2 * r, 2 * r, start, -full_span)

        # Value arc, colour shifting from accent to warning as it fills
        frac = self._value / 100.0
        colour = GOOD if frac < 0.6 else (ACCENT if frac < 0.85 else WARN)
        p.setPen(QPen(colour, 14, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(cx - r, cy - r, 2 * r, 2 * r, start, -int(full_span * frac))

        # Readout
        p.setPen(TEXT)
        f = p.font()
        f.setPointSize(28)
        f.setBold(True)
        p.setFont(f)
        p.drawText(cx - 60, cy - 24, 120, 44, Qt.AlignCenter, f"{self._value:.0f}")

        p.setPen(MUTED)
        f2 = p.font()
        f2.setPointSize(11)
        f2.setBold(False)
        p.setFont(f2)
        p.drawText(cx - 80, cy + 20, 160, 20, Qt.AlignCenter, "%")
        p.drawText(0, 168, 220, 20, Qt.AlignCenter, self._label)
        p.end()


class Sparkline(QWidget):
    """A scrolling history plot with a gradient area fill."""

    def __init__(self, capacity: int = 60):
        super().__init__()
        self.setFixedSize(460, 200)
        self._capacity = capacity
        self._samples: list[float] = []

    def push(self, v: float):
        self._samples.append(max(0.0, min(100.0, v)))
        if len(self._samples) > self._capacity:
            self._samples.pop(0)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = 460, 200
        pad = 12
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 10))
        p.drawRoundedRect(0, 0, w, h, 10, 10)

        # Gridlines
        p.setPen(QPen(QColor(255, 255, 255, 18), 1, Qt.DashLine))
        for i in range(1, 4):
            y = pad + (h - 2 * pad) * i / 4
            p.drawLine(pad, int(y), w - pad, int(y))

        if len(self._samples) < 2:
            p.end()
            return

        n = len(self._samples)
        step = (w - 2 * pad) / (self._capacity - 1)
        x0 = w - pad - (n - 1) * step

        def pt(i, val):
            x = x0 + i * step
            y = pad + (h - 2 * pad) * (1 - val / 100.0)
            return x, y

        # Area fill under the curve
        area = QPolygon()
        area.append(int(x0), h - pad)
        for i, val in enumerate(self._samples):
            x, y = pt(i, val)
            area.append(int(x), int(y))
        area.append(int(x0 + (n - 1) * step), h - pad)

        grad = QLinearGradient(0, pad, 0, h - pad)
        grad.setColorAt(0.0, QColor(91, 141, 239, 150))
        grad.setColorAt(1.0, QColor(91, 141, 239, 10))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPolygon(area)

        # The line itself
        line = QPolygon()
        for i, val in enumerate(self._samples):
            x, y = pt(i, val)
            line.append(int(x), int(y))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(ACCENT, 2))
        p.drawPolyline(line)

        # Last-value dot + label
        lx, ly = pt(n - 1, self._samples[-1])
        p.setPen(Qt.NoPen)
        p.setBrush(TEXT)
        p.drawEllipse(int(lx) - 4, int(ly) - 4, 8, 8)
        p.setPen(TEXT)
        p.drawText(int(lx) - 60, int(ly) - 24, 52, 18,
                   Qt.AlignRight | Qt.AlignVCenter, f"{self._samples[-1]:.0f}%")
        p.end()


class Monitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Resource Monitor")

        central = QWidget()
        central.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        title = QLabel("System load")
        title.setStyleSheet(f"color:{TEXT.name()};font-size:18px;font-weight:700;")
        outer.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(16)
        self.cpu_gauge = Gauge("CPU")
        self.mem_gauge = Gauge("Memory")
        self.spark = Sparkline()
        for card in (self.cpu_gauge, self.mem_gauge, self.spark):
            card.setStyleSheet(f"background:{SURFACE};border-radius:12px;")
        row.addWidget(self.cpu_gauge)
        row.addWidget(self.mem_gauge)
        row.addWidget(self.spark)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        self.setCentralWidget(central)

        self._cpu = 32.0
        self._mem = 58.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(700)
        self._tick()

    def _tick(self):
        self._cpu = _wander(self._cpu, spread=14, lo=4, hi=97)
        self._mem = _wander(self._mem, spread=5, lo=20, hi=92)
        self.cpu_gauge.set_value(self._cpu)
        self.mem_gauge.set_value(self._mem)
        self.spark.push(self._cpu)


def _wander(value: float, spread: float, lo: float, hi: float) -> float:
    value += random.uniform(-spread, spread) + math.sin(value / 20.0)
    return max(lo, min(hi, value))


if __name__ == "__main__":
    app = QApplication([])
    win = Monitor()
    win.resize(820, 320)
    win.show()
    app.exec()
