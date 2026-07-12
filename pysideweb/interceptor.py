"""
pysideweb.interceptor — Module-level interception of PySide6 imports.

When `install()` is called, this module injects custom module objects into
`sys.modules` so that any subsequent `from PySide6.QtWidgets import ...`
(or QtCore, QtGui) returns our virtual classes instead of real Qt ones.
"""

from __future__ import annotations

import sys
import types
from typing import Any

from . import core, layouts, widgets


def _build_qtwidgets_namespace() -> dict[str, Any]:
    """Build the namespace for the fake PySide6.QtWidgets module."""
    ns: dict[str, Any] = {}

    # Widgets
    widget_classes = [
        'QWidget', 'QMainWindow', 'QFrame', 'QPushButton', 'QLabel',
        'QLineEdit', 'QTextEdit', 'QComboBox', 'QCheckBox', 'QRadioButton',
        'QSlider', 'QProgressBar', 'QSpinBox', 'QDoubleSpinBox',
        'QTabWidget', 'QGroupBox', 'QScrollArea', 'QStackedWidget',
        'QListWidget', 'QListWidgetItem', 'QSplitter',
        'QMenuBar', 'QMenu', 'QAction', 'QToolBar', 'QStatusBar',
        'QDialog', 'QMessageBox', 'QButtonGroup',
        'QSizePolicy', 'QSpacerItem', 'QWidgetItem',
    ]
    for name in widget_classes:
        cls = getattr(widgets, name, None)
        if cls is not None:
            ns[name] = cls

    # Layouts
    layout_classes = [
        'QVBoxLayout', 'QHBoxLayout', 'QGridLayout', 'QFormLayout',
        'QStackedLayout', 'QLayout',
    ]
    for name in layout_classes:
        cls = getattr(layouts, name, None)
        if cls is not None:
            ns[name] = cls

    # QApplication
    ns['QApplication'] = core.QApplication

    return ns


def _build_qtcore_namespace() -> dict[str, Any]:
    """Build the namespace for the fake PySide6.QtCore module."""
    ns: dict[str, Any] = {}
    ns['Qt'] = core.Qt
    ns['Signal'] = core.Signal
    ns['QTimer'] = core.QTimer
    ns['QSize'] = core.QSize
    ns['QPoint'] = core.QPoint
    ns['QRect'] = core.QRect
    ns['QMargins'] = core.QMargins

    # Slot decorator (no-op in web mode)
    def Slot(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator

    ns['Slot'] = Slot

    # Property (simple stub)
    class Property:
        def __init__(self, type_=None, fget=None, fset=None, notify=None):
            self._fget = fget
            self._fset = fset

        def __call__(self, func):
            return func

        def getter(self, func):
            self._fget = func
            return self

        def setter(self, func):
            self._fset = func
            return self

    ns['Property'] = Property

    # QObject base (maps to QWidget for simplicity)
    class QObject:
        def __init__(self, parent=None):
            self._parent = parent

        def setParent(self, parent):
            self._parent = parent

        def parent(self):
            return self._parent

        def deleteLater(self):
            pass

        def findChild(self, *args):
            return None

    ns['QObject'] = QObject

    # QEvent
    class QEvent:
        def __init__(self, type_=0):
            self._type = type_

        def type(self):
            return self._type

        def accept(self):
            pass

        def ignore(self):
            pass

    ns['QEvent'] = QEvent

    # QUrl
    class QUrl:
        def __init__(self, url: str = ""):
            self._url = url

        def toString(self) -> str:
            return self._url

        @staticmethod
        def fromLocalFile(path: str):
            return QUrl(f"file:///{path}")

    ns['QUrl'] = QUrl

    # QModelIndex stub
    class QModelIndex:
        def __init__(self):
            self._row = -1
            self._col = -1

        def row(self) -> int:
            return self._row

        def column(self) -> int:
            return self._col

        def isValid(self) -> bool:
            return self._row >= 0

    ns['QModelIndex'] = QModelIndex

    return ns


def _build_qtgui_namespace() -> dict[str, Any]:
    """Build the namespace for the fake PySide6.QtGui module."""
    ns: dict[str, Any] = {}
    ns['QColor'] = core.QColor
    ns['QFont'] = core.QFont
    ns['QIcon'] = core.QIcon
    ns['QPixmap'] = core.QPixmap
    ns['QAction'] = widgets.QAction  # Qt6 moved QAction to QtGui

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

    # QBrush stub
    class QBrush:
        def __init__(self, color=None):
            self._color = color or core.QColor()

        def color(self):
            return self._color

    ns['QBrush'] = QBrush

    # QPen stub
    class QPen:
        def __init__(self, *args):
            pass

    ns['QPen'] = QPen

    # QPainter stub
    class QPainter:
        def __init__(self, *args):
            pass

        def begin(self, *args): pass
        def end(self): pass
        def setPen(self, *args): pass
        def setBrush(self, *args): pass
        def drawText(self, *args): pass
        def drawRect(self, *args): pass
        def fillRect(self, *args): pass

    ns['QPainter'] = QPainter

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

    # QFontMetrics
    class QFontMetrics:
        def __init__(self, font=None):
            pass

        def horizontalAdvance(self, text: str) -> int:
            return len(text) * 8

        def height(self) -> int:
            return 16

        def boundingRect(self, *args):
            return core.QRect(0, 0, 100, 16)

    ns['QFontMetrics'] = QFontMetrics

    # QImage stub
    class QImage:
        def __init__(self, *args):
            pass

    ns['QImage'] = QImage

    return ns


def _make_module(name: str, namespace: dict) -> types.ModuleType:
    """Create a fake module from a namespace dict."""
    mod = types.ModuleType(name)
    mod.__package__ = "PySide6"
    mod.__path__ = []
    mod.__file__ = f"<pysideweb:{name}>"
    for key, value in namespace.items():
        setattr(mod, key, value)
    return mod


def install():
    """
    Patch sys.modules so that `from PySide6.QtWidgets import ...` etc.
    returns our virtual classes.
    """
    # Create the fake PySide6 parent module
    pyside6 = types.ModuleType("PySide6")
    pyside6.__package__ = "PySide6"
    pyside6.__path__ = []
    pyside6.__file__ = "<pysideweb:PySide6>"
    pyside6.__version__ = "6.99.0-pysideweb"

    # Build sub-modules
    qtwidgets = _make_module("PySide6.QtWidgets", _build_qtwidgets_namespace())
    qtcore = _make_module("PySide6.QtCore", _build_qtcore_namespace())
    qtgui = _make_module("PySide6.QtGui", _build_qtgui_namespace())

    # Attach to parent
    pyside6.QtWidgets = qtwidgets
    pyside6.QtCore = qtcore
    pyside6.QtGui = qtgui

    # Inject into sys.modules
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtWidgets"] = qtwidgets
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui

    # Also handle common sub-module imports
    # PySide6.QtNetwork, PySide6.QtSvg, etc. — provide empty stubs
    for submod_name in ["QtNetwork", "QtSvg", "QtSvgWidgets", "QtOpenGL",
                        "QtMultimedia", "QtPrintSupport", "QtWebEngine",
                        "QtWebEngineWidgets"]:
        full_name = f"PySide6.{submod_name}"
        stub = types.ModuleType(full_name)
        stub.__package__ = "PySide6"
        stub.__path__ = []
        stub.__file__ = f"<pysideweb:{full_name}>"
        setattr(pyside6, submod_name, stub)
        sys.modules[full_name] = stub

    print("[PySideWeb] PySide6 imports intercepted -- UI will render in your browser")
