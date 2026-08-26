"""
pysideweb.core — Pure-Python reimplementation of PySide6.QtCore fundamentals.

Provides Signal/Slot mechanism, Qt namespace (enums/flags), value types
(QSize, QPoint, QRect, QColor, QFont), QTimer, and QApplication.
"""

from __future__ import annotations

import inspect
import os
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from enum import IntEnum, IntFlag
from typing import Any

from . import state

# ---------------------------------------------------------------------------
# Signal / Slot
# ---------------------------------------------------------------------------

class Signal:
    """Pure-Python implementation of Qt's Signal/Slot mechanism."""

    def __init__(self, *arg_types: type):
        self._arg_types = arg_types
        self._name: str = ""
        self._owner: Any = None

    def __set_name__(self, owner: type, name: str):
        self._name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        # Return a bound signal instance
        key = f"_signal_{self._name}"
        if not hasattr(obj, key):
            bound = BoundSignal(self, obj)
            object.__setattr__(obj, key, bound)
        return object.__getattribute__(obj, key)

def _slot_arity(slot: Callable) -> tuple[bool, int]:
    """Precompute how many positional args `slot` accepts, once, at connect()
    time rather than re-running `inspect.signature()` on every single
    `emit()` -- a slot stays connected far longer than any one emit (e.g. a
    slider dragged at 60fps re-invokes the same connected slot thousands of
    times), so paying the introspection cost once per connection is strictly
    cheaper than paying it once per emission.

    Returns (accepts_all_args, max_positional_params). A callable whose
    signature can't be introspected (some builtins) is treated as accepting
    everything, matching the previous fallback behavior.
    """
    try:
        sig = inspect.signature(slot)
    except ValueError:
        return True, 0
    if any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values()):
        return True, 0
    max_params = sum(
        1 for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    )
    return False, max_params


class BoundSignal:
    """A signal bound to a specific widget instance."""

    def __init__(self, signal: Signal, owner: Any):
        self._signal = signal
        self._owner = owner
        # (slot, accepts_all_args, max_positional_params) -- see _slot_arity().
        self._slots: list[tuple[Callable, bool, int]] = []

    def connect(self, slot: Callable):
        self._slots.append((slot, *_slot_arity(slot)))

    def disconnect(self, slot: Callable | None = None):
        if slot is None:
            self._slots.clear()
        else:
            self._slots = [s for s in self._slots if s[0] is not slot]

    def emit(self, *args):
        for slot, accepts_all, max_params in self._slots[:]:  # copy: allow modification during iteration
            try:
                if accepts_all:
                    slot(*args)
                else:
                    slot(*args[:max_params])
            except Exception as e:
                print(f"[PySideWeb] Signal error in {self._signal._name}: {e}")


# ---------------------------------------------------------------------------
# Universal fallback: absorb calls to Qt API pysideweb hasn't implemented
# ---------------------------------------------------------------------------
#
# pysideweb only implements a subset of Qt. Third-party PySide6 code (e.g.
# a library found on GitHub, not just an app written directly against
# pysideweb) routinely calls methods, instantiates classes, and imports
# submodules well outside that subset. Without a fallback, any of that is a
# hard crash: an ImportError on `from PySide6.QtWidgets import <unknown>`,
# or an AttributeError the first time unimplemented-but-called method runs.
#
# _AutoAttr is a permissive "black hole" object: any attribute access or
# call on it succeeds and returns itself, so arbitrary chains like
# `obj.viewport().update()` or `obj.setSomething(1, 2).andChain()` never
# raise -- they just quietly do nothing. It's returned by
# interceptor.py's per-module fallback (for classes/constants pysideweb
# never heard of) and by QWidget.__getattr__ (for methods pysideweb hasn't
# implemented on a class it does otherwise support).
#
# Names starting with "_" are deliberately NOT absorbed -- pysideweb's own
# code relies on hasattr()/getattr(x, "_foo", None) style duck typing
# throughout (state.py walking `_widget`/`_layout`/`_wid`, widgets.py
# checking `_children`, etc.); silently answering those with a truthy
# placeholder instead of a real AttributeError would corrupt that internal
# bookkeeping. Only public, Qt-API-looking names are absorbed.

class _AutoAttrMeta(type):
    """Metaclass for placeholder classes: makes CLASS-level attribute access
    (``UnknownClass.SomeEnumMember``, looked up without an instance) permissive
    too, the same way `_AutoAttr` makes instance-level access permissive. Qt
    code constantly reaches for enum/flag constants this way (e.g.
    `QGraphicsView.ScrollHandDrag`, `QAbstractItemView.SelectRows`) -- without
    this, an unimplemented class would raise `AttributeError` the moment
    something touched one of its "class constants", even though every other
    kind of unsupported use of it degrades gracefully."""

    def __getattr__(cls, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return _AutoAttr()


class _AutoAttr(metaclass=_AutoAttrMeta):
    """Silently absorbs attribute access and calls for Qt API pysideweb
    doesn't implement, so unrecognized methods/classes degrade to a no-op
    instead of crashing the app. See the module comment above."""

    def __init__(self, *args, **kwargs):
        pass  # Accept (and ignore) any constructor signature.

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return self

    def __bool__(self):
        return False

    def __iter__(self):
        return iter(())

    def __repr__(self):
        return f"<pysideweb unimplemented: {type(self).__name__}>"


# ---------------------------------------------------------------------------
# Reflective property engine
# ---------------------------------------------------------------------------
#
# Most Qt-style properties follow the same shape: store a value and, if it
# changed, notify a listener (a widget broadcasting to the browser, or
# nothing at all for a plain value type like QFont). Instead of hand-writing
# a getter + setter + bookkeeping entry for every property on every class,
# it's declared once —
#
#     text = Prop("", notify=True)
#     value = Prop(0, notify=True, signal="valueChanged")
#
# — and a class using it (see widgets.QWidget) synthesizes the Qt-style
# `text()` / `setText(...)` methods reflectively, via __set_name__-style
# introspection, at class-creation time. The public API is unchanged:
# callers still write `label.setText(...)`, exactly as with a hand-written
# method.

class Prop:
    """Declares one Qt-style scalar property on a class that stores its
    declared values in a per-instance `self._props` dict.

    notify:   broadcast the change via state.notify_change(self._wid, ...).
              Only meaningful on classes that have a `_wid` (widgets).
    signal:   name of a Signal attribute to emit when the value actually changes.
    cast:     optional type coercion applied to incoming values (e.g. int).
    in_props: whether to include this property in _get_props(). Set to False
              for properties reported under a different key or shape.
    getter:   override the generated getter's method name — Qt uses `isFoo()`
              rather than `foo()` for several booleans (isChecked, isVisible, …).
    """

    __slots__ = ("default", "notify", "signal", "cast", "in_props", "getter_name", "name")

    def __init__(self, default=None, *, notify=False, signal=None, cast=None,
                 in_props=True, getter=None):
        self.default = default
        self.notify = notify
        self.signal = signal
        self.cast = cast
        self.in_props = in_props
        self.getter_name = getter
        self.name = None  # filled in by _register_props()


def _prop_getter(prop: Prop):
    def getter(self):
        return self._props.get(prop.name, prop.default)
    getter.__name__ = prop.getter_name or prop.name
    return getter


def _prop_setter(prop: Prop):
    def setter(self, value):
        if prop.cast is not None:
            value = prop.cast(value)
        old = self._props.get(prop.name, prop.default)
        self._props[prop.name] = value
        if prop.notify:
            state.notify_change(self._wid, prop.name, value)
        if prop.signal and value != old:
            getattr(self, prop.signal).emit(value)
        return value
    setter.__name__ = "set" + prop.name[0].upper() + prop.name[1:]
    return setter


def _register_props(cls) -> None:
    """Scan `cls`'s own namespace for Prop() declarations and synthesize
    their Qt-style getter()/setter() methods onto the class.

    The setter/alt-getter are only synthesized if no class in `cls`'s MRO —
    not just `cls` itself, but also any hand-written mixin providing custom
    logic (e.g. _RangedMixin.setValue's clamping) — already defines that
    name; `hasattr` walks the full MRO, so an inherited override is honored
    exactly like one written directly on `cls`.
    """
    declared = dict(getattr(cls, "_declared_props", {}))
    own = vars(cls)
    for attr_name, value in list(own.items()):
        if isinstance(value, Prop):
            value.name = attr_name
            declared[attr_name] = value
            setattr(cls, f"_raw_set_{attr_name}", _prop_setter(value))
            # The plain-name getter always replaces the Prop() placeholder
            # itself; if a Qt `isFoo()`-style name was requested, add that
            # too (both remain valid).
            setattr(cls, attr_name, _prop_getter(value))
            if value.getter_name and not hasattr(cls, value.getter_name):
                setattr(cls, value.getter_name, _prop_getter(value))
            qt_setter = "set" + attr_name[0].upper() + attr_name[1:]
            if not hasattr(cls, qt_setter):
                # No hand-written (or mixed-in) override -> synthesize one.
                setattr(cls, qt_setter, _prop_setter(value))
    cls._declared_props = declared


# ---------------------------------------------------------------------------
# Qt Namespace
# ---------------------------------------------------------------------------

class _AlignmentFlag(IntFlag):
    AlignLeft = 0x0001
    AlignRight = 0x0002
    AlignHCenter = 0x0004
    AlignTop = 0x0020
    AlignBottom = 0x0040
    AlignVCenter = 0x0080
    AlignCenter = AlignHCenter | AlignVCenter

class _Orientation(IntEnum):
    Horizontal = 0x1
    Vertical = 0x2

class _CheckState(IntEnum):
    Unchecked = 0
    PartiallyChecked = 1
    Checked = 2

class _ItemFlag(IntFlag):
    NoItemFlags = 0
    ItemIsSelectable = 1
    ItemIsEditable = 2
    ItemIsDragEnabled = 4
    ItemIsDropEnabled = 8
    ItemIsUserCheckable = 16
    ItemIsEnabled = 32
    ItemIsAutoTristate = 64
    ItemNeverHasChildren = 128
    ItemIsUserTristate = 256

class _ScrollBarPolicy(IntEnum):
    ScrollBarAsNeeded = 0
    ScrollBarAlwaysOff = 1
    ScrollBarAlwaysOn = 2

class _SortOrder(IntEnum):
    AscendingOrder = 0
    DescendingOrder = 1

class _WindowType(IntFlag):
    Widget = 0x00000000
    Window = 0x00000001
    Dialog = 0x00000002
    Popup = 0x00000080
    FramelessWindowHint = 0x00000800

class _SizePolicy(IntEnum):
    Fixed = 0
    Minimum = 1
    Maximum = 4
    Preferred = 5
    Expanding = 7
    MinimumExpanding = 3
    Ignored = 13

class _ToolButtonStyle(IntEnum):
    ToolButtonIconOnly = 0
    ToolButtonTextOnly = 1
    ToolButtonTextBesideIcon = 2
    ToolButtonTextUnderIcon = 3
    ToolButtonFollowStyle = 4

class _CursorShape(IntEnum):
    ArrowCursor = 0
    PointingHandCursor = 13
    WaitCursor = 3
    CrossCursor = 2
    IBeamCursor = 4

class _Key(IntEnum):
    Key_Return = 0x01000004
    Key_Enter = 0x01000005
    Key_Escape = 0x01000000
    Key_Tab = 0x01000001
    Key_Backspace = 0x01000003
    Key_Delete = 0x01000007
    Key_Space = 0x20
    Key_A = 0x41
    Key_Z = 0x5a

class Qt:
    """Namespace mirroring PySide6.QtCore.Qt.

    Every member of the enums above is exposed here under its own name
    (e.g. `_AlignmentFlag.AlignLeft` -> `Qt.AlignLeft`). Rather than
    hand-copying each one, `_export_enum` reflects over each enum class's
    members and assigns them directly on `Qt` — the two-line loop below
    replaces what used to be ~65 lines of `Foo = _FooEnum.Foo` repetition,
    and any member added to an enum class is picked up automatically.
    """

    # Text interaction (not backed by one of the enums above)
    TextSelectableByMouse = 1
    LinksAccessibleByMouse = 2
    TextBrowserInteraction = 3

    class SizePolicy:
        pass


def _export_enum(namespace: type, enum_cls: type) -> None:
    """Copy every member of `enum_cls` onto `namespace` under its own name.

    Uses `__members__` rather than iterating `enum_cls` directly: plain
    iteration of an IntFlag only yields its canonical (single-bit) members,
    silently dropping composite aliases like `AlignCenter = AlignHCenter |
    AlignVCenter`. `__members__` includes those aliases too.
    """
    for member_name, member in enum_cls.__members__.items():
        setattr(namespace, member_name, member)


for _enum_cls in (
    _AlignmentFlag, _Orientation, _CheckState, _ItemFlag, _ScrollBarPolicy,
    _SortOrder, _WindowType, _ToolButtonStyle, _CursorShape, _Key,
):
    _export_enum(Qt, _enum_cls)
_export_enum(Qt.SizePolicy, _SizePolicy)
del _enum_cls

# ---------------------------------------------------------------------------
# Value Types
# ---------------------------------------------------------------------------

class QSize:
    def __init__(self, w: int = -1, h: int = -1):
        self._w = w
        self._h = h

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h

    def setWidth(self, w: int):
        self._w = w

    def setHeight(self, h: int):
        self._h = h

    def toTuple(self):
        return (self._w, self._h)

    def __repr__(self):
        return f"QSize({self._w}, {self._h})"

class QPoint:
    def __init__(self, x: int = 0, y: int = 0):
        self._x = x
        self._y = y

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def __repr__(self):
        return f"QPoint({self._x}, {self._y})"

class QRect:
    def __init__(self, x: int = 0, y: int = 0, w: int = 0, h: int = 0):
        self._x = x
        self._y = y
        self._w = w
        self._h = h

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h

    def __repr__(self):
        return f"QRect({self._x}, {self._y}, {self._w}, {self._h})"

class QColor:
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], str):
            self._name = args[0]
            self._r = self._g = self._b = self._a = 0
        elif len(args) >= 3:
            self._r, self._g, self._b = args[0], args[1], args[2]
            self._a = args[3] if len(args) > 3 else 255
            self._name = f"rgba({self._r},{self._g},{self._b},{self._a/255:.2f})"
        else:
            self._r = self._g = self._b = 0
            self._a = 255
            self._name = "#000000"

    def name(self) -> str:
        return self._name

    def red(self) -> int: return self._r
    def green(self) -> int: return self._g
    def blue(self) -> int: return self._b
    def alpha(self) -> int: return self._a

    def __repr__(self):
        return f"QColor('{self._name}')"

class QFont:
    family = Prop("")
    pointSize = Prop(-1)
    pixelSize = Prop(-1)
    italic = Prop(False)
    weight = Prop(400)
    underline = Prop(False)

    def __init__(self, family: str = "", size: int = -1):
        self._props: dict = {name: p.default for name, p in self._declared_props.items()}
        self._props["family"] = family
        self._props["pointSize"] = size
        self._bold = False

    def bold(self) -> bool:
        return self._bold

    def setBold(self, bold: bool):
        self._bold = bold
        self.setWeight(700 if bold else 400)

    def to_css(self) -> dict:
        css = {}
        if self.family():
            css["fontFamily"] = self.family()
        if self.pointSize() > 0:
            css["fontSize"] = f"{self.pointSize()}pt"
        if self.pixelSize() > 0:
            css["fontSize"] = f"{self.pixelSize()}px"
        if self._bold:
            css["fontWeight"] = "bold"
        if self.italic():
            css["fontStyle"] = "italic"
        if self.underline():
            css["textDecoration"] = "underline"
        return css

    def __repr__(self):
        return f"QFont('{self.family()}', {self.pointSize()})"


_register_props(QFont)

class QIcon:
    """Minimal QIcon stub — stores an emoji or text icon."""
    def __init__(self, icon_text: str = ""):
        self._text = icon_text

    def text(self) -> str:
        return self._text

    def isNull(self) -> bool:
        return not self._text

    def __repr__(self):
        return f"QIcon('{self._text}')"

class QPixmap:
    """Minimal QPixmap stub."""
    def __init__(self, *args):
        self._width = 0
        self._height = 0
        if len(args) == 2:
            self._width = args[0]
            self._height = args[1]

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def isNull(self) -> bool:
        return self._width == 0 and self._height == 0

    def scaled(self, *args, **kwargs):
        return self

class QMargins:
    def __init__(self, left: int = 0, top: int = 0, right: int = 0, bottom: int = 0):
        self._left = left
        self._top = top
        self._right = right
        self._bottom = bottom

    def left(self) -> int: return self._left
    def top(self) -> int: return self._top
    def right(self) -> int: return self._right
    def bottom(self) -> int: return self._bottom

# ---------------------------------------------------------------------------
# QTimer
# ---------------------------------------------------------------------------

class QTimer:
    """Virtual QTimer using threading."""

    timeout = Signal()

    def __init__(self, parent=None):
        self._interval = 0
        self._single_shot = False
        self._running = False
        self._thread: threading.Timer | None = None
        self._parent = parent

    def setInterval(self, msec: int):
        self._interval = msec

    def interval(self) -> int:
        return self._interval

    def setSingleShot(self, single: bool):
        self._single_shot = single

    def isSingleShot(self) -> bool:
        return self._single_shot

    def start(self, msec: int | None = None):
        if msec is not None:
            self._interval = msec
        self._running = True
        self._schedule()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.cancel()
            self._thread = None

    def isActive(self) -> bool:
        return self._running

    def _schedule(self):
        if not self._running:
            return
        self._thread = threading.Timer(
            self._interval / 1000.0, self._fire
        )
        self._thread.daemon = True
        self._thread.start()

    def _fire(self):
        if not self._running:
            return
        self.timeout.emit()
        if not self._single_shot and self._running:
            self._schedule()

    @staticmethod
    def singleShot(msec: int, slot: Callable):
        t = QTimer()
        t.setSingleShot(True)
        t.timeout.connect(slot)
        t.start(msec)

# ---------------------------------------------------------------------------
# QApplication
# ---------------------------------------------------------------------------

class QApplication:
    """Virtual QApplication — starts the web server and blocks on exec()."""

    _instance: QApplication | None = None

    def __init__(self, argv: list[str] | None = None):
        QApplication._instance = self
        self._argv = argv or sys.argv
        self._windows: list = []

    @staticmethod
    def instance():
        return QApplication._instance

    def exec(self) -> int:
        return self.exec_()

    def exec_(self) -> int:
        from . import server as srv
        port = int(os.environ.get("PYSIDEWEB_PORT", "8765"))
        srv.ensure_server_running(port)

        # Open browser
        url = f"http://localhost:{port}"
        print(f"\n{'='*50}")
        print(f"  PySideWeb running at: {url}")
        print("  Press Ctrl+C to quit")
        print(f"{'='*50}\n")
        webbrowser.open(url)

        # Block until Ctrl+C
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[PySideWeb] Shutting down...")
            return 0

    @staticmethod
    def processEvents():
        pass  # no-op in web mode

    @staticmethod
    def quit():
        sys.exit(0)

    def setStyle(self, style):
        pass  # ignore

    def setApplicationName(self, name: str):
        pass

    def setWindowIcon(self, icon):
        pass

    def setApplicationDisplayName(self, name: str):
        pass
