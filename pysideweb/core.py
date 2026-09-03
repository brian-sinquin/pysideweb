"""
pysideweb.core — Pure-Python reimplementation of PySide6.QtCore fundamentals.

Provides Signal/Slot mechanism, Qt namespace (enums/flags), value types
(QSize, QPoint, QRect, QColor, QFont), QTimer, and QApplication.
"""

from __future__ import annotations

import heapq
import inspect
import itertools
import os
import sys
import threading
import time
import weakref
import webbrowser
from collections.abc import Callable
from contextvars import ContextVar
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
    except (TypeError, ValueError):
        return True, 0
    if any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values()):
        return True, 0
    max_params = sum(
        1 for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    )
    return False, max_params


# Signal owner scoped to the emitting context; tokens restore nested emissions.
_current_sender: ContextVar[Any] = ContextVar("pysideweb_sender", default=None)


def sender():
    """Signal owner in the current thread/context, or None outside emission."""
    return _current_sender.get()

# Set PYSIDEWEB_STRICT=1 to re-raise slot exceptions (and unknown-API access)
# instead of swallowing them -- useful while developing an app against pysideweb.
_STRICT = bool(os.environ.get("PYSIDEWEB_STRICT"))


class BoundSignal:
    """A signal bound to a specific widget instance."""

    def __init__(self, signal: Signal, owner: Any):
        self._signal = signal
        self._owner = owner
        # (slot, accepts_all_args, max_positional_params) -- see _slot_arity().
        self._slots: list[tuple[Callable, bool, int]] = []

    def connect(self, slot: Callable):
        self._slots.append((slot, *_slot_arity(slot)))
        return True

    def disconnect(self, slot: Callable | None = None):
        if slot is None:
            self._slots.clear()
        else:
            self._slots = [s for s in self._slots if s[0] != slot]
        return True

    def emit(self, *args):
        if getattr(self._owner, "_signals_blocked", False):
            return
        token = _current_sender.set(self._owner)
        try:
            for slot, accepts_all, max_params in self._slots[:]:  # copy: allow modification mid-iteration
                try:
                    slot(*args) if accepts_all else slot(*args[:max_params])
                except Exception as e:
                    if _STRICT:
                        raise
                    print(f"[PySideWeb] Signal error in {self._signal._name}: {e}")
        finally:
            _current_sender.reset(token)


class Property(property):
    """Qt-style property descriptor supporting direct and decorator forms.

    The notify signal is metadata; as in Qt, setters emit it explicitly.
    """

    def __init__(self, type_=None, fget=None, fset=None, freset=None, doc=None,
                 notify=None, **metadata):
        self.type = type_
        self.notify = notify
        self.freset = freset
        self.metadata = metadata
        super().__init__(fget, fset, None, doc)

    def _copy(self, fget, fset):
        return type(self)(self.type, fget, fset, self.freset, self.__doc__,
                          self.notify, **self.metadata)

    def __call__(self, fget):
        return self.getter(fget)

    def getter(self, fget):
        return self._copy(fget, self.fset)

    def setter(self, fset):
        return self._copy(self.fget, fset)


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

def _absorb_ok(name: str) -> bool:
    """Whether `name` should degrade to a no-op placeholder rather than raise.

    "_"-prefixed (pysideweb internals duck-type on those), isFoo()/hasFoo()
    predicate names (libraries feature-detect with hasattr -- absorbing makes
    it always true), and everything under PYSIDEWEB_STRICT are answered with a
    real AttributeError instead.
    """
    if _STRICT or name.startswith("_"):
        return False
    # isFoo() / hasFoo() -> let hasattr() see a real miss so feature-detection
    # takes the unsupported branch instead of silently no-opping.
    if len(name) > 2 and name.startswith("is") and name[2].isupper():
        return False
    if len(name) > 3 and name.startswith("has") and name[3].isupper():
        return False
    return True


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
        if not _absorb_ok(name):
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
        if not _absorb_ok(name):
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
# QObject — root of the Qt object hierarchy
# ---------------------------------------------------------------------------
#
# Real Qt: QWidget IS-A QObject. Third-party code relies on that constantly --
# isinstance(x, QObject), class Thing(QObject) for signals, QObject.__init__,
# blockSignals(), sender(), findChild(), setProperty(). Before this class,
# QtCore.QObject was an unrelated inline stub and QWidget didn't inherit it, so
# every one of those checks failed. QWidget, QTimer and QAction now inherit
# this, and the interceptor exports this exact class as QtCore.QObject.

class QObject:
    """Root of the object hierarchy: object name, parent/child ownership,
    signal blocking, dynamic properties, event-filter hooks."""

    _declared_props: dict = {}

    objectName = Prop("")

    destroyed = Signal(object)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_props(cls)

    def __init__(self, parent=None):
        # A subclass (e.g. QWidget) may have already built _props.
        if not hasattr(self, "_props"):
            self._props = {n: p.default for n, p in self._declared_props.items()}
        self._qobject_parent = None
        self._qobject_children: list = []
        self._signals_blocked = False
        self._dynamic_props: dict = {}
        self._event_filters: list = []
        if parent is not None:
            self.setParent(parent)

    # -- ownership --
    def setParent(self, parent):
        old = self._qobject_parent
        if old is not None and self in getattr(old, "_qobject_children", ()):
            old._qobject_children.remove(self)
        self._qobject_parent = parent
        kids = getattr(parent, "_qobject_children", None)
        if kids is not None and self not in kids:
            kids.append(self)

    def parent(self):
        return self._qobject_parent

    def children(self):
        return list(self._qobject_children)

    # -- signal blocking --
    def blockSignals(self, block: bool) -> bool:
        old = self._signals_blocked
        self._signals_blocked = bool(block)
        return old

    def signalsBlocked(self) -> bool:
        return self._signals_blocked

    # -- dynamic properties --
    def setProperty(self, name: str, value) -> bool:
        existed = name in self._dynamic_props
        self._dynamic_props[name] = value
        return existed

    def property(self, name: str):
        return self._dynamic_props.get(name)

    def dynamicPropertyNames(self):
        return list(self._dynamic_props)

    # -- event filters (no native event loop, so these are inert but present) --
    def installEventFilter(self, obj):
        if obj not in self._event_filters:
            self._event_filters.append(obj)

    def removeEventFilter(self, obj):
        if obj in self._event_filters:
            self._event_filters.remove(obj)

    def eventFilter(self, obj, event):
        return False

    def event(self, event):
        return False

    def deleteLater(self):
        pass

    # -- introspection --
    def _iter_child_objects(self):
        for c in self._qobject_children:
            yield c
            if hasattr(c, "_iter_child_objects"):
                yield from c._iter_child_objects()

    def findChild(self, type_=None, name: str = "", *args):
        for c in self._iter_child_objects():
            if (not name or _obj_name(c) == name) and (type_ is None or isinstance(c, type_)):
                return c
        return None

    def findChildren(self, type_=None, name: str = "", *args):
        return [
            c for c in self._iter_child_objects()
            if (not name or _obj_name(c) == name) and (type_ is None or isinstance(c, type_))
        ]

    def inherits(self, class_name: str) -> bool:
        return any(k.__name__ == class_name for k in type(self).__mro__)

    def metaObject(self):
        return _AutoAttr()

    def thread(self):
        return _AutoAttr()

    def moveToThread(self, thread):
        pass

    def sender(self):
        return sender()

    @staticmethod
    def tr(text, *args, **kwargs):
        return text

    @staticmethod
    def connect(*args, **kwargs):
        # QObject.connect(sender, signal, receiver, slot) old-style form.
        if len(args) >= 2 and hasattr(args[1], "connect"):
            args[1].connect(args[-1])
        return True


# The root class does not run __init_subclass__ for itself.
_register_props(QObject)


def _obj_name(obj) -> str:
    getter = getattr(obj, "objectName", None)
    return getter() if callable(getter) else ""


class QEvent:
    """Minimal QEvent. `type()` returns whatever int/enum it was built with."""

    # A few commonly-checked types (values match Qt).
    Type = None
    MouseButtonPress = 2
    MouseButtonRelease = 3
    KeyPress = 6
    KeyRelease = 7
    Resize = 14
    Show = 17
    Hide = 18
    Close = 19
    Paint = 12

    def __init__(self, type_=0):
        self._type = type_
        self._accepted = True

    def type(self):
        return self._type

    def accept(self):
        self._accepted = True

    def ignore(self):
        self._accepted = False

    def isAccepted(self) -> bool:
        return self._accepted

    def setAccepted(self, accepted: bool):
        self._accepted = bool(accepted)


class QUrl:
    def __init__(self, url: str = ""):
        self._url = url.toString() if isinstance(url, QUrl) else str(url)

    def toString(self, *args) -> str:
        return self._url

    def url(self, *args) -> str:
        return self._url

    def isValid(self) -> bool:
        return bool(self._url)

    def isEmpty(self) -> bool:
        return not self._url

    def scheme(self) -> str:
        return self._url.split(":", 1)[0] if ":" in self._url else ""

    def toLocalFile(self) -> str:
        return self._url[7:] if self._url.startswith("file://") else self._url

    @staticmethod
    def fromLocalFile(path: str) -> QUrl:
        if not path.startswith("/"):
            path = "/" + path
        return QUrl(f"file://{path}")

    def __str__(self) -> str:
        return self._url

    def __repr__(self) -> str:
        return f"QUrl('{self._url}')"


class QModelIndex:
    def __init__(self, row: int = -1, col: int = -1, parent=None):
        self._row = row
        self._col = col
        self._parent = parent

    def row(self) -> int:
        return self._row

    def column(self) -> int:
        return self._col

    def isValid(self) -> bool:
        return self._row >= 0 and self._col >= 0

    def parent(self):
        return self._parent if self._parent is not None else QModelIndex()

    def data(self, role: int = 0):
        return None

    def __eq__(self, other):
        return (isinstance(other, QModelIndex)
                and (self._row, self._col) == (other._row, other._col))

    def __hash__(self):
        return hash((self._row, self._col))


class QSettings(QObject):
    """Persistent settings, backed by a JSON file under the user config dir.

    Real apps call ``QSettings()`` on startup and read values with a default
    (``settings.value("geometry", QByteArray())``). The universal fallback
    would drop that default; this keeps it, and actually persists.
    """

    NativeFormat = 0
    IniFormat = 1
    UserScope = 0
    SystemScope = 1

    def __init__(self, *args, **kwargs):
        super().__init__(None)
        parts = [a for a in args if isinstance(a, str)]
        org = parts[0] if parts else "pysideweb"
        app = parts[1] if len(parts) > 1 else "app"
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
        self._path = os.path.join(base, "pysideweb", f"{org}-{app}.json")
        self._group = ""
        self._data: dict = {}
        try:
            import json
            with open(self._path, encoding="utf-8") as fh:
                self._data = json.load(fh)
        except (OSError, ValueError):
            self._data = {}

    def _key(self, key: str) -> str:
        return f"{self._group}/{key}" if self._group else key

    def value(self, key: str, default=None, type=None):
        val = self._data.get(self._key(key), default)
        if type is not None and val is not None:
            try:
                return type(val)
            except (TypeError, ValueError):
                return default
        return val

    def setValue(self, key: str, value):
        self._data[self._key(key)] = value
        self.sync()

    def remove(self, key: str):
        self._data.pop(self._key(key), None)
        self.sync()

    def contains(self, key: str) -> bool:
        return self._key(key) in self._data

    def allKeys(self):
        return list(self._data)

    def beginGroup(self, prefix: str):
        self._group = f"{self._group}/{prefix}" if self._group else prefix

    def endGroup(self):
        self._group = self._group.rsplit("/", 1)[0] if "/" in self._group else ""

    def group(self) -> str:
        return self._group

    def sync(self):
        try:
            import json
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, default=str)
        except OSError:
            pass

    def fileName(self) -> str:
        return self._path


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
    Key_Escape = 0x01000000
    Key_Tab = 0x01000001
    Key_Backtab = 0x01000002
    Key_Backspace = 0x01000003
    Key_Return = 0x01000004
    Key_Enter = 0x01000005
    Key_Insert = 0x01000006
    Key_Delete = 0x01000007
    Key_Pause = 0x01000008
    Key_Print = 0x01000009
    Key_Home = 0x01000010
    Key_End = 0x01000011
    Key_Left = 0x01000012
    Key_Up = 0x01000013
    Key_Right = 0x01000014
    Key_Down = 0x01000015
    Key_PageUp = 0x01000016
    Key_PageDown = 0x01000017
    Key_Shift = 0x01000020
    Key_Control = 0x01000021
    Key_Meta = 0x01000022
    Key_Alt = 0x01000023
    Key_CapsLock = 0x01000024
    Key_NumLock = 0x01000025
    Key_ScrollLock = 0x01000026
    Key_F1 = 0x01000030
    Key_F2 = 0x01000031
    Key_F3 = 0x01000032
    Key_F4 = 0x01000033
    Key_F5 = 0x01000034
    Key_F6 = 0x01000035
    Key_F7 = 0x01000036
    Key_F8 = 0x01000037
    Key_F9 = 0x01000038
    Key_F10 = 0x01000039
    Key_F11 = 0x0100003a
    Key_F12 = 0x0100003b
    Key_Menu = 0x01000055
    Key_Help = 0x01000058
    Key_Space = 0x20
    Key_Exclam = 0x21
    Key_QuoteDbl = 0x22
    Key_NumberSign = 0x23
    Key_Dollar = 0x24
    Key_Percent = 0x25
    Key_Ampersand = 0x26
    Key_Apostrophe = 0x27
    Key_ParenLeft = 0x28
    Key_ParenRight = 0x29
    Key_Asterisk = 0x2a
    Key_Plus = 0x2b
    Key_Comma = 0x2c
    Key_Minus = 0x2d
    Key_Period = 0x2e
    Key_Slash = 0x2f
    Key_0 = 0x30
    Key_1 = 0x31
    Key_2 = 0x32
    Key_3 = 0x33
    Key_4 = 0x34
    Key_5 = 0x35
    Key_6 = 0x36
    Key_7 = 0x37
    Key_8 = 0x38
    Key_9 = 0x39
    Key_Colon = 0x3a
    Key_Semicolon = 0x3b
    Key_Less = 0x3c
    Key_Equal = 0x3d
    Key_Greater = 0x3e
    Key_Question = 0x3f
    Key_At = 0x40
    Key_A = 0x41
    Key_B = 0x42
    Key_C = 0x43
    Key_D = 0x44
    Key_E = 0x45
    Key_F = 0x46
    Key_G = 0x47
    Key_H = 0x48
    Key_I = 0x49
    Key_J = 0x4a
    Key_K = 0x4b
    Key_L = 0x4c
    Key_M = 0x4d
    Key_N = 0x4e
    Key_O = 0x4f
    Key_P = 0x50
    Key_Q = 0x51
    Key_R = 0x52
    Key_S = 0x53
    Key_T = 0x54
    Key_U = 0x55
    Key_V = 0x56
    Key_W = 0x57
    Key_X = 0x58
    Key_Y = 0x59
    Key_Z = 0x5a
    Key_BracketLeft = 0x5b
    Key_Backslash = 0x5c
    Key_BracketRight = 0x5d
    Key_Underscore = 0x5f
    Key_BraceLeft = 0x7b
    Key_Bar = 0x7c
    Key_BraceRight = 0x7d


class _MouseButton(IntFlag):
    NoButton = 0x00000000
    LeftButton = 0x00000001
    RightButton = 0x00000002
    MiddleButton = 0x00000004
    BackButton = 0x00000008
    ForwardButton = 0x00000010


class _KeyboardModifier(IntFlag):
    NoModifier = 0x00000000
    ShiftModifier = 0x02000000
    ControlModifier = 0x04000000
    AltModifier = 0x08000000
    MetaModifier = 0x10000000
    KeypadModifier = 0x20000000


class _ItemDataRole(IntEnum):
    DisplayRole = 0
    DecorationRole = 1
    EditRole = 2
    ToolTipRole = 3
    StatusTipRole = 4
    WhatsThisRole = 5
    FontRole = 6
    TextAlignmentRole = 7
    BackgroundRole = 8
    ForegroundRole = 9
    CheckStateRole = 10
    SizeHintRole = 13
    InitialSortOrderRole = 14
    UserRole = 256


class _FocusPolicy(IntEnum):
    NoFocus = 0
    TabFocus = 1
    ClickFocus = 2
    StrongFocus = 11
    WheelFocus = 15


class _TextFormat(IntEnum):
    PlainText = 0
    RichText = 1
    AutoText = 2
    MarkdownText = 3


class _ContextMenuPolicy(IntEnum):
    NoContextMenu = 0
    PreventContextMenu = 4
    DefaultContextMenu = 1
    ActionsContextMenu = 2
    CustomContextMenu = 3


class _ConnectionType(IntEnum):
    AutoConnection = 0
    DirectConnection = 1
    QueuedConnection = 2
    BlockingQueuedConnection = 3
    UniqueConnection = 0x80


class _AspectRatioMode(IntEnum):
    IgnoreAspectRatio = 0
    KeepAspectRatio = 1
    KeepAspectRatioByExpanding = 2


class _TransformationMode(IntEnum):
    FastTransformation = 0
    SmoothTransformation = 1


class _TextElideMode(IntEnum):
    ElideLeft = 0
    ElideRight = 1
    ElideMiddle = 2
    ElideNone = 3


class _LayoutDirection(IntEnum):
    LeftToRight = 0
    RightToLeft = 1
    LayoutDirectionAuto = 2

class _PenStyle(IntEnum):
    NoPen = 0
    SolidLine = 1
    DashLine = 2
    DotLine = 3
    DashDotLine = 4
    DashDotDotLine = 5

class _PenCapStyle(IntEnum):
    FlatCap = 0x00
    SquareCap = 0x10
    RoundCap = 0x20

class _PenJoinStyle(IntEnum):
    MiterJoin = 0x00
    BevelJoin = 0x40
    RoundJoin = 0x80

class _BrushStyle(IntEnum):
    NoBrush = 0
    SolidPattern = 1
    Dense1Pattern = 2
    Dense2Pattern = 3
    Dense3Pattern = 4
    Dense4Pattern = 5
    Dense5Pattern = 6
    Dense6Pattern = 7
    Dense7Pattern = 8
    HorPattern = 9
    VerPattern = 10
    CrossPattern = 11
    LinearGradientPattern = 15

class _GlobalColor(IntEnum):
    color0 = 0
    color1 = 1
    black = 2
    white = 3
    darkGray = 4
    gray = 5
    lightGray = 6
    red = 7
    green = 8
    blue = 9
    cyan = 10
    magenta = 11
    yellow = 12
    darkRed = 13
    darkGreen = 14
    darkBlue = 15
    darkCyan = 16
    darkMagenta = 17
    darkYellow = 18
    transparent = 19

class _QtConst(int):
    """Placeholder for a `Qt.<member>` pysideweb doesn't ship a real value for.

    Distinct names get distinct, stable values, so `event.key() == Qt.Key_Xyz`
    is at least self-consistent instead of raising AttributeError (the old
    behaviour) or collapsing every unknown member to 0. Bitwise use is
    meaningless but won't crash.
    """

    def __new__(cls, name: str):
        obj = int.__new__(cls, 0x7F000000 | (hash(name) & 0x00FFFFFF))
        obj._qt_name = name
        return obj

    def __repr__(self):
        return f"Qt.{self._qt_name}"


class _QtMeta(type):
    """Makes `Qt.<anything unknown>` return a stable `_QtConst` instead of
    raising. Real members (set by `_export_enum` below) are found first and
    never reach here."""

    _unknown: dict = {}

    def __getattr__(cls, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        c = _QtMeta._unknown.get(name)
        if c is None:
            c = _QtMeta._unknown[name] = _QtConst(name)
        return c


class Qt(metaclass=_QtMeta):
    """Namespace mirroring PySide6.QtCore.Qt.

    Real enum members are copied on by `_export_enum` (the loop below); any
    `Qt.<member>` we don't ship falls through `_QtMeta.__getattr__` to a
    stable placeholder rather than an AttributeError.
    """

    # Text interaction (not backed by one of the enums above)
    NoTextInteraction = 0
    TextSelectableByMouse = 1
    LinksAccessibleByMouse = 2
    TextBrowserInteraction = 3
    TextEditorInteraction = 0x13

    # Qt6 scoped-enum access: `Qt.AlignmentFlag.AlignLeft` as well as the flat
    # `Qt.AlignLeft`. Assigned after the export loop below.

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


# (enum class, scoped-access name). The scoped name lets Qt6-style
# `Qt.AlignmentFlag.AlignLeft` work alongside the flat `Qt.AlignLeft`.
_QT_ENUMS = [
    (_AlignmentFlag, "AlignmentFlag"), (_Orientation, "Orientation"),
    (_CheckState, "CheckState"), (_ItemFlag, "ItemFlag"),
    (_ScrollBarPolicy, "ScrollBarPolicy"), (_SortOrder, "SortOrder"),
    (_WindowType, "WindowType"), (_ToolButtonStyle, "ToolButtonStyle"),
    (_CursorShape, "CursorShape"), (_Key, "Key"),
    (_PenStyle, "PenStyle"), (_PenCapStyle, "PenCapStyle"),
    (_PenJoinStyle, "PenJoinStyle"), (_BrushStyle, "BrushStyle"),
    (_GlobalColor, "GlobalColor"), (_MouseButton, "MouseButton"),
    (_KeyboardModifier, "KeyboardModifier"), (_ItemDataRole, "ItemDataRole"),
    (_FocusPolicy, "FocusPolicy"), (_TextFormat, "TextFormat"),
    (_ContextMenuPolicy, "ContextMenuPolicy"), (_ConnectionType, "ConnectionType"),
    (_AspectRatioMode, "AspectRatioMode"), (_TransformationMode, "TransformationMode"),
    (_TextElideMode, "TextElideMode"), (_LayoutDirection, "LayoutDirection"),
]
for _enum_cls, _scoped in _QT_ENUMS:
    _export_enum(Qt, _enum_cls)
    setattr(Qt, _scoped, _enum_cls)
_export_enum(Qt.SizePolicy, _SizePolicy)
del _enum_cls, _scoped

# ---------------------------------------------------------------------------
# Value Types
# ---------------------------------------------------------------------------

class _QSizeBase:
    _num = int

    def __init__(self, w=-1, h=-1):
        if hasattr(w, "width"):  # copy ctor
            self._w, self._h = self._num(w.width()), self._num(w.height())
        else:
            self._w, self._h = self._num(w), self._num(h)

    def width(self): return self._w
    def height(self): return self._h
    def setWidth(self, w): self._w = self._num(w)
    def setHeight(self, h): self._h = self._num(h)
    def isNull(self): return self._w == 0 and self._h == 0
    def isEmpty(self): return self._w <= 0 or self._h <= 0
    def isValid(self): return self._w >= 0 and self._h >= 0
    def transposed(self): return type(self)(self._h, self._w)
    def toTuple(self): return (self._w, self._h)
    def toSize(self): return QSize(round(self._w), round(self._h))

    def boundedTo(self, other):
        return type(self)(min(self._w, other.width()), min(self._h, other.height()))

    def expandedTo(self, other):
        return type(self)(max(self._w, other.width()), max(self._h, other.height()))

    def scale(self, w, h=None, mode=None):
        pass  # aspect-ratio scaling: rarely needed for layout math here

    def __add__(self, o): return type(self)(self._w + o.width(), self._h + o.height())
    def __sub__(self, o): return type(self)(self._w - o.width(), self._h - o.height())
    def __mul__(self, f): return type(self)(self._w * f, self._h * f)
    __rmul__ = __mul__
    def __eq__(self, o): return hasattr(o, "width") and (self._w, self._h) == (o.width(), o.height())
    def __hash__(self): return hash((type(self).__name__, self._w, self._h))
    def __repr__(self): return f"{type(self).__name__}({self._w}, {self._h})"


class QSize(_QSizeBase):
    _num = int


class QSizeF(_QSizeBase):
    _num = float


class _QPointBase:
    _num = int

    def __init__(self, x=0, y=0):
        if hasattr(x, "x"):  # copy ctor
            self._x, self._y = self._num(x.x()), self._num(x.y())
        else:
            self._x, self._y = self._num(x), self._num(y)

    def x(self): return self._x
    def y(self): return self._y
    def setX(self, x): self._x = self._num(x)
    def setY(self, y): self._y = self._num(y)
    def isNull(self): return self._x == 0 and self._y == 0
    def manhattanLength(self): return abs(self._x) + abs(self._y)
    def toTuple(self): return (self._x, self._y)
    def toPoint(self): return QPoint(round(self._x), round(self._y))
    def transposed(self): return type(self)(self._y, self._x)
    def dotProduct(self, o): return self._x * o.x() + self._y * o.y()

    def __add__(self, o): return type(self)(self._x + o.x(), self._y + o.y())
    def __sub__(self, o): return type(self)(self._x - o.x(), self._y - o.y())
    def __mul__(self, f): return type(self)(self._x * f, self._y * f)
    __rmul__ = __mul__
    def __truediv__(self, f): return type(self)(self._x / f, self._y / f)
    def __neg__(self): return type(self)(-self._x, -self._y)
    def __eq__(self, o): return hasattr(o, "x") and (self._x, self._y) == (o.x(), o.y())
    def __hash__(self): return hash((type(self).__name__, self._x, self._y))
    def __repr__(self): return f"{type(self).__name__}({self._x}, {self._y})"


class QPoint(_QPointBase):
    _num = int


class QPointF(_QPointBase):
    _num = float


class _QRectBase:
    _num = int
    _point = None   # set below
    _size = None

    def __init__(self, *args):
        if len(args) == 2 and hasattr(args[0], "x") and hasattr(args[1], "width"):
            p, s = args
            self._x, self._y, self._w, self._h = p.x(), p.y(), s.width(), s.height()
        elif len(args) == 2 and hasattr(args[0], "x") and hasattr(args[1], "x"):
            p1, p2 = args
            self._x, self._y = p1.x(), p1.y()
            self._w, self._h = p2.x() - p1.x(), p2.y() - p1.y()
        elif len(args) == 1 and hasattr(args[0], "x"):
            r = args[0]
            self._x, self._y, self._w, self._h = r.x(), r.y(), r.width(), r.height()
        elif len(args) == 4:
            self._x, self._y, self._w, self._h = args
        else:
            self._x = self._y = self._w = self._h = 0
        n = self._num
        self._x, self._y, self._w, self._h = n(self._x), n(self._y), n(self._w), n(self._h)

    def x(self): return self._x
    def y(self): return self._y
    def width(self): return self._w
    def height(self): return self._h
    def left(self): return self._x
    def top(self): return self._y
    def right(self): return self._x + self._w - (1 if self._num is int else 0)
    def bottom(self): return self._y + self._h - (1 if self._num is int else 0)
    def setX(self, v): self._x = self._num(v)
    def setY(self, v): self._y = self._num(v)
    def setWidth(self, v): self._w = self._num(v)
    def setHeight(self, v): self._h = self._num(v)
    def setRect(self, x, y, w, h):
        self._x, self._y, self._w, self._h = x, y, w, h

    def setLeft(self, v):
        self._w += self._x - v
        self._x = v

    def setTop(self, v):
        self._h += self._y - v
        self._y = v

    def setRight(self, v):
        self._w = v - self._x

    def setBottom(self, v):
        self._h = v - self._y

    def topLeft(self): return self._point(self._x, self._y)
    def topRight(self): return self._point(self.right(), self._y)
    def bottomLeft(self): return self._point(self._x, self.bottom())
    def bottomRight(self): return self._point(self.right(), self.bottom())
    def center(self):
        if self._num is int:
            # Qt: QPoint(x1 + (x2 - x1)/2, ...) with x2 = x1 + w - 1 (inclusive).
            return self._point(self._x + (self._w - 1) // 2, self._y + (self._h - 1) // 2)
        return self._point(self._x + self._w / 2, self._y + self._h / 2)
    def size(self): return self._size(self._w, self._h)

    def moveTo(self, x, y=None):
        if y is None:
            x, y = x.x(), x.y()
        self._x, self._y = x, y

    def moveCenter(self, p):
        self._x = p.x() - self._w / 2
        self._y = p.y() - self._h / 2

    def translate(self, dx, dy=None):
        if dy is None:
            dx, dy = dx.x(), dx.y()
        self._x += dx
        self._y += dy

    def translated(self, dx, dy=None):
        r = type(self)(self)
        r.translate(dx, dy)
        return r

    def adjusted(self, dx1, dy1, dx2, dy2):
        return type(self)(self._x + dx1, self._y + dy1,
                          self._w - dx1 + dx2, self._h - dy1 + dy2)

    def adjust(self, dx1, dy1, dx2, dy2):
        self._x += dx1
        self._y += dy1
        self._w += dx2 - dx1
        self._h += dy2 - dy1

    def marginsRemoved(self, m):
        return type(self)(self._x + m.left(), self._y + m.top(),
                          self._w - m.left() - m.right(),
                          self._h - m.top() - m.bottom())

    def contains(self, *args):
        if len(args) == 1 and hasattr(args[0], "width"):
            r = args[0]
            return (r.left() >= self.left() and r.right() <= self.right()
                    and r.top() >= self.top() and r.bottom() <= self.bottom())
        px, py = (args[0].x(), args[0].y()) if len(args) == 1 else (args[0], args[1])
        return self._x <= px <= self._x + self._w and self._y <= py <= self._y + self._h

    def intersects(self, r):
        return not (r.left() > self.right() or r.right() < self.left()
                    or r.top() > self.bottom() or r.bottom() < self.top())

    def intersected(self, r):
        edge = 1 if self._num is int else 0  # right()/bottom() are inclusive for QRect
        x1, y1 = max(self.left(), r.left()), max(self.top(), r.top())
        x2, y2 = min(self.right(), r.right()), min(self.bottom(), r.bottom())
        if x2 < x1 or y2 < y1:
            return type(self)(x1, y1, 0, 0)
        return type(self)(x1, y1, x2 - x1 + edge, y2 - y1 + edge)

    def united(self, r):
        edge = 1 if self._num is int else 0
        x1, y1 = min(self.left(), r.left()), min(self.top(), r.top())
        x2, y2 = max(self.right(), r.right()), max(self.bottom(), r.bottom())
        return type(self)(x1, y1, x2 - x1 + edge, y2 - y1 + edge)

    def normalized(self):
        x, y, w, h = self._x, self._y, self._w, self._h
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h
        return type(self)(x, y, w, h)

    def isNull(self): return self._w == 0 and self._h == 0
    def isEmpty(self): return self._w <= 0 or self._h <= 0
    def isValid(self): return self._w > 0 and self._h > 0
    def getRect(self): return (self._x, self._y, self._w, self._h)
    def toRect(self): return QRect(round(self._x), round(self._y), round(self._w), round(self._h))
    def toTuple(self): return (self._x, self._y, self._w, self._h)

    def __and__(self, r): return self.intersected(r)
    def __or__(self, r): return self.united(r)
    def __eq__(self, o):
        return (hasattr(o, "width")
                and (self._x, self._y, self._w, self._h)
                == (o.x(), o.y(), o.width(), o.height()))
    def __hash__(self): return hash((type(self).__name__, self._x, self._y, self._w, self._h))
    def __repr__(self):
        return f"{type(self).__name__}({self._x}, {self._y}, {self._w}, {self._h})"


class QRect(_QRectBase):
    _num = int
    _point = QPoint
    _size = QSize


class QRectF(_QRectBase):
    _num = float
    _point = QPointF
    _size = QSizeF


class _QLineBase:
    _point = QPoint

    def __init__(self, *args):
        if len(args) == 2 and hasattr(args[0], "x"):
            self._x1, self._y1 = args[0].x(), args[0].y()
            self._x2, self._y2 = args[1].x(), args[1].y()
        elif len(args) == 4:
            self._x1, self._y1, self._x2, self._y2 = args
        else:
            self._x1 = self._y1 = self._x2 = self._y2 = 0

    def x1(self): return self._x1
    def y1(self): return self._y1
    def x2(self): return self._x2
    def y2(self): return self._y2
    def p1(self): return self._point(self._x1, self._y1)
    def p2(self): return self._point(self._x2, self._y2)
    def dx(self): return self._x2 - self._x1
    def dy(self): return self._y2 - self._y1
    def length(self):
        return (self.dx() ** 2 + self.dy() ** 2) ** 0.5
    def center(self):
        return self._point((self._x1 + self._x2) / 2, (self._y1 + self._y2) / 2)
    def isNull(self):
        return self._x1 == self._x2 and self._y1 == self._y2
    def translated(self, dx, dy=None):
        if dy is None:
            dx, dy = dx.x(), dx.y()
        return type(self)(self._x1 + dx, self._y1 + dy, self._x2 + dx, self._y2 + dy)
    def __eq__(self, o):
        return (isinstance(o, _QLineBase)
                and (self._x1, self._y1, self._x2, self._y2)
                == (o.x1(), o.y1(), o.x2(), o.y2()))
    def __hash__(self): return hash((type(self).__name__, self._x1, self._y1, self._x2, self._y2))
    def __repr__(self):
        return f"{type(self).__name__}({self._x1}, {self._y1}, {self._x2}, {self._y2})"


class QLine(_QLineBase):
    _point = QPoint


class QLineF(_QLineBase):
    _point = QPointF

# Qt.GlobalColor value -> (r, g, b, a). Mirrors Qt's predefined colours so
# `QColor(Qt.red)`, `painter.setPen(Qt.blue)`, etc. resolve to real pixels.
_GLOBAL_COLOR_RGB: dict[int, tuple[int, int, int, int]] = {
    0: (255, 255, 255, 0),   # color0 (transparent)
    1: (0, 0, 0, 255),       # color1
    2: (0, 0, 0, 255),       # black
    3: (255, 255, 255, 255), # white
    4: (128, 128, 128, 255), # darkGray
    5: (160, 160, 164, 255), # gray
    6: (192, 192, 192, 255), # lightGray
    7: (255, 0, 0, 255),     # red
    8: (0, 255, 0, 255),     # green
    9: (0, 0, 255, 255),     # blue
    10: (0, 255, 255, 255),  # cyan
    11: (255, 0, 255, 255),  # magenta
    12: (255, 255, 0, 255),  # yellow
    13: (128, 0, 0, 255),    # darkRed
    14: (0, 128, 0, 255),    # darkGreen
    15: (0, 0, 128, 255),    # darkBlue
    16: (0, 128, 128, 255),  # darkCyan
    17: (128, 0, 128, 255),  # darkMagenta
    18: (128, 128, 0, 255),  # darkYellow
    19: (0, 0, 0, 0),        # transparent
}


# CSS/SVG named colours -> (r, g, b). Lets QColor("steelblue").red() be right,
# which real Qt paint code depends on.
_CSS_COLORS: dict[str, tuple[int, int, int]] = {
    "aliceblue": (240, 248, 255), "antiquewhite": (250, 235, 215), "aqua": (0, 255, 255),
    "aquamarine": (127, 255, 212), "azure": (240, 255, 255), "beige": (245, 245, 220),
    "bisque": (255, 228, 196), "black": (0, 0, 0), "blanchedalmond": (255, 235, 205),
    "blue": (0, 0, 255), "blueviolet": (138, 43, 226), "brown": (165, 42, 42),
    "burlywood": (222, 184, 135), "cadetblue": (95, 158, 160), "chartreuse": (127, 255, 0),
    "chocolate": (210, 105, 30), "coral": (255, 127, 80), "cornflowerblue": (100, 149, 237),
    "cornsilk": (255, 248, 220), "crimson": (220, 20, 60), "cyan": (0, 255, 255),
    "darkblue": (0, 0, 139), "darkcyan": (0, 139, 139), "darkgoldenrod": (184, 134, 11),
    "darkgray": (169, 169, 169), "darkgreen": (0, 100, 0), "darkgrey": (169, 169, 169),
    "darkkhaki": (189, 183, 107), "darkmagenta": (139, 0, 139), "darkolivegreen": (85, 107, 47),
    "darkorange": (255, 140, 0), "darkorchid": (153, 50, 204), "darkred": (139, 0, 0),
    "darksalmon": (233, 150, 122), "darkseagreen": (143, 188, 143), "darkslateblue": (72, 61, 139),
    "darkslategray": (47, 79, 79), "darkslategrey": (47, 79, 79), "darkturquoise": (0, 206, 209),
    "darkviolet": (148, 0, 211), "deeppink": (255, 20, 147), "deepskyblue": (0, 191, 255),
    "dimgray": (105, 105, 105), "dimgrey": (105, 105, 105), "dodgerblue": (30, 144, 255),
    "firebrick": (178, 34, 34), "floralwhite": (255, 250, 240), "forestgreen": (34, 139, 34),
    "fuchsia": (255, 0, 255), "gainsboro": (220, 220, 220), "ghostwhite": (248, 248, 255),
    "gold": (255, 215, 0), "goldenrod": (218, 165, 32), "gray": (128, 128, 128),
    "green": (0, 128, 0), "greenyellow": (173, 255, 47), "grey": (128, 128, 128),
    "honeydew": (240, 255, 240), "hotpink": (255, 105, 180), "indianred": (205, 92, 92),
    "indigo": (75, 0, 130), "ivory": (255, 255, 240), "khaki": (240, 230, 140),
    "lavender": (230, 230, 250), "lavenderblush": (255, 240, 245), "lawngreen": (124, 252, 0),
    "lemonchiffon": (255, 250, 205), "lightblue": (173, 216, 230), "lightcoral": (240, 128, 128),
    "lightcyan": (224, 255, 255), "lightgoldenrodyellow": (250, 250, 210), "lightgray": (211, 211, 211),
    "lightgreen": (144, 238, 144), "lightgrey": (211, 211, 211), "lightpink": (255, 182, 193),
    "lightsalmon": (255, 160, 122), "lightseagreen": (32, 178, 170), "lightskyblue": (135, 206, 250),
    "lightslategray": (119, 136, 153), "lightslategrey": (119, 136, 153), "lightsteelblue": (176, 196, 222),
    "lightyellow": (255, 255, 224), "lime": (0, 255, 0), "limegreen": (50, 205, 50),
    "linen": (250, 240, 230), "magenta": (255, 0, 255), "maroon": (128, 0, 0),
    "mediumaquamarine": (102, 205, 170), "mediumblue": (0, 0, 205), "mediumorchid": (186, 85, 211),
    "mediumpurple": (147, 112, 219), "mediumseagreen": (60, 179, 113), "mediumslateblue": (123, 104, 238),
    "mediumspringgreen": (0, 250, 154), "mediumturquoise": (72, 209, 204), "mediumvioletred": (199, 21, 133),
    "midnightblue": (25, 25, 112), "mintcream": (245, 255, 250), "mistyrose": (255, 228, 225),
    "moccasin": (255, 228, 181), "navajowhite": (255, 222, 173), "navy": (0, 0, 128),
    "oldlace": (253, 245, 230), "olive": (128, 128, 0), "olivedrab": (107, 142, 35),
    "orange": (255, 165, 0), "orangered": (255, 69, 0), "orchid": (218, 112, 214),
    "palegoldenrod": (238, 232, 170), "palegreen": (152, 251, 152), "paleturquoise": (175, 238, 238),
    "palevioletred": (219, 112, 147), "papayawhip": (255, 239, 213), "peachpuff": (255, 218, 185),
    "peru": (205, 133, 63), "pink": (255, 192, 203), "plum": (221, 160, 221),
    "powderblue": (176, 224, 230), "purple": (128, 0, 128), "rebeccapurple": (102, 51, 153),
    "red": (255, 0, 0), "rosybrown": (188, 143, 143), "royalblue": (65, 105, 225),
    "saddlebrown": (139, 69, 19), "salmon": (250, 128, 114), "sandybrown": (244, 164, 96),
    "seagreen": (46, 139, 87), "seashell": (255, 245, 238), "sienna": (160, 82, 45),
    "silver": (192, 192, 192), "skyblue": (135, 206, 235), "slateblue": (106, 90, 205),
    "slategray": (112, 128, 144), "slategrey": (112, 128, 144), "snow": (255, 250, 250),
    "springgreen": (0, 255, 127), "steelblue": (70, 130, 180), "tan": (210, 180, 140),
    "teal": (0, 128, 128), "thistle": (216, 191, 216), "tomato": (255, 99, 71),
    "turquoise": (64, 224, 208), "violet": (238, 130, 238), "wheat": (245, 222, 179),
    "white": (255, 255, 255), "whitesmoke": (245, 245, 245), "yellow": (255, 255, 0),
    "yellowgreen": (154, 205, 50),
}


def _parse_color_string(s: str) -> tuple[int, int, int, int] | None:
    """('#rgb' | '#rrggbb' | '#rrggbbaa' | '#aarrggbb' | name) -> (r,g,b,a)."""
    s = s.strip()
    key = s.lower()
    if key in _CSS_COLORS:
        r, g, b = _CSS_COLORS[key]
        return r, g, b, 255
    if key in ("transparent",):
        return 0, 0, 0, 0
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            return tuple(int(c * 2, 16) for c in h) + (255,)  # type: ignore[return-value]
        if len(h) == 6:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255
        if len(h) == 8:  # Qt's #AARRGGBB
            return int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16), int(h[0:2], 16)
    return None


class QColor:
    HexRgb = 0
    HexArgb = 1

    def __init__(self, *args):
        self._r = self._g = self._b = 0
        self._a = 255
        self._valid = True
        if not args:
            self._valid = False
        elif len(args) == 1 and isinstance(args[0], QColor):
            src = args[0]
            self._r, self._g, self._b, self._a = src._r, src._g, src._b, src._a
            self._valid = src._valid
        elif len(args) == 1 and isinstance(args[0], _GlobalColor):
            self._r, self._g, self._b, self._a = _GLOBAL_COLOR_RGB.get(
                int(args[0]), (0, 0, 0, 255))
        elif len(args) == 1 and isinstance(args[0], str):
            parsed = _parse_color_string(args[0])
            if parsed is None:
                self._valid = False
            else:
                self._r, self._g, self._b, self._a = parsed
        elif len(args) == 1 and isinstance(args[0], int):
            v = args[0]  # QRgb: 0xAARRGGBB, alpha forced opaque (Qt behaviour)
            self._r, self._g, self._b = (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
        elif len(args) >= 3:
            self._r, self._g, self._b = (int(args[0]), int(args[1]), int(args[2]))
            self._a = int(args[3]) if len(args) > 3 else 255

    # -- construction helpers --
    @staticmethod
    def fromRgb(r, g, b, a=255):
        return QColor(r, g, b, a)

    @staticmethod
    def fromRgbF(r, g, b, a=1.0):
        return QColor(round(r * 255), round(g * 255), round(b * 255), round(a * 255))

    @staticmethod
    def fromHsv(h, s, v, a=255):
        c = QColor()
        c.setHsv(h, s, v, a)
        return c

    # -- channel access --
    def red(self) -> int: return self._r
    def green(self) -> int: return self._g
    def blue(self) -> int: return self._b
    def alpha(self) -> int: return self._a
    def redF(self) -> float: return self._r / 255
    def greenF(self) -> float: return self._g / 255
    def blueF(self) -> float: return self._b / 255
    def alphaF(self) -> float: return self._a / 255

    def getRgb(self):
        return (self._r, self._g, self._b, self._a)

    def getRgbF(self):
        return (self._r / 255, self._g / 255, self._b / 255, self._a / 255)

    def rgb(self) -> int:
        return (0xFF << 24) | (self._r << 16) | (self._g << 8) | self._b

    def rgba(self) -> int:
        return (self._a << 24) | (self._r << 16) | (self._g << 8) | self._b

    def setRed(self, v): self._r = int(v)
    def setGreen(self, v): self._g = int(v)
    def setBlue(self, v): self._b = int(v)

    def setAlpha(self, a: int):
        self._a = int(a)

    def setAlphaF(self, a: float):
        self._a = round(a * 255)

    def setRgb(self, r, g, b, a=255):
        self._r, self._g, self._b, self._a = int(r), int(g), int(b), int(a)
        self._valid = True

    def setNamedColor(self, name: str):
        parsed = _parse_color_string(name)
        if parsed is not None:
            self._r, self._g, self._b, self._a = parsed
            self._valid = True

    def setHsv(self, h, s, v, a=255):
        import colorsys
        h = (h % 360) / 360.0 if h >= 0 else 0.0
        r, g, b = colorsys.hsv_to_rgb(h, s / 255.0, v / 255.0)
        self._r, self._g, self._b, self._a = (
            round(r * 255), round(g * 255), round(b * 255), int(a))
        self._valid = True

    def getHsv(self):
        import colorsys
        h, s, v = colorsys.rgb_to_hsv(self._r / 255, self._g / 255, self._b / 255)
        return (round(h * 360), round(s * 255), round(v * 255), self._a)

    def hue(self): return self.getHsv()[0]
    def saturation(self): return self.getHsv()[1]
    def value(self): return self.getHsv()[2]

    def toHsv(self):
        return QColor.fromHsv(*self.getHsv())

    def toRgb(self):
        return QColor(self)

    # -- derived colours --
    def lighter(self, factor: int = 150):
        h, s, v, a = self.getHsv()
        return QColor.fromHsv(h, s, min(255, round(v * factor / 100)), a)

    def darker(self, factor: int = 200):
        h, s, v, a = self.getHsv()
        return QColor.fromHsv(h, s, round(v * 100 / factor), a)

    # -- names --
    def name(self, fmt: int = 0) -> str:
        if fmt == QColor.HexArgb:
            return f"#{self._a:02x}{self._r:02x}{self._g:02x}{self._b:02x}"
        return f"#{self._r:02x}{self._g:02x}{self._b:02x}"

    def _rgba_str(self) -> str:
        return f"rgba({self._r},{self._g},{self._b},{self._a / 255:.3f})"

    def to_css(self) -> str:
        """A CSS colour string usable anywhere (canvas fillStyle, style attr)."""
        return self.name() if self._a >= 255 else self._rgba_str()

    def isValid(self) -> bool:
        return self._valid

    def __eq__(self, other):
        return (isinstance(other, QColor)
                and (self._r, self._g, self._b, self._a)
                == (other._r, other._g, other._b, other._a))

    def __hash__(self):
        return hash((self._r, self._g, self._b, self._a))

    def __repr__(self):
        return f"QColor({self._r}, {self._g}, {self._b}, {self._a})"

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

# QPixmap lives in painting.py now (it reads a file into a data: URL); the
# interceptor exports painting.QPixmap as QtGui.QPixmap.

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

class _TimerScheduler:
    """One monotonic deadline heap shared by all virtual timers."""

    def __init__(self):
        self._condition = threading.Condition()
        self._deadlines: list[tuple[float, int, weakref.ReferenceType, int]] = []
        self._sequence = itertools.count()
        self._thread: threading.Thread | None = None

    def schedule(self, timer, generation: int, delay: float):
        deadline = time.monotonic() + max(0.0, delay)
        with self._condition:
            heapq.heappush(
                self._deadlines,
                (deadline, next(self._sequence), weakref.ref(timer), generation),
            )
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run, daemon=True, name="pysideweb-timers",
                )
                self._thread.start()
            self._condition.notify()

    def cancel(self, timer):
        with self._condition:
            # Generations make stale entries harmless. Compact in batches so
            # frequent start/stop remains O(1) instead of rebuilding the heap
            # for every timer operation, while long-delay cancellations cannot
            # grow the heap without bound.
            if len(self._deadlines) < 1024:
                self._condition.notify()
                return
            retained = [
                entry for entry in self._deadlines
                if (candidate := entry[2]()) is not None
                and candidate is not timer
                and candidate._running
                and candidate._generation == entry[3]
            ]
            if len(retained) != len(self._deadlines):
                self._deadlines = retained
                heapq.heapify(self._deadlines)
                self._condition.notify()

    def _run(self):
        while True:
            with self._condition:
                while not self._deadlines:
                    self._condition.wait()
                deadline, _, timer_ref, generation = self._deadlines[0]
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    self._condition.wait(remaining)
                    continue
                heapq.heappop(self._deadlines)
            timer = timer_ref()
            if timer is not None:
                timer._fire(generation)


_timer_scheduler = _TimerScheduler()


class QTimer(QObject):
    """Virtual QTimer using the process-wide monotonic scheduler thread."""

    timeout = Signal()
    _single_shots: set[QTimer] = set()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._interval = 0
        self._single_shot = False
        self._running = False
        self._generation = 0
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
        _timer_scheduler.cancel(self)
        self._running = True
        self._generation += 1
        _timer_scheduler.schedule(
            self, self._generation, max(0.001, self._interval / 1000.0),
        )

    def stop(self):
        self._running = False
        self._generation += 1
        _timer_scheduler.cancel(self)
        self._single_shots.discard(self)

    def isActive(self) -> bool:
        return self._running

    def _fire(self, generation: int):
        if not self._running or generation != self._generation:
            return
        self.timeout.emit()
        if not self._running or generation != self._generation:
            return
        if self._single_shot:
            self._running = False
            self._generation += 1
            self._single_shots.discard(self)
            return
        _timer_scheduler.schedule(
            self, generation, max(0.001, self._interval / 1000.0),
        )

    @staticmethod
    def singleShot(msec: int, slot: Callable):
        t = QTimer()
        t.setSingleShot(True)
        t.timeout.connect(slot)
        QTimer._single_shots.add(t)
        t.start(msec)

# ---------------------------------------------------------------------------
# QApplication
# ---------------------------------------------------------------------------

class _Clipboard(QObject):
    """A process-local clipboard. Can't touch the OS clipboard from a headless
    server, but code that round-trips text through it still works."""

    dataChanged = Signal()

    def __init__(self):
        super().__init__(None)
        self._text = ""

    def text(self, *args) -> str:
        return self._text

    def setText(self, text: str, *args):
        self._text = str(text)
        self.dataChanged.emit()

    def clear(self, *args):
        self._text = ""

    def mimeData(self, *args):
        return _AutoAttr()


class QApplication(QObject):
    """Virtual QApplication — starts the web server and blocks on exec()."""

    _instance: QApplication | None = None
    _clipboard: _Clipboard | None = None

    aboutToQuit = Signal()
    lastWindowClosed = Signal()

    def __init__(self, argv: list | None = None):
        QObject.__init__(self, None)
        QApplication._instance = self
        self._argv = argv if isinstance(argv, list) else sys.argv
        self._style_sheet = ""
        self._name = ""
        self._display_name = ""
        self._org = ""
        self._domain = ""
        self._font = QFont()
        self._quit_on_last_window_closed = True
        self._exit_code = 0
        self._quit_event = threading.Event()
        self._server_port = int(os.environ.get("PYSIDEWEB_PORT", "8765"))
        # Warm up the web server now (importing aiohttp is ~300 ms, plus the
        # bind) on a throwaway thread, so it overlaps with the user building
        # their widget tree instead of all landing on exec(). Skipped under
        # pytest, where nothing calls exec() and a bound socket is just noise.
        if "pytest" not in sys.modules:
            threading.Thread(
                target=self._boot_server, daemon=True, name="pysideweb-boot"
            ).start()

    def _boot_server(self):
        try:
            from . import server as srv
            srv.start_server(self._server_port)
        except Exception:  # noqa: BLE001 - exec() will surface a real error
            pass

    @staticmethod
    def instance():
        return QApplication._instance

    @staticmethod
    def clipboard() -> _Clipboard:
        if QApplication._clipboard is None:
            QApplication._clipboard = _Clipboard()
        return QApplication._clipboard

    def exec(self) -> int:
        return self.exec_()

    def exec_(self) -> int:
        from . import server as srv
        port = self._server_port
        srv.start_server(port)      # no-op if _boot_server already did it
        ok = srv.wait_for_server()

        url = f"http://localhost:{port}"
        if ok:
            print(f"\n{'=' * 50}")
            print(f"  PySideWeb running at: {url}")
            print("  Press Ctrl+C to quit")
            print(f"{'=' * 50}\n")
            if not os.environ.get("PYSIDEWEB_NO_BROWSER"):
                webbrowser.open(url)
        else:
            print("[PySideWeb] the UI is NOT being served (see the error above). "
                  "Ctrl+C to exit.")

        try:
            self._quit_event.wait()
        except KeyboardInterrupt:
            pass
        print("\n[PySideWeb] Shutting down...")
        try:
            self.aboutToQuit.emit()
        except Exception:
            pass
        return self._exit_code

    @staticmethod
    def quit(code: int = 0):
        inst = QApplication._instance
        if inst is not None:
            inst._exit_code = int(code) if isinstance(code, int) else 0
            inst._quit_event.set()

    exit = quit
    closeAllWindows = quit

    @staticmethod
    def processEvents(*args, **kwargs):
        pass  # no native event loop to pump

    @staticmethod
    def sendEvent(*args, **kwargs):
        return False

    postEvent = sendEvent

    # -- app-wide style --
    def setStyleSheet(self, css: str):
        self._style_sheet = css or ""
        state.set_app_stylesheet(self._style_sheet)

    def styleSheet(self) -> str:
        return self._style_sheet

    def setStyle(self, style):
        pass

    def style(self):
        return _AutoAttr()

    # -- app-wide font / palette --
    def setFont(self, font):
        self._font = font

    def font(self):
        return self._font

    def palette(self, *args):
        return _AutoAttr()

    def setPalette(self, *args):
        pass

    # -- metadata --
    def setApplicationName(self, name: str):
        self._name = name

    def applicationName(self) -> str:
        return self._name

    def setApplicationDisplayName(self, name: str):
        self._display_name = name

    def applicationDisplayName(self) -> str:
        return self._display_name

    def setApplicationVersion(self, v: str):
        self._version = v

    def setOrganizationName(self, name: str):
        self._org = name

    def setOrganizationDomain(self, domain: str):
        self._domain = domain

    def setWindowIcon(self, icon):
        pass

    def windowIcon(self):
        return QIcon()

    def setDesktopFileName(self, name: str):
        pass

    def setQuitOnLastWindowClosed(self, on: bool):
        self._quit_on_last_window_closed = bool(on)

    def quitOnLastWindowClosed(self) -> bool:
        return self._quit_on_last_window_closed

    # -- widget / screen queries --
    @staticmethod
    def topLevelWidgets():
        return state.get_roots()

    allWidgets = topLevelWidgets

    @staticmethod
    def activeWindow():
        roots = state.get_roots()
        return roots[-1] if roots else None

    activeModalWidget = activeWindow
    focusWidget = activeWindow

    @staticmethod
    def primaryScreen():
        return _AutoAttr()

    @staticmethod
    def screens():
        return [_AutoAttr()]

    @staticmethod
    def setOverrideCursor(*args):
        pass

    @staticmethod
    def restoreOverrideCursor(*args):
        pass

    @staticmethod
    def setEffectEnabled(*args):
        pass


# Qt6 keeps QCoreApplication / QGuiApplication distinct; here they're aliases.
QCoreApplication = QApplication
QGuiApplication = QApplication
