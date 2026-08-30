"""Cross-check: run the SAME reference assertions against real PySide6.

These have no `import pysideweb` -- they load the genuine Qt binding. CI runs
this file with `pip install pyside6` and QT_QPA_PLATFORM=offscreen. If a value
pysideweb's own tests assert (in tests/test_qtcore_compat.py) is actually wrong
for real Qt, this file fails and pins down which one.

Skipped automatically when PySide6 isn't installed.
"""

import pytest

pytest.importorskip("PySide6", reason="real PySide6 not installed")

from PySide6.QtCore import QLine, QPoint, QPointF, QRect, QRectF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402


def test_color_channels():
    assert QColor("#ff8800").getRgb() == (255, 136, 0, 255)
    assert QColor("steelblue").getRgb() == (70, 130, 180, 255)
    c = QColor("#80ff0000")
    assert (c.alpha(), c.red()) == (128, 255)
    assert QColor("#ff0000") == QColor(255, 0, 0)
    assert QColor(0xFF8800).getRgb()[:3] == (255, 136, 0)
    assert QColor(255, 0, 0).name() == "#ff0000"
    assert QColor(255, 0, 0, 128).name(QColor.HexArgb) == "#80ff0000"
    assert not QColor().isValid()


def test_geometry():
    assert QPointF(1.5, 2.5).x() == 1.5
    assert (QPointF(1.5, 2.5) + QPointF(0.5, 0.5)).x() == 2.0
    assert (QPoint(3, -4)).manhattanLength() == 7
    r = QRect(0, 0, 10, 20)
    assert (r.center().x(), r.center().y()) == (4, 9)
    assert r.adjusted(1, 1, -1, -1).getRect() == (1, 1, 8, 18)
    a, b = QRect(0, 0, 10, 10), QRect(5, 5, 10, 10)
    assert a.intersected(b).getRect() == (5, 5, 5, 5)
    assert a.united(b).getRect() == (0, 0, 15, 15)
    assert QRectF(0.0, 0.0, 3.0, 4.0).center().y() == 2.0
    assert QSize(4, 9).boundedTo(QSize(6, 3)).toTuple() == (4, 3)
    assert QLine(0, 0, 3, 4).length() == 5.0


def test_enums():
    # PySide6's Qt6 enums are Python enum.Enum/Flag; use .value, not int().
    assert Qt.Key.Key_F5.value == 0x01000034
    assert Qt.Key.Key_Left.value == 0x01000012
    assert Qt.ItemDataRole.DisplayRole.value == 0
    assert Qt.ItemDataRole.UserRole.value == 256
    assert Qt.FocusPolicy.StrongFocus.value == 11
    assert Qt.KeyboardModifier.ControlModifier.value == 0x04000000
