"""
pysideweb.interceptor — Module-level interception of PySide6 imports.

When `install()` is called, this module injects custom module objects into
`sys.modules` so that any subsequent `from PySide6.QtWidgets import ...`
(or QtCore, QtGui) returns our virtual classes instead of real Qt ones.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys
import types
from typing import Any

from . import core, layouts, painting, widgets


def _public_classes(module: types.ModuleType) -> dict[str, type]:
    """Every `Q*`-named class *defined in* `module` or one of its submodules
    (not merely imported into it from elsewhere).

    Adding a new class to `widgets/` or `layouts.py` is then enough on its own
    to expose it through the fake `PySide6` package -- this reflects over the
    namespace instead of a hand-maintained list. Works for a plain module
    (`layouts`) and a package (`widgets`, whose classes live in
    `pysideweb.widgets.<submodule>`).
    """
    pkg = module.__name__
    return {
        name: obj for name, obj in vars(module).items()
        if isinstance(obj, type) and name.startswith("Q")
        and (obj.__module__ == pkg or obj.__module__.startswith(pkg + "."))
    }


def _build_qtwidgets_namespace() -> dict[str, Any]:
    """Build the namespace for the fake PySide6.QtWidgets module."""
    ns: dict[str, Any] = {}
    ns.update(_public_classes(widgets))
    ns.update(_public_classes(layouts))
    ns['QApplication'] = core.QApplication
    return ns


def _build_qtcore_namespace() -> dict[str, Any]:
    """Build the namespace for the fake PySide6.QtCore module."""
    ns: dict[str, Any] = {}
    ns['Qt'] = core.Qt
    ns['Signal'] = core.Signal
    ns['QTimer'] = core.QTimer
    for _name in (
        "QSize", "QSizeF", "QPoint", "QPointF", "QRect", "QRectF",
        "QLine", "QLineF", "QMargins",
    ):
        ns[_name] = getattr(core, _name)

    # Slot decorator (no-op in web mode)
    def Slot(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator

    ns['Slot'] = Slot

    ns['Property'] = core.Property

    # Real object hierarchy + value types (see core.py).
    ns['QObject'] = core.QObject
    ns['QEvent'] = core.QEvent
    ns['QUrl'] = core.QUrl
    ns['QModelIndex'] = core.QModelIndex
    ns['QSettings'] = core.QSettings

    return ns


def _build_qtgui_namespace() -> dict[str, Any]:
    """Build the namespace for the fake PySide6.QtGui module."""
    ns: dict[str, Any] = {}
    ns['QColor'] = core.QColor
    ns['QFont'] = core.QFont
    ns['QIcon'] = core.QIcon
    ns['QAction'] = widgets.QAction  # Qt6 moved QAction to QtGui

    # Real virtual-painting pipeline (pysideweb/painting.py): a QPainter that
    # records drawing calls for replay on an HTML5 <canvas>, plus its
    # supporting value types.
    ns['QPainter'] = painting.QPainter
    ns['QPen'] = painting.QPen
    ns['QBrush'] = painting.QBrush
    ns['QPainterPath'] = painting.QPainterPath
    ns['QPolygon'] = painting.QPolygon
    ns['QPolygonF'] = painting.QPolygonF
    ns['QLinearGradient'] = painting.QLinearGradient
    ns['QRadialGradient'] = painting.QRadialGradient
    ns['QConicalGradient'] = painting.QRadialGradient
    ns['QGradient'] = painting.QGradient
    ns['QImage'] = painting.QImage
    ns['QPixmap'] = painting.QPixmap
    ns['QPaintEvent'] = painting.QPaintEvent
    ns['QPaintDevice'] = painting.QPaintDevice

    # QPalette stub
    class QPalette:
        Window = 0
        WindowText = 1
        Base = 2
        AlternateBase = 3
        ToolTipBase = 4
        ToolTipText = 5
        PlaceholderText = 6
        Text = 7
        Button = 8
        ButtonText = 9
        BrightText = 10
        Light = 11
        Midlight = 12
        Dark = 13
        Mid = 14
        Shadow = 15
        Highlight = 16
        HighlightedText = 17
        Link = 18
        LinkVisited = 19

        def __init__(self):
            self._colors: dict = {}

        def setColor(self, role, color):
            self._colors[role] = color

        def color(self, role):
            return self._colors.get(role, core.QColor())

    ns['QPalette'] = QPalette

    # QKeySequence
    class QKeySequence:
        def __init__(self, key: str = ""):
            self._key = key

        def toString(self) -> str:
            return self._key

    ns['QKeySequence'] = QKeySequence

    # QCursor
    class QCursor:
        @staticmethod
        def pos():
            return core.QPoint(0, 0)

    ns['QCursor'] = QCursor

    # Approximate text metrics (per-character width table; no real font engine).
    ns['QFontMetrics'] = painting.QFontMetrics
    ns['QFontMetricsF'] = painting.QFontMetricsF

    return ns


# ---------------------------------------------------------------------------
# Universal fallback: classes/submodules pysideweb doesn't implement
# ---------------------------------------------------------------------------
#
# pysideweb only implements a subset of Qt. Real-world PySide6 code --
# including third-party libraries found on GitHub (pyqtgraph and friends),
# not just apps written directly against pysideweb -- routinely imports
# classes and even whole submodules outside that subset. A fixed namespace
# dict makes every one of those a hard ImportError/AttributeError.
#
# Each fake module below gets a PEP 562 module-level __getattr__ that
# auto-generates (and caches, so repeated access returns the same class --
# matters for isinstance checks and subclassing) a permissive placeholder
# for any name it doesn't already know about, instead of failing the import.

_unknown_widget_classes: dict[str, type] = {}
_unknown_value_classes: dict[str, type] = {}
_unknown_submodules: dict[str, types.ModuleType] = {}


def _warn_once(name: str, what: str) -> None:
    print(f"[PySideWeb] Note: {name} isn't implemented -- using a placeholder that "
          f"{what}. If you need it, please open an issue.")


def _unknown_widget_init(self, *args, **kwargs):
    """Replaces QWidget.__init__'s fixed (parent=None, flags=None) signature
    on generated unknown-widget classes: a real Qt class we don't implement
    can take any constructor shape (QGraphicsView(scene), QGraphicsView(x,
    y, w, h), ...), and calling QWidget.__init__ positionally with more args
    than it accepts would raise TypeError -- exactly the crash this whole
    mechanism exists to avoid. `parent` is still picked up, by keyword or as
    the first widget-like positional argument, so nesting still works when
    the caller does pass one.
    """
    parent = kwargs.get("parent")
    if parent is None:
        parent = next((a for a in args if hasattr(a, "_children")), None)
    widgets.QWidget.__init__(self, parent)


def _unknown_widget_class(name: str) -> type:
    """A QtWidgets class pysideweb hasn't implemented: made a real QWidget
    subclass so it can still be added to a layout and shown -- it renders
    as an empty placeholder box, and any Qt method called on it is absorbed
    by QWidget's own __getattr__ fallback (see widgets.py). Built with
    core._AutoAttrMeta so class-level constants (`QGraphicsView.ScrollHandDrag`
    and the like, referenced without an instance) are absorbed too."""
    if name not in _unknown_widget_classes:
        _warn_once(name, "renders as an empty box and absorbs any Qt calls made on it")
        _unknown_widget_classes[name] = core._AutoAttrMeta(
            name, (widgets.QWidget,),
            {"_widget_type": name, "__init__": _unknown_widget_init},
        )
    return _unknown_widget_classes[name]


def _unknown_value_class(name: str) -> type:
    """A QtCore/QtGui/other class pysideweb hasn't implemented: most of
    these are value types (QTransform, QPen, an enum, ...), not widgets, so
    this is a plain core._AutoAttr subclass -- constructible with any
    arguments, and every attribute access/call on it is absorbed."""
    if name not in _unknown_value_classes:
        _warn_once(name, "silently absorbs any use of it")
        _unknown_value_classes[name] = type(name, (core._AutoAttr,), {})
    return _unknown_value_classes[name]


def _make_module(
    name: str, namespace: dict, unknown_factory=None
) -> types.ModuleType:
    """Create a fake module from a namespace dict. If `unknown_factory` is
    given, any attribute not already in `namespace` is generated on demand
    via `unknown_factory(attr_name)` instead of raising AttributeError."""
    mod = types.ModuleType(name)
    mod.__package__ = "PySide6"
    mod.__path__ = []
    mod.__file__ = f"<pysideweb:{name}>"
    for key, value in namespace.items():
        setattr(mod, key, value)

    if unknown_factory is not None:
        def __getattr__(attr_name: str, _factory=unknown_factory):
            if attr_name.startswith("__"):
                raise AttributeError(attr_name)
            return _factory(attr_name)
        mod.__getattr__ = __getattr__

    return mod


def _unknown_submodule(name: str) -> types.ModuleType:
    """A `PySide6.<Something>` submodule we don't stub at all (e.g.
    QtCharts) -- e.g. `from PySide6.QtCharts import QChart`. Built the same
    permissive way as QtNetwork/QtSvg/etc. below, and registered in
    sys.modules so the `from X import Y` machinery can find it."""
    if name not in _unknown_submodules:
        mod = _make_module(f"PySide6.{name}", {}, unknown_factory=_unknown_value_class)
        _unknown_submodules[name] = mod
        sys.modules[f"PySide6.{name}"] = mod
    return _unknown_submodules[name]


class _UnknownSubmoduleFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Makes `import PySide6.<Something>` work for a submodule pysideweb
    doesn't stub at all (e.g. `import PySide6.QtCharts`), not just
    `from PySide6 import <Something>`.

    Module __getattr__ (used everywhere else in this file) only covers
    plain attribute access -- `X.Y` as an expression, or `from X import Y`.
    A bare `import X.Y` statement instead asks the import system's
    sys.meta_path finders to locate "X.Y" directly, bypassing attribute
    access on X entirely, so that path needs its own hook.
    """

    def find_spec(self, fullname: str, path, target=None):
        if fullname in sys.modules or not fullname.startswith("PySide6."):
            return None
        if fullname.count(".") != 1:  # only PySide6.<Something>, not deeper
            return None
        return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return _unknown_submodule(spec.name.split(".", 1)[1])

    def exec_module(self, module):
        pass  # _unknown_submodule() already fully populated it


def install():
    """
    Patch sys.modules so that `from PySide6.QtWidgets import ...` etc.
    returns our virtual classes.
    """
    if not any(isinstance(f, _UnknownSubmoduleFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _UnknownSubmoduleFinder())

    # Create the fake PySide6 parent module, then its real sub-modules
    pyside6 = _make_module(
        "PySide6", {"__version__": "6.99.0-pysideweb"}, unknown_factory=_unknown_submodule
    )
    submodules = {
        "QtWidgets": (_build_qtwidgets_namespace(), _unknown_widget_class),
        "QtCore": (_build_qtcore_namespace(), _unknown_value_class),
        "QtGui": (_build_qtgui_namespace(), _unknown_value_class),
        # Common sub-module imports we don't implement beyond an empty stub
        # namespace -- unknown_factory covers anything imported *from* them.
        **{name: ({}, _unknown_value_class) for name in [
            "QtNetwork", "QtSvg", "QtSvgWidgets", "QtOpenGL",
            "QtMultimedia", "QtPrintSupport", "QtWebEngine",
            "QtWebEngineWidgets",
        ]},
    }
    for name, (namespace, unknown_factory) in submodules.items():
        mod = _make_module(f"PySide6.{name}", namespace, unknown_factory=unknown_factory)
        setattr(pyside6, name, mod)
        sys.modules[f"PySide6.{name}"] = mod

    sys.modules["PySide6"] = pyside6

    print("[PySideWeb] PySide6 imports intercepted -- UI will render in your browser")
