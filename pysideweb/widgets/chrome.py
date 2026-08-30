"""pysideweb.widgets.chrome - QAction, menus, toolbar, status bar."""

from __future__ import annotations

from ..core import (
    Prop,
    QIcon,
    QObject,
    Signal,
    _register_props,
)
from .base import QWidget


class QAction(QObject):
    triggered = Signal()
    toggled = Signal(bool)

    text = Prop("")
    enabled = Prop(True, getter="isEnabled")
    checkable = Prop(False, getter="isCheckable")
    checked = Prop(False, getter="isChecked")

    def __init__(self, *args, parent=None):
        # Qt overloads: QAction(parent) | QAction(text[, parent])
        #             | QAction(icon, text[, parent])
        self._props: dict = {name: p.default for name, p in self._declared_props.items()}
        icon = QIcon()
        text = ""
        rest = list(args)
        if rest and isinstance(rest[0], QIcon):
            icon = rest.pop(0)
        if rest and isinstance(rest[0], str):
            text = rest.pop(0)
        if rest and parent is None:  # trailing QObject* parent
            parent = rest.pop(0)
        QObject.__init__(self, parent)
        self._props["text"] = text
        self._icon = icon
        self._shortcut = ""
        self._parent = parent

    def trigger(self):
        if self.isCheckable():
            self.setChecked(not self.isChecked())
            self.toggled.emit(self.isChecked())
        self.triggered.emit()

    def setChecked(self, checked: bool):
        self._raw_set_checked(bool(checked))
        self.toggled.emit(bool(checked))

    def setShortcut(self, shortcut):
        self._shortcut = str(shortcut)

    def setIcon(self, icon):
        self._icon = icon


_register_props(QAction)

class QMenu(QWidget):
    _widget_type = "QMenu"

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._actions: list[QAction] = []

    def addAction(self, *args) -> QAction:
        if args and isinstance(args[0], QAction):
            action = args[0]
        else:
            action = QAction(*args)
        self._actions.append(action)
        return action

    def addSeparator(self):
        pass

    def addMenu(self, *args):
        if args and isinstance(args[0], QMenu):
            return args[0]
        menu = QMenu(args[0] if args else "", self)
        return menu

    def title(self) -> str:
        return self._title

class QMenuBar(QWidget):
    _widget_type = "QMenuBar"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._menus: list[QMenu] = []

    def addMenu(self, *args) -> QMenu:
        if args and isinstance(args[0], QMenu):
            menu = args[0]
        else:
            menu = QMenu(args[0] if args else "", self)
        self._menus.append(menu)
        return menu

    def addAction(self, *args) -> QAction:
        action = QAction(*args)
        return action

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["menus"] = [
            {"title": m._title, "actions": [a.text() for a in m._actions]}
            for m in self._menus
        ]
        return props

class QToolBar(QWidget):
    _widget_type = "QToolBar"

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._actions: list[QAction] = []

    def addAction(self, *args) -> QAction:
        action = QAction(*args)
        self._actions.append(action)
        return action

    def addSeparator(self):
        pass

    def addWidget(self, widget):
        self._add_child(widget)

    def setMovable(self, movable: bool):
        pass

    def setToolButtonStyle(self, style):
        pass

class QStatusBar(QWidget):
    _widget_type = "QStatusBar"

    message = Prop("", notify=True)

    def showMessage(self, msg: str, timeout: int = 0):
        self.setMessage(msg)

    def clearMessage(self):
        self.setMessage("")

    def addWidget(self, widget, stretch: int = 0):
        self._add_child(widget)

    def addPermanentWidget(self, widget, stretch: int = 0):
        self.addWidget(widget, stretch)

