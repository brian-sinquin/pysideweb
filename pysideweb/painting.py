"""
pysideweb.painting — Virtual QPainter pipeline.

Real Qt renders custom widgets by calling their ``paintEvent`` with a live
``QPainter`` bound to a native surface. pysideweb has no native surface, so
instead ``QPainter`` here is a *recorder*: every ``drawLine`` / ``drawRect`` /
``drawText`` / ... call appends a small JSON command to a list. That list rides
along in the widget's serialized props (``props.paint``) and ``renderer.js``
replays it onto an HTML5 ``<canvas>`` of the same size — a "virtual painting"
pipeline.

What this means in practice:

* A ``QWidget`` subclass that overrides ``paintEvent`` renders for real in the
  browser, not as a dashed "unsupported" box.
* ``update()`` / ``repaint()`` re-run ``paintEvent`` and repaint the canvas.
* Pixel *readback* is impossible — nothing is ever rasterized on the Python
  side — so code whose logic inspects rendered pixels still can't work here.

Only the common 2D drawing surface is covered (pen/brush/font state, the
rect/ellipse/line/polygon/path/text primitives, the affine transform stack,
opacity and clipping). Anything else degrades to a no-op via ``__getattr__``,
same as the rest of pysideweb's unimplemented-API handling.
"""

from __future__ import annotations

import math
from typing import Any

from .core import (
    _GLOBAL_COLOR_RGB,
    QColor,
    QFont,
    QPoint,
    QRect,
    _AutoAttr,
    _BrushStyle,
    _PenStyle,
)

# ---------------------------------------------------------------------------
# Colour / style resolution
# ---------------------------------------------------------------------------

_PEN_STYLE_CSS = {
    0: "none",       # NoPen
    1: "solid",      # SolidLine
    2: "dash",       # DashLine
    3: "dot",        # DotLine
    4: "dashdot",    # DashDotLine
    5: "dashdotdot", # DashDotDotLine
}

_CAP_CSS = {0x00: "butt", 0x10: "square", 0x20: "round"}
_JOIN_CSS = {0x00: "miter", 0x40: "bevel", 0x80: "round"}


def _color_to_css(value: Any) -> str | None:
    """Resolve any Qt colour-ish value to a CSS colour string.

    Accepts ``QColor``, a CSS string, a ``Qt.GlobalColor`` int/enum, or an
    ``(r, g, b[, a])`` tuple. Returns ``None`` for ``None`` (meaning "no
    colour", e.g. ``Qt.NoPen`` / ``Qt.NoBrush``).
    """
    if value is None:
        return None
    if isinstance(value, QColor):
        return value.to_css()
    if isinstance(value, str):
        return value
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        r, g, b = value[0], value[1], value[2]
        a = value[3] / 255 if len(value) > 3 else 1.0
        return f"rgba({r},{g},{b},{a:.3f})"
    if isinstance(value, int):
        rgb = _GLOBAL_COLOR_RGB.get(int(value))
        if rgb is not None:
            r, g, b, a = rgb
            return f"rgba({r},{g},{b},{a / 255:.3f})"
    return None


# ---------------------------------------------------------------------------
# QPen / QBrush
# ---------------------------------------------------------------------------

class QPen:
    """Stroke description: colour, width, dash style, cap and join.

    Constructor forms mirror Qt's:
        QPen()
        QPen(QColor | Qt.GlobalColor | QBrush)
        QPen(colour, width)
        QPen(colour, width, style)
        QPen(colour, width, style, cap, join)
    """

    def __init__(self, *args):
        self._color: Any = QColor(0, 0, 0)
        self._width: float = 1.0
        self._style: int = 1  # SolidLine
        self._cap: int = 0x10  # SquareCap (Qt default)
        self._join: int = 0x00  # BevelJoin-ish; Qt default is BevelJoin(0x40) but miter reads fine

        if args:
            first = args[0]
            if isinstance(first, _PenStyle):
                # QPen(Qt.PenStyle) — a bare style, no colour.
                self._style = int(first)
            elif isinstance(first, QBrush):
                self._color = first.color()
            elif first is not None:
                # QColor | Qt.GlobalColor | CSS string — resolved at _wire().
                self._color = first
        if len(args) >= 2 and args[1] is not None:
            self._width = float(args[1])
        if len(args) >= 3 and args[2] is not None:
            self._style = int(args[2])
        if len(args) >= 4 and args[3] is not None:
            self._cap = int(args[3])
        if len(args) >= 5 and args[4] is not None:
            self._join = int(args[4])

    # -- Qt-style accessors --
    def color(self):
        return self._color

    def setColor(self, c):
        self._color = c

    def width(self) -> float:
        return self._width

    def widthF(self) -> float:
        return self._width

    def setWidth(self, w):
        self._width = float(w)

    setWidthF = setWidth

    def style(self) -> int:
        return self._style

    def setStyle(self, s):
        self._style = int(s)

    def setCapStyle(self, c):
        self._cap = int(c)

    def setJoinStyle(self, j):
        self._join = int(j)

    def capStyle(self) -> int:
        return self._cap

    def joinStyle(self) -> int:
        return self._join

    def _wire(self) -> dict:
        css = _color_to_css(self._color)
        return {
            "op": "pen",
            "color": None if self._style == 0 else css,
            "width": self._width,
            "style": _PEN_STYLE_CSS.get(self._style, "solid"),
            "cap": _CAP_CSS.get(self._cap, "square"),
            "join": _JOIN_CSS.get(self._join, "miter"),
        }

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return _AutoAttr()


class QGradient:
    """Base for the gradient types; carries the colour stops."""

    def __init__(self):
        self._stops: list[tuple[float, Any]] = []

    def setColorAt(self, pos: float, color):
        self._stops.append((float(pos), color))

    def stops(self):
        return list(self._stops)

    def _wire_stops(self):
        return [[pos, _color_to_css(c)] for pos, c in self._stops]


class QLinearGradient(QGradient):
    def __init__(self, x1=0.0, y1=0.0, x2=0.0, y2=0.0):
        super().__init__()
        # QLinearGradient(QPointF, QPointF) overload
        if hasattr(x1, "x") and hasattr(y1, "x"):
            self._x1, self._y1 = x1.x(), x1.y()
            self._x2, self._y2 = y1.x(), y1.y()
        else:
            self._x1, self._y1, self._x2, self._y2 = x1, y1, x2, y2

    def _wire(self) -> dict:
        return {
            "type": "linear",
            "x1": self._x1, "y1": self._y1, "x2": self._x2, "y2": self._y2,
            "stops": self._wire_stops(),
        }


class QRadialGradient(QGradient):
    def __init__(self, cx=0.0, cy=0.0, radius=0.0, fx=None, fy=None):
        super().__init__()
        if hasattr(cx, "x"):
            self._cx, self._cy = cx.x(), cx.y()
            self._radius = cy
        else:
            self._cx, self._cy, self._radius = cx, cy, radius
        self._fx = self._cx if fx is None else fx
        self._fy = self._cy if fy is None else fy

    def _wire(self) -> dict:
        return {
            "type": "radial",
            "cx": self._cx, "cy": self._cy, "r": self._radius,
            "fx": self._fx, "fy": self._fy,
            "stops": self._wire_stops(),
        }


class QBrush:
    """Fill description: a solid colour, ``Qt.NoBrush``, or a gradient."""

    def __init__(self, *args):
        self._color: Any = None
        self._style: int = 0  # NoBrush
        self._gradient: QGradient | None = None

        if args:
            first = args[0]
            if isinstance(first, QGradient):
                self._gradient = first
                self._style = 15  # LinearGradientPattern
            elif isinstance(first, _BrushStyle):
                # QBrush(Qt.BrushStyle) — style only (black if a fill style).
                self._style = int(first)
                if self._style not in (0,):
                    self._color = QColor(0, 0, 0)
            elif first is not None:
                self._color = first
                self._style = 1  # SolidPattern
        if len(args) >= 2 and args[1] is not None:
            self._style = int(args[1])
            if self._style == 0:
                self._color = None

    def color(self):
        return self._color if self._color is not None else QColor(0, 0, 0)

    def setColor(self, c):
        self._color = c
        if self._style == 0:
            self._style = 1

    def style(self) -> int:
        return self._style

    def setStyle(self, s):
        self._style = int(s)

    def gradient(self):
        return self._gradient

    def _wire(self) -> dict:
        if self._gradient is not None:
            return {"op": "brush", "color": None, "gradient": self._gradient._wire()}
        if self._style == 0:
            return {"op": "brush", "color": None, "gradient": None}
        return {"op": "brush", "color": _color_to_css(self._color), "gradient": None}

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return _AutoAttr()


# ---------------------------------------------------------------------------
# QPainterPath
# ---------------------------------------------------------------------------

class QPainterPath:
    """Records path segments as ``[op, *coords]`` lists for canvas replay."""

    def __init__(self, start=None):
        self._segments: list[list] = []
        self._cx = 0.0
        self._cy = 0.0
        self._start = (0.0, 0.0)
        if start is not None:
            self.moveTo(start)

    @staticmethod
    def _xy(x, y=None):
        if y is None:  # QPoint / QPointF
            return float(x.x()), float(x.y())
        return float(x), float(y)

    def moveTo(self, x, y=None):
        px, py = self._xy(x, y)
        self._segments.append(["M", px, py])
        self._cx, self._cy = px, py
        self._start = (px, py)

    def lineTo(self, x, y=None):
        px, py = self._xy(x, y)
        self._segments.append(["L", px, py])
        self._cx, self._cy = px, py

    def cubicTo(self, c1x, c1y, c2x, c2y, ex, ey):
        self._segments.append(["C", c1x, c1y, c2x, c2y, ex, ey])
        self._cx, self._cy = ex, ey

    def quadTo(self, cx, cy, ex, ey):
        self._segments.append(["Q", cx, cy, ex, ey])
        self._cx, self._cy = ex, ey

    def arcTo(self, x, y, w, h, start_angle, sweep_length):
        # Approximate an elliptical arc segment for the canvas replayer.
        self._segments.append(["A", x, y, w, h, start_angle, sweep_length])

    def addRect(self, x, y=None, w=None, h=None):
        if y is None:  # QRect / QRectF
            r = x
            x, y, w, h = r.x(), r.y(), r.width(), r.height()
        self._segments += [
            ["M", x, y], ["L", x + w, y], ["L", x + w, y + h],
            ["L", x, y + h], ["Z"],
        ]

    def addEllipse(self, x, y=None, w=None, h=None):
        if y is None:
            r = x
            x, y, w, h = r.x(), r.y(), r.width(), r.height()
        self._segments.append(["E", x, y, w, h])

    def closeSubpath(self):
        self._segments.append(["Z"])
        self._cx, self._cy = self._start

    def currentPosition(self):
        return QPoint(int(self._cx), int(self._cy))

    def _wire(self):
        return list(self._segments)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return _AutoAttr()


# ---------------------------------------------------------------------------
# QPolygon / QPolygonF
# ---------------------------------------------------------------------------

class QPolygon:
    def __init__(self, points=None):
        self._points: list[tuple[float, float]] = []
        for p in points or []:
            self.append(p)

    def append(self, p, y=None):
        if y is None:
            self._points.append((float(p.x()), float(p.y())))
        else:
            self._points.append((float(p), float(y)))

    add = append

    def __lshift__(self, p):
        self.append(p)
        return self

    def _wire(self):
        return [list(pt) for pt in self._points]

    def __iter__(self):
        return iter(QPoint(int(x), int(y)) for x, y in self._points)

    def __len__(self):
        return len(self._points)


class QPolygonF(QPolygon):
    pass


# ---------------------------------------------------------------------------
# Paint device / event
# ---------------------------------------------------------------------------

class QPaintEvent:
    def __init__(self, rect: QRect):
        self._rect = rect

    def rect(self) -> QRect:
        return self._rect

    def region(self):
        return self._rect


class QPaintDevice:
    """Minimal paint-device surface with a fixed logical size."""

    def __init__(self, width: int = 0, height: int = 0):
        self._pd_w = int(width)
        self._pd_h = int(height)

    def width(self) -> int:
        return self._pd_w

    def height(self) -> int:
        return self._pd_h

    def rect(self) -> QRect:
        return QRect(0, 0, self._pd_w, self._pd_h)


# ---------------------------------------------------------------------------
# QImage / QPixmap with a payload (data URL) for drawImage/drawPixmap
# ---------------------------------------------------------------------------

class QImage(QPaintDevice):
    """Image handle. pysideweb can't decode pixels, but it *can* carry a
    data-URL through to the browser so ``drawImage`` shows something."""

    def __init__(self, *args):
        w = h = 0
        self._src = ""
        if len(args) == 1 and isinstance(args[0], str):
            self._src = args[0]  # a path/URL; the browser resolves it
        elif len(args) >= 2 and isinstance(args[0], int):
            w, h = args[0], args[1]
        super().__init__(w, h)

    def isNull(self) -> bool:
        return not self._src and self._pd_w == 0

    def _wire_src(self) -> str:
        return self._src


class QPixmap(QImage):
    def scaled(self, *args, **kwargs):
        return self


# ---------------------------------------------------------------------------
# QPainter — the recorder
# ---------------------------------------------------------------------------

class QPainter:
    """Records drawing calls as JSON commands for canvas replay.

    Construct it with the device to paint on — a widget inside its own
    ``paintEvent`` (``QPainter(self)``), or explicitly via ``begin(device)``.
    """

    # RenderHint constants (accepted, then ignored — canvas AA is always on).
    Antialiasing = 0x01
    TextAntialiasing = 0x02
    SmoothPixmapTransform = 0x04
    HighQualityAntialiasing = 0x08

    def __init__(self, device=None):
        self._commands: list[dict] = []
        self._device = None
        self._active = False
        self._pen = QPen()
        self._brush = QBrush()
        self._font = QFont()
        if device is not None:
            self.begin(device)

    # -- lifecycle --
    def begin(self, device) -> bool:
        self._device = device
        self._active = True
        # If painting onto a widget (the usual `QPainter(self)` inside
        # paintEvent), register with it so record_widget_paint() can collect
        # what we draw once paintEvent returns.
        if getattr(device, "_wid", None) is not None and hasattr(device, "_painters"):
            device._painters.append(self)
        return True

    def end(self) -> bool:
        self._active = False
        return True

    def isActive(self) -> bool:
        return self._active

    def device(self):
        return self._device

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.end()
        return False

    # -- state --
    def setPen(self, pen):
        self._pen = pen if isinstance(pen, QPen) else QPen(pen)
        self._commands.append(self._pen._wire())

    def setBrush(self, brush):
        self._brush = brush if isinstance(brush, QBrush) else QBrush(brush)
        self._commands.append(self._brush._wire())

    def setFont(self, font: QFont):
        self._font = font
        self._commands.append({"op": "font", "css": font.to_css()})

    def pen(self):
        return self._pen

    def brush(self):
        return self._brush

    def font(self):
        return self._font

    def setRenderHint(self, *args, **kwargs):
        pass  # canvas is always antialiased

    setRenderHints = setRenderHint

    def setOpacity(self, value: float):
        self._commands.append({"op": "opacity", "value": float(value)})

    def setCompositionMode(self, mode):
        self._commands.append({"op": "composite", "mode": int(mode)})

    # -- transform stack --
    def save(self):
        self._commands.append({"op": "save"})

    def restore(self):
        self._commands.append({"op": "restore"})

    def translate(self, x, y=None):
        x, y = _pt(x, y)
        self._commands.append({"op": "translate", "x": x, "y": y})

    def rotate(self, deg: float):
        self._commands.append({"op": "rotate", "deg": float(deg)})

    def scale(self, sx: float, sy: float):
        self._commands.append({"op": "scale", "x": float(sx), "y": float(sy)})

    def shear(self, sh: float, sv: float):
        self._commands.append({"op": "shear", "x": float(sh), "y": float(sv)})

    def resetTransform(self):
        self._commands.append({"op": "resetTransform"})

    def setClipRect(self, x, y=None, w=None, h=None):
        x, y, w, h = _rect(x, y, w, h)
        self._commands.append({"op": "clipRect", "x": x, "y": y, "w": w, "h": h})

    def setClipping(self, on: bool):
        if not on:
            self._commands.append({"op": "resetClip"})

    # -- primitives --
    def drawLine(self, x1, y1=None, x2=None, y2=None):
        if y1 is None or (x2 is None and hasattr(x1, "x")):
            (x1, y1), (x2, y2) = _pt(x1), _pt(y1)
        self._commands.append({"op": "drawLine", "x1": x1, "y1": y1, "x2": x2, "y2": y2})

    def drawLines(self, lines):
        for ln in lines:
            self.drawLine(ln.x1(), ln.y1(), ln.x2(), ln.y2())

    def drawRect(self, x, y=None, w=None, h=None):
        x, y, w, h = _rect(x, y, w, h)
        self._commands.append({"op": "drawRect", "x": x, "y": y, "w": w, "h": h})

    def drawRoundedRect(self, x, y=None, w=None, h=None, xr=0, yr=0):
        if hasattr(x, "x") and y is not None and w is None:
            # drawRoundedRect(QRect, xr, yr)
            r, xr, yr = x, y, w
            x, y, w, h = r.x(), r.y(), r.width(), r.height()
        else:
            x, y, w, h = _rect(x, y, w, h)
        self._commands.append({
            "op": "drawRoundedRect", "x": x, "y": y, "w": w, "h": h,
            "rx": float(xr), "ry": float(yr),
        })

    def fillRect(self, x, y=None, w=None, h=None, color=None):
        # fillRect(QRect, color) | fillRect(x, y, w, h, color)
        if hasattr(x, "x") and y is not None and w is None:
            r, color = x, y
            x, y, w, h = r.x(), r.y(), r.width(), r.height()
        else:
            x, y, w, h = _rect(x, y, w, h)
        payload = {"op": "fillRect", "x": x, "y": y, "w": w, "h": h}
        if isinstance(color, (QBrush, QGradient)):
            br = color if isinstance(color, QBrush) else QBrush(color)
            payload["brush"] = br._wire()
        else:
            payload["color"] = _color_to_css(color)
        self._commands.append(payload)

    def eraseRect(self, x, y=None, w=None, h=None):
        x, y, w, h = _rect(x, y, w, h)
        self._commands.append({"op": "clearRect", "x": x, "y": y, "w": w, "h": h})

    def drawEllipse(self, x, y=None, w=None, h=None):
        # drawEllipse(QRect) | drawEllipse(QPoint, rx, ry) | drawEllipse(x,y,w,h)
        if hasattr(x, "x") and w is not None and h is None:
            cx, rx, ry = x, y, w
            x, y, w, h = cx.x() - rx, cx.y() - ry, 2 * rx, 2 * ry
        else:
            x, y, w, h = _rect(x, y, w, h)
        self._commands.append({"op": "drawEllipse", "x": x, "y": y, "w": w, "h": h})

    def drawArc(self, x, y=None, w=None, h=None, start_angle=0, span_angle=0):
        x, y, w, h, start_angle, span_angle = _arc_args(x, y, w, h, start_angle, span_angle)
        self._commands.append(_arc_cmd("drawArc", x, y, w, h, start_angle, span_angle))

    def drawPie(self, x, y=None, w=None, h=None, start_angle=0, span_angle=0):
        x, y, w, h, start_angle, span_angle = _arc_args(x, y, w, h, start_angle, span_angle)
        self._commands.append(_arc_cmd("drawPie", x, y, w, h, start_angle, span_angle))

    def drawChord(self, x, y=None, w=None, h=None, start_angle=0, span_angle=0):
        x, y, w, h, start_angle, span_angle = _arc_args(x, y, w, h, start_angle, span_angle)
        self._commands.append(_arc_cmd("drawChord", x, y, w, h, start_angle, span_angle))

    def drawPoint(self, x, y=None):
        x, y = _pt(x, y)
        self._commands.append({"op": "drawPoint", "x": x, "y": y})

    def drawPolyline(self, points):
        self._commands.append({"op": "drawPolyline", "pts": _points(points)})

    def drawPolygon(self, points, *args):
        self._commands.append({"op": "drawPolygon", "pts": _points(points)})

    def drawConvexPolygon(self, points, *args):
        self.drawPolygon(points)

    def drawPath(self, path: QPainterPath):
        self._commands.append({
            "op": "drawPath",
            "segments": path._wire(),
            "stroke": self._pen.style() != 0,
            "fill": self._brush.style() != 0,
        })

    def fillPath(self, path: QPainterPath, brush):
        br = brush if isinstance(brush, QBrush) else QBrush(brush)
        self._commands.append({
            "op": "drawPath", "segments": path._wire(),
            "stroke": False, "fill": True, "brush": br._wire(),
        })

    def strokePath(self, path: QPainterPath, pen):
        pn = pen if isinstance(pen, QPen) else QPen(pen)
        self._commands.append({
            "op": "drawPath", "segments": path._wire(),
            "stroke": True, "fill": False, "pen": pn._wire(),
        })

    def drawText(self, x, y=None, *rest):
        """Supported overloads:
            drawText(x, y, text)
            drawText(QPoint, text)
            drawText(QRect, flags, text)
            drawText(x, y, w, h, flags, text)
        """
        if hasattr(x, "x") and hasattr(x, "width") and rest:
            # drawText(QRect, flags, text)
            r = x
            flags = y if not isinstance(y, str) else 0
            text = rest[-1]
            self._commands.append({
                "op": "drawTextRect", "x": r.x(), "y": r.y(),
                "w": r.width(), "h": r.height(), "flags": int(flags), "text": str(text),
            })
        elif hasattr(x, "x") and not hasattr(x, "width"):
            # drawText(QPoint, text)
            self._commands.append({"op": "drawText", "x": x.x(), "y": x.y(), "text": str(y)})
        elif rest and isinstance(rest[-1], str) and len(rest) >= 3:
            # drawText(x, y, w, h, flags, text)
            w, h, flags, text = rest[0], rest[1], rest[2], rest[3]
            self._commands.append({
                "op": "drawTextRect", "x": float(x), "y": float(y),
                "w": float(w), "h": float(h), "flags": int(flags), "text": str(text),
            })
        else:
            # drawText(x, y, text)
            self._commands.append({"op": "drawText", "x": float(x), "y": float(y),
                                   "text": str(rest[0]) if rest else str(y)})

    def drawImage(self, target, image, *rest):
        self._draw_image_like("drawImage", target, image)

    def drawPixmap(self, target, pixmap, *rest):
        self._draw_image_like("drawPixmap", target, pixmap)

    def _draw_image_like(self, op, target, image):
        src = getattr(image, "_wire_src", lambda: "")()
        if hasattr(target, "width"):
            box = {"x": target.x(), "y": target.y(),
                   "w": target.width(), "h": target.height()}
        elif hasattr(target, "x"):
            box = {"x": target.x(), "y": target.y(),
                   "w": getattr(image, "width", lambda: 0)(),
                   "h": getattr(image, "height", lambda: 0)()}
        else:
            box = {"x": float(target), "y": 0, "w": 0, "h": 0}
        if not src:
            return  # nothing drawable
        self._commands.append({"op": op, "src": src, **box})

    def boundingRect(self, rect, *args) -> QRect:
        # Rough metric: no real font shaping available.
        text = args[-1] if args and isinstance(args[-1], str) else ""
        if hasattr(rect, "width"):
            return QRect(rect.x(), rect.y(),
                         min(rect.width(), len(text) * 8) or rect.width(), 16)
        return QRect(0, 0, len(text) * 8, 16)

    def fontMetrics(self):
        return _SimpleFontMetrics(self._font)

    def commands(self) -> list[dict]:
        return self._commands

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return _AutoAttr()


class _SimpleFontMetrics:
    """Coarse text metrics — no real font shaping is available server-side."""

    def __init__(self, font: QFont):
        size = font.pointSize() if font.pointSize() > 0 else font.pixelSize()
        self._px = size if size > 0 else 12

    def height(self) -> int:
        return int(self._px * 1.3)

    def ascent(self) -> int:
        return int(self._px)

    def descent(self) -> int:
        return int(self._px * 0.3)

    def horizontalAdvance(self, text: str) -> int:
        return int(len(text) * self._px * 0.55)

    width = horizontalAdvance

    def boundingRect(self, text: str) -> QRect:
        return QRect(0, 0, self.horizontalAdvance(text), self.height())


# ---------------------------------------------------------------------------
# Small arg-normalizing helpers
# ---------------------------------------------------------------------------

def _pt(x, y=None):
    if y is None and hasattr(x, "x"):
        return float(x.x()), float(x.y())
    return float(x), float(y if y is not None else 0.0)


def _rect(x, y=None, w=None, h=None):
    if y is None and hasattr(x, "width"):
        return float(x.x()), float(x.y()), float(x.width()), float(x.height())
    return float(x), float(y), float(w), float(h)


def _points(points):
    out = []
    for p in points:
        if hasattr(p, "x"):
            out.append([float(p.x()), float(p.y())])
        elif isinstance(p, (tuple, list)):
            out.append([float(p[0]), float(p[1])])
    if hasattr(points, "_wire"):
        return points._wire()
    return out


def _arc_args(x, y, w, h, start_angle, span_angle):
    if hasattr(x, "width"):
        # drawArc(QRect, startAngle, spanAngle)
        r = x
        return (float(r.x()), float(r.y()), float(r.width()), float(r.height()),
                y, w)
    return float(x), float(y), float(w), float(h), start_angle, span_angle


def _arc_cmd(op, x, y, w, h, start_angle, span_angle):
    """Convert Qt's 1/16-degree, counter-clockwise angles into canvas radians.

    Qt measures angles counter-clockwise from the 3 o'clock position in units
    of 1/16 degree. The browser canvas measures clockwise (its y-axis points
    down), so a Qt angle theta maps to canvas angle -theta.
    """
    start_deg = start_angle / 16.0
    end_deg = (start_angle + span_angle) / 16.0
    return {
        "op": op,
        "cx": x + w / 2.0, "cy": y + h / 2.0,
        "rx": w / 2.0, "ry": h / 2.0,
        "start": -math.radians(start_deg),
        "end": -math.radians(end_deg),
        "anticlockwise": span_angle > 0,
    }


# ---------------------------------------------------------------------------
# Widget integration
# ---------------------------------------------------------------------------

def widget_overrides_paint(widget) -> bool:
    from .widgets import QWidget as _QWidget

    return type(widget).paintEvent is not _QWidget.paintEvent


def record_widget_paint(widget) -> dict | None:
    """Run ``widget.paintEvent`` and collect everything its ``QPainter``(s)
    drew, as ``{"commands": [...], "w": W, "h": H}``.

    Returns ``None`` if the widget doesn't customise painting, if its
    ``paintEvent`` raised, or if it drew nothing. Called from
    ``QWidget._get_props()`` during serialization; the user's ``paintEvent``
    constructs its own ``QPainter(self)`` exactly as under real Qt, and
    ``QPainter.begin`` registers it on ``widget._painters``.
    """
    if not widget_overrides_paint(widget):
        return None

    impl = type(widget).paintEvent
    w, h = _paint_surface_size(widget)
    widget._painters = []
    try:
        impl(widget, QPaintEvent(QRect(0, 0, w, h)))
    except Exception as exc:  # a broken paintEvent shouldn't kill serialization
        print(f"[PySideWeb] paintEvent error in {type(widget).__name__}: {exc}")
        widget._painters = []
        return None

    commands: list[dict] = []
    for painter in widget._painters:
        commands.extend(painter._commands)
    widget._painters = []
    if not commands:
        return None
    return {"commands": commands, "w": w, "h": h}


def _paint_surface_size(widget) -> tuple[int, int]:
    if getattr(widget, "_fixed_size", None):
        return int(widget._fixed_size[0]), int(widget._fixed_size[1])
    geo = getattr(widget, "_geometry", (0, 0, 0, 0))
    w = geo[2] if geo[2] else 0
    h = geo[3] if geo[3] else 0
    mn = getattr(widget, "_min_size", None)
    if not w and mn is not None:
        w = mn.width()
    if not h and mn is not None:
        h = mn.height()
    return int(w or 300), int(h or 150)
