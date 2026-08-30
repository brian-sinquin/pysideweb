"""Tests for the virtual QPainter pipeline (pysideweb/painting.py)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygon,
)
from PySide6.QtWidgets import QWidget

from pysideweb import state


def _paint_of(widget) -> dict:
    tree = state.serialize_widget(widget)
    return tree["props"].get("paint")


class _Custom(QWidget):
    def __init__(self, draw):
        super().__init__()
        self.setFixedSize(120, 80)
        self._draw = draw

    def paintEvent(self, event):
        p = QPainter(self)
        self._draw(p)
        p.end()


class TestRecording:
    def test_plain_widget_has_no_paint_prop(self):
        w = QWidget()
        w.show()
        assert _paint_of(w) is None

    def test_overridden_paintevent_is_recorded(self):
        w = _Custom(lambda p: p.drawRect(0, 0, 10, 10))
        w.show()
        paint = _paint_of(w)
        assert paint is not None
        assert paint["w"] == 120 and paint["h"] == 80
        ops = [c["op"] for c in paint["commands"]]
        assert "drawRect" in ops

    def test_paintevent_drawing_nothing_yields_no_prop(self):
        w = _Custom(lambda p: None)
        w.show()
        assert _paint_of(w) is None

    def test_broken_paintevent_does_not_break_serialization(self):
        def boom(p):
            raise RuntimeError("kaboom")

        w = _Custom(boom)
        w.show()
        assert _paint_of(w) is None  # swallowed, not raised

    def test_update_reflects_new_drawing(self):
        state_box = {"n": 3}
        w = _Custom(lambda p: p.drawText(1, 1, f"n={state_box['n']}"))
        w.show()
        assert _paint_of(w)["commands"][-1]["text"] == "n=3"
        state_box["n"] = 7
        assert _paint_of(w)["commands"][-1]["text"] == "n=7"


class TestPenBrush:
    def test_pen_color_width_style(self):
        w = _Custom(lambda p: (
            p.setPen(QPen(QColor(10, 20, 30), 4, Qt.DashLine)),
            p.drawLine(0, 0, 5, 5),
        ))
        w.show()
        pens = [c for c in _paint_of(w)["commands"] if c["op"] == "pen"]
        last = pens[-1]
        assert last["color"] == "rgba(10,20,30,1.000)"
        assert last["width"] == 4
        assert last["style"] == "dash"

    def test_no_pen_disables_stroke(self):
        w = _Custom(lambda p: (p.setPen(Qt.NoPen), p.drawRect(0, 0, 1, 1)))
        w.show()
        last_pen = [c for c in _paint_of(w)["commands"] if c["op"] == "pen"][-1]
        assert last_pen["color"] is None

    def test_global_color_pen(self):
        w = _Custom(lambda p: (p.setPen(Qt.red), p.drawPoint(1, 1)))
        w.show()
        last_pen = [c for c in _paint_of(w)["commands"] if c["op"] == "pen"][-1]
        assert last_pen["color"] == "rgba(255,0,0,1.000)"

    def test_brush_solid_and_nobrush(self):
        w = _Custom(lambda p: (
            p.setBrush(QColor(1, 2, 3)),
            p.drawRect(0, 0, 2, 2),
            p.setBrush(Qt.NoBrush),
            p.drawRect(0, 0, 2, 2),
        ))
        w.show()
        brushes = [c for c in _paint_of(w)["commands"] if c["op"] == "brush"]
        assert brushes[-2]["color"] == "rgba(1,2,3,1.000)"
        assert brushes[-1]["color"] is None

    def test_linear_gradient_brush(self):
        def draw(p):
            g = QLinearGradient(0, 0, 100, 0)
            g.setColorAt(0.0, QColor(255, 0, 0))
            g.setColorAt(1.0, Qt.blue)
            p.setBrush(QBrush(g))
            p.drawRect(0, 0, 100, 10)

        w = _Custom(draw)
        w.show()
        grad = [c for c in _paint_of(w)["commands"] if c["op"] == "brush"][-1]["gradient"]
        assert grad["type"] == "linear"
        assert grad["stops"][0] == [0.0, "rgba(255,0,0,1.000)"]
        assert grad["stops"][1][1] == "rgba(0,0,255,1.000)"


class TestPrimitives:
    def test_arc_angle_conversion(self):
        # Qt: 90 degrees == 1440 sixteenths, counter-clockwise.
        w = _Custom(lambda p: p.drawArc(0, 0, 40, 40, 0, 1440))
        w.show()
        arc = [c for c in _paint_of(w)["commands"] if c["op"] == "drawArc"][0]
        assert arc["cx"] == 20 and arc["cy"] == 20
        assert arc["start"] == 0.0
        assert abs(arc["end"] - (-3.14159265 / 2)) < 1e-6
        assert arc["anticlockwise"] is True

    def test_path_segments(self):
        def draw(p):
            path = QPainterPath()
            path.moveTo(0, 0)
            path.lineTo(10, 0)
            path.cubicTo(10, 5, 5, 10, 0, 10)
            path.closeSubpath()
            p.drawPath(path)

        w = _Custom(draw)
        w.show()
        seg = [c for c in _paint_of(w)["commands"] if c["op"] == "drawPath"][0]["segments"]
        assert seg[0] == ["M", 0.0, 0.0]
        assert seg[2][0] == "C"
        assert seg[-1] == ["Z"]

    def test_polygon(self):
        def draw(p):
            poly = QPolygon([_P(0, 0), _P(10, 0), _P(5, 8)])
            p.drawPolygon(poly)

        w = _Custom(draw)
        w.show()
        cmd = [c for c in _paint_of(w)["commands"] if c["op"] == "drawPolygon"][0]
        assert cmd["pts"] == [[0.0, 0.0], [10.0, 0.0], [5.0, 8.0]]

    def test_drawtext_rect_overload(self):
        w = _Custom(lambda p: p.drawText(_R(0, 0, 50, 20), Qt.AlignCenter, "hi"))
        w.show()
        cmd = [c for c in _paint_of(w)["commands"] if c["op"] == "drawTextRect"][0]
        assert cmd["text"] == "hi" and cmd["w"] == 50

    def test_fillrect_explicit_color(self):
        w = _Custom(lambda p: p.fillRect(_R(0, 0, 5, 5), QColor(9, 9, 9)))
        w.show()
        cmd = [c for c in _paint_of(w)["commands"] if c["op"] == "fillRect"][0]
        assert cmd["color"] == "rgba(9,9,9,1.000)"


class TestCompositionAndOpacity:
    def test_composition_mode_recorded(self):
        from PySide6.QtGui import QPainter as _QP

        w = _Custom(lambda p: (
            p.setCompositionMode(_QP.CompositionMode_Multiply),
            p.drawRect(0, 0, 5, 5),
        ))
        w.show()
        cmd = [c for c in _paint_of(w)["commands"] if c["op"] == "composite"][0]
        assert cmd["mode"] == _QP.CompositionMode_Multiply

    def test_opacity_recorded(self):
        w = _Custom(lambda p: (p.setOpacity(0.4), p.drawRect(0, 0, 5, 5)))
        w.show()
        cmd = [c for c in _paint_of(w)["commands"] if c["op"] == "opacity"][0]
        assert cmd["value"] == 0.4


class TestImagePayload:
    def test_qimage_reads_file_as_data_url(self, tmp_path):
        from PySide6.QtGui import QImage

        png = tmp_path / "x.png"
        # 1x1 transparent PNG
        png.write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6300010000050001a5f645400000000049454e44ae"
            "426082"
        ))
        img = QImage(str(png))
        assert img._wire_src().startswith("data:image/png;base64,")

        w = _Custom(lambda p: p.drawImage(_R(0, 0, 10, 10), QImage(str(png))))
        w.show()
        cmd = [c for c in _paint_of(w)["commands"] if c["op"] == "drawImage"][0]
        assert cmd["src"].startswith("data:image/png;base64,")

    def test_missing_file_kept_verbatim_not_crash(self):
        from PySide6.QtGui import QImage

        img = QImage("does/not/exist.png")
        assert img._wire_src() == "does/not/exist.png"

    def test_url_passed_through(self):
        from PySide6.QtGui import QPixmap

        assert QPixmap("https://example.com/a.png")._wire_src() == "https://example.com/a.png"


class TestFontMetrics:
    def test_width_scales_with_size_and_text(self):
        from PySide6.QtGui import QFont, QFontMetrics

        fm12 = QFontMetrics(QFont("Arial", 12))
        fm24 = QFontMetrics(QFont("Arial", 24))
        assert fm24.horizontalAdvance("hello") > fm12.horizontalAdvance("hello")
        assert fm12.horizontalAdvance("mmmm") > fm12.horizontalAdvance("iiii")
        assert fm12.height() > 0 and fm12.ascent() > fm12.descent()

    def test_elided_text(self):
        from PySide6.QtGui import QFont, QFontMetrics

        fm = QFontMetrics(QFont("Arial", 12))
        full = "a fairly long label that will not fit"
        out = fm.elidedText(full, 0, 40)
        assert out.endswith("…") and len(out) < len(full)


class TestGraceful:
    def test_unknown_painter_method_is_noop(self):
        w = _Custom(lambda p: p.drawSomethingExotic(1, 2, 3))
        w.show()
        # No crash; nothing recorded for the unknown call.
        assert _paint_of(w) is None


# -- tiny local helpers so the tests don't depend on QtCore point/rect shape --

class _P:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


class _R:
    def __init__(self, x, y, w, h):
        self._x, self._y, self._w, self._h = x, y, w, h

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._w

    def height(self):
        return self._h
