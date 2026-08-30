"""pysideweb.widgets.containers - windows, frames, tabs, stacks, dialogs."""

from __future__ import annotations

from .. import state
from ..core import (
    Prop,
    Qt,
    Signal,
)
from .base import QWidget
from .chrome import QMenuBar, QStatusBar, QToolBar


class QMainWindow(QWidget):
    _widget_type = "QMainWindow"

    def __init__(self, parent=None, flags=None):
        super().__init__(parent, flags)
        self._central_widget = None
        self._menu_bar = None
        self._status_bar = None
        self._toolbars: list = []

    def setCentralWidget(self, widget: QWidget):
        self._central_widget = widget
        self._add_child(widget)
        state.notify_full_refresh()

    def centralWidget(self):
        return self._central_widget

    def menuBar(self):
        if self._menu_bar is None:
            self._menu_bar = QMenuBar(self)
        return self._menu_bar

    def setMenuBar(self, bar):
        self._menu_bar = bar

    def statusBar(self):
        if self._status_bar is None:
            self._status_bar = QStatusBar(self)
        return self._status_bar

    def setStatusBar(self, bar):
        self._status_bar = bar

    def addToolBar(self, *args):
        if args:
            toolbar = args[-1] if isinstance(args[-1], QToolBar) else QToolBar(args[0] if args else "")
            self._toolbars.append(toolbar)
            return toolbar

    def _get_props(self) -> dict:
        props = super()._get_props()
        if self._central_widget:
            props["centralWidgetId"] = self._central_widget._wid
        return props


class QFrame(QWidget):
    _widget_type = "QFrame"

    NoFrame = 0
    Box = 1
    Panel = 2
    StyledPanel = 6
    HLine = 4
    VLine = 5
    Plain = 0x0010
    Raised = 0x0020
    Sunken = 0x0030

    frameShape = Prop(NoFrame)
    frameShadow = Prop(Plain)
    # `lineWidth` had no getter at all in the hand-written version (only
    # setLineWidth() existed, storing into an otherwise-unread
    # `self._line_width`) â€” Prop gives it a matching getter for free.
    lineWidth = Prop(1)


class QTabWidget(QWidget):
    _widget_type = "QTabWidget"

    currentChanged = Signal(int)

    currentIndex = Prop(0, notify=True, signal="currentChanged", cast=int)
    tabPosition = Prop(0, in_props=False)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs: list[dict] = []  # [{text, icon, widget}]

    def addTab(self, widget: QWidget, *args) -> int:
        icon = None
        text = ""
        if len(args) == 1:
            text = args[0]
        elif len(args) == 2:
            icon = args[0]
            text = args[1]
        tab = {"text": text, "icon": icon, "widget": widget}
        self._add_child(widget)
        self._tabs.append(tab)
        state.notify_full_refresh()
        return len(self._tabs) - 1

    def insertTab(self, index: int, widget: QWidget, text: str) -> int:
        tab = {"text": text, "icon": None, "widget": widget}
        widget._parent = self
        self._tabs.insert(index, tab)
        return index

    def removeTab(self, index: int):
        if 0 <= index < len(self._tabs):
            self._tabs.pop(index)
            if self.currentIndex() >= len(self._tabs):
                self.setCurrentIndex(max(0, len(self._tabs) - 1))

    def count(self) -> int:
        return len(self._tabs)

    def tabText(self, index: int) -> str:
        return self._tabs[index]["text"] if 0 <= index < len(self._tabs) else ""

    def setTabText(self, index: int, text: str):
        if 0 <= index < len(self._tabs):
            self._tabs[index]["text"] = text

    def widget(self, index: int):
        return self._tabs[index]["widget"] if 0 <= index < len(self._tabs) else None

    def setTabBarAutoHide(self, hide: bool):
        pass

    def setDocumentMode(self, mode: bool):
        pass

    def setMovable(self, movable: bool):
        pass

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["tabs"] = [
            {
                "text": t["text"],
                "icon": t["icon"].text() if t["icon"] and hasattr(t["icon"], 'text') else None,
                "widgetId": t["widget"]._wid,
            }
            for t in self._tabs
        ]
        return props

    def _handle_event(self, event_type, value):
        if event_type == "currentChanged":
            self.setCurrentIndex(int(value))


class QGroupBox(QWidget):
    _widget_type = "QGroupBox"

    toggled = Signal(bool)

    title = Prop("", notify=True)
    checkable = Prop(False, getter="isCheckable")
    checked = Prop(True, getter="isChecked")

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._props["title"] = title


class QScrollArea(QWidget):
    _widget_type = "QScrollArea"

    widgetResizable = Prop(True)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widget_inside = None

    def setWidget(self, widget: QWidget):
        self._widget_inside = widget
        self._add_child(widget)

    def widget(self):
        return self._widget_inside

    def setHorizontalScrollBarPolicy(self, policy):
        pass

    def setVerticalScrollBarPolicy(self, policy):
        pass

    def _get_props(self) -> dict:
        props = super()._get_props()
        if self._widget_inside:
            props["innerWidgetId"] = self._widget_inside._wid
        return props


class QStackedWidget(QWidget):
    _widget_type = "QStackedWidget"

    currentChanged = Signal(int)

    currentIndex = Prop(0, notify=True, signal="currentChanged", cast=int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages: list[QWidget] = []

    def addWidget(self, widget: QWidget) -> int:
        self._add_child(widget)
        self._pages.append(widget)
        return len(self._pages) - 1

    def currentWidget(self):
        idx = self.currentIndex()
        if 0 <= idx < len(self._pages):
            return self._pages[idx]
        return None

    def count(self) -> int:
        return len(self._pages)

    def widget(self, index: int):
        return self._pages[index] if 0 <= index < len(self._pages) else None

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["pageIds"] = [p._wid for p in self._pages]
        return props

    def _handle_event(self, event_type, value):
        if event_type == "currentChanged":
            self.setCurrentIndex(int(value))


class QSplitter(QWidget):
    _widget_type = "QSplitter"

    orientation = Prop(int(Qt.Horizontal), cast=int)

    def __init__(self, orientation=None, parent=None):
        super().__init__(parent)
        if orientation is not None:
            self.setOrientation(orientation)
        self._widgets: list[QWidget] = []
        self._sizes: list[int] = []

    def addWidget(self, widget: QWidget):
        self._add_child(widget)
        self._widgets.append(widget)

    def setSizes(self, sizes: list[int]):
        self._sizes = sizes

    def setHandleWidth(self, w: int):
        pass

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["widgetIds"] = [w._wid for w in self._widgets]
        props["sizes"] = self._sizes
        return props


class QDialog(QWidget):
    _widget_type = "QDialog"

    Accepted = 1
    Rejected = 0

    accepted = Signal()
    rejected = Signal()

    modal = Prop(True)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = QDialog.Rejected

    def exec(self) -> int:
        self.show()
        return self._result

    def exec_(self) -> int:
        return self.exec()

    def accept(self):
        self._result = QDialog.Accepted
        self.accepted.emit()
        self.hide()

    def reject(self):
        self._result = QDialog.Rejected
        self.rejected.emit()
        self.hide()


class QMessageBox(QDialog):
    _widget_type = "QMessageBox"

    # Button roles
    Ok = 0x00000400
    Cancel = 0x00400000
    Yes = 0x00004000
    No = 0x00010000
    Information = 1
    Warning = 2
    Critical = 3
    Question = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._informative_text = ""
        self._icon_type = 0

    def setText(self, text: str):
        self._text = text

    def setInformativeText(self, text: str):
        self._informative_text = text

    def setIcon(self, icon_type):
        self._icon_type = icon_type

    @staticmethod
    def information(parent, title, text, *args):
        print(f"[MessageBox Info] {title}: {text}")
        return QMessageBox.Ok

    @staticmethod
    def warning(parent, title, text, *args):
        print(f"[MessageBox Warning] {title}: {text}")
        return QMessageBox.Ok

    @staticmethod
    def critical(parent, title, text, *args):
        print(f"[MessageBox Error] {title}: {text}")
        return QMessageBox.Ok

    @staticmethod
    def question(parent, title, text, *args):
        print(f"[MessageBox Question] {title}: {text}")
        return QMessageBox.Yes

