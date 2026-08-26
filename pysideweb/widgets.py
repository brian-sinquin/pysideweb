"""
pysideweb.widgets — Virtual widget classes that mirror PySide6.QtWidgets.

Each class stores its properties in Python dicts and notifies the state
module whenever a property changes, triggering a WebSocket broadcast
to connected browsers.
"""

from __future__ import annotations

from typing import Any

from . import state
from .core import (
    Prop,
    QFont,
    QIcon,
    QSize,
    Qt,
    Signal,
    _register_props,
)

# ---------------------------------------------------------------------------
# Base: QWidget
# ---------------------------------------------------------------------------

class QWidget:
    """Virtual QWidget — base class for all virtual widgets."""

    _widget_type = "QWidget"
    _declared_props: dict[str, Prop] = {}

    objectName = Prop("", notify=True)
    styleSheet = Prop("", notify=True)
    windowTitle = Prop("", notify=True)
    toolTip = Prop("", in_props=False)  # reported under the "tooltip" wire key below

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_props(cls)

    def __init__(self, parent=None, flags=None):
        self._wid: str = state.register_widget(self)
        self._parent = parent
        self._children: list[QWidget] = []
        self._layout = None
        self._parent_layout = None
        self._props: dict[str, Any] = {name: p.default for name, p in self._declared_props.items()}
        self._visible = True
        self._enabled = True
        self._min_size = QSize(0, 0)
        self._max_size = QSize(16777215, 16777215)
        self._fixed_size = None
        self._size_hint = QSize(-1, -1)
        self._font = QFont()
        self._cursor = None
        self._geometry = (0, 0, 640, 480)
        self._focus_policy = 0
        self._extra_classes: list[str] = []
        self._custom_props: dict[str, Any] = {}

        if parent is not None and hasattr(parent, '_children'):
            parent._children.append(self)

    def _reflective_props(self) -> dict:
        """Declared Prop values, for a subclass's _get_props() to merge in."""
        return {
            name: self._props.get(name, p.default)
            for name, p in self._declared_props.items()
            if p.in_props
        }

    # -- Visibility --
    def show(self):
        self._visible = True
        if self._parent is None:
            state.add_root(self)
        self._notify("visible", True)
        state.notify_full_refresh()

    def hide(self):
        self._visible = False
        self._notify("visible", False)
        state.notify_full_refresh()

    def setVisible(self, visible: bool):
        if visible:
            self.show()
        else:
            self.hide()

    def isVisible(self) -> bool:
        return self._visible

    def isHidden(self) -> bool:
        return not self._visible

    # -- Enable / Disable --
    def setEnabled(self, enabled: bool):
        self._enabled = enabled
        self._notify("enabled", enabled)

    def isEnabled(self) -> bool:
        return self._enabled

    def setDisabled(self, disabled: bool):
        self.setEnabled(not disabled)

    # -- Geometry --
    def setGeometry(self, x, y=None, w=None, h=None):
        if y is None:  # QRect overload
            r = x
            self._geometry = (r.x(), r.y(), r.width(), r.height())
        else:
            self._geometry = (x, y, w, h)

    def geometry(self):
        from .core import QRect
        return QRect(*self._geometry)

    def resize(self, w, h=None):
        if h is None:
            w, h = w.width(), w.height()
        self._geometry = (self._geometry[0], self._geometry[1], w, h)
        self._notify("geometry", list(self._geometry))

    def setFixedSize(self, w, h=None):
        if h is None:
            w, h = w.width(), w.height()
        self._fixed_size = (w, h)
        self._min_size = QSize(w, h)
        self._max_size = QSize(w, h)

    def setFixedWidth(self, w: int):
        self._min_size.setWidth(w)
        self._max_size.setWidth(w)

    def setFixedHeight(self, h: int):
        self._min_size.setHeight(h)
        self._max_size.setHeight(h)

    def setMinimumSize(self, w, h=None):
        if h is None:
            w, h = w.width(), w.height()
        self._min_size = QSize(w, h)

    def setMaximumSize(self, w, h=None):
        if h is None:
            w, h = w.width(), w.height()
        self._max_size = QSize(w, h)

    def setMinimumWidth(self, w: int):
        self._min_size.setWidth(w)

    def setMinimumHeight(self, h: int):
        self._min_size.setHeight(h)

    def setMaximumWidth(self, w: int):
        self._max_size.setWidth(w)

    def setMaximumHeight(self, h: int):
        self._max_size.setHeight(h)

    def minimumSizeHint(self):
        return self._min_size

    def sizeHint(self):
        return self._size_hint

    def width(self) -> int:
        return self._geometry[2]

    def height(self) -> int:
        return self._geometry[3]

    # -- Style --
    def setFont(self, font: QFont):
        self._font = font
        self._notify("font", font.to_css())

    def font(self) -> QFont:
        return self._font

    def setCursor(self, cursor):
        self._cursor = cursor

    # -- Focus --
    def setFocusPolicy(self, policy):
        self._focus_policy = policy

    def setFocus(self):
        pass

    # -- Layout --
    def setLayout(self, layout):
        self._layout = layout
        layout._parent = self
        state.notify_full_refresh()

    def layout(self):
        return self._layout

    # -- Window --
    def setWindowIcon(self, icon):
        pass

    def setWindowFlags(self, flags):
        pass

    # -- Parent/Child --
    def setParent(self, parent):
        if self._parent and hasattr(self._parent, '_children'):
            self._parent._children = [c for c in self._parent._children if c is not self]
        self._parent = parent
        if parent and hasattr(parent, '_children'):
            parent._children.append(self)

    def parent(self):
        return self._parent

    def children(self):
        return list(self._children)

    def _add_child(self, widget: QWidget):
        """Reparent `widget` under self and register it as a child, once.

        Shared by every container-ish addWidget()/setWidget()/addTab() —
        previously each repeated the same "set parent, append if absent"
        trio by hand.
        """
        widget._parent = self
        if widget not in self._children:
            self._children.append(widget)

    def findChild(self, type_=None, name: str = ""):
        for child in self._children:
            if name and child.objectName() == name:
                return child
            if type_ and isinstance(child, type_):
                return child
        return None

    # -- Deletions --
    def deleteLater(self):
        if self._parent and hasattr(self._parent, '_children'):
            self._parent._children = [c for c in self._parent._children if c is not self]
        state.unregister_widget(self._wid)
        state.notify_full_refresh()

    def close(self):
        self.hide()

    # -- Size policy (stub) --
    def setSizePolicy(self, *args, **kwargs):
        pass

    # -- Property helpers --
    def setProperty(self, name: str, value):
        self._custom_props[name] = value

    def property(self, name: str):
        return self._custom_props.get(name)

    def update(self):
        state.notify_full_refresh()

    def repaint(self):
        state.notify_full_refresh()

    # -- Internals --
    def _notify(self, prop: str, value: Any):
        state.notify_change(self._wid, prop, value)

    def _get_props(self) -> dict:
        props = {
            "visible": self._visible,
            "enabled": self._enabled,
            "tooltip": self.toolTip(),
            "extraClasses": self._extra_classes,
        }
        props.update(self._reflective_props())
        if self._font and self._font.family():
            props["font"] = self._font.to_css()
        if self._fixed_size:
            props["fixedSize"] = list(self._fixed_size)
        if self._min_size.width() > 0 or self._min_size.height() > 0:
            props["minSize"] = self._min_size.toTuple()
        if self._custom_props:
            props["customProps"] = self._custom_props
        return props

    def _handle_event(self, event_type: str, value: Any):
        """Handle events dispatched from the browser."""
        pass

# QWidget doesn't go through __init_subclass__ itself (that hook only fires
# for subclasses), so its own Prop() declarations are registered explicitly
# here, once.
_register_props(QWidget)

# ---------------------------------------------------------------------------
# QMainWindow
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# QFrame
# ---------------------------------------------------------------------------

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
    # `self._line_width`) — Prop gives it a matching getter for free.
    lineWidth = Prop(1)

# ---------------------------------------------------------------------------
# QPushButton
# ---------------------------------------------------------------------------

class QPushButton(QWidget):
    _widget_type = "QPushButton"

    clicked = Signal()

    text = Prop("", notify=True)
    checked = Prop(False, notify=True, getter="isChecked")
    checkable = Prop(False, getter="isCheckable")
    flat = Prop(False, getter="isFlat")

    def __init__(self, text: str = "", parent=None, icon=None):
        super().__init__(parent)
        self._props["text"] = text
        self._icon = icon or QIcon()
        self._auto_default = False

    def setIcon(self, icon):
        self._icon = icon
        self._notify("icon", icon.text() if hasattr(icon, 'text') else str(icon))

    def icon(self):
        return self._icon

    def setDefault(self, default: bool):
        self._auto_default = default

    def setAutoDefault(self, auto: bool):
        self._auto_default = auto

    def _get_props(self) -> dict:
        props = super()._get_props()
        if self._icon and not self._icon.isNull():
            props["icon"] = self._icon.text()
        return props

    def _handle_event(self, event_type, value):
        if event_type == "clicked":
            if self.isCheckable():
                self.setChecked(not self.isChecked())
            self.clicked.emit(self.isChecked() if self.isCheckable() else False)

# ---------------------------------------------------------------------------
# QLabel
# ---------------------------------------------------------------------------

class QLabel(QWidget):
    _widget_type = "QLabel"

    linkActivated = Signal(str)

    text = Prop("", notify=True)
    alignment = Prop(0, cast=int)
    wordWrap = Prop(False)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._props["text"] = text
        self._pixmap = None
        self._text_format = 0  # PlainText
        self._indent = -1
        self._margin = 0
        self._buddy = None
        self._scaled_contents = False

    def setPixmap(self, pixmap):
        self._pixmap = pixmap

    def setScaledContents(self, scaled: bool):
        self._scaled_contents = scaled

    def setTextInteractionFlags(self, flags):
        pass

    def setOpenExternalLinks(self, open_links: bool):
        pass

    def setBuddy(self, buddy):
        self._buddy = buddy

    def setIndent(self, indent: int):
        self._indent = indent

    def setMargin(self, margin: int):
        self._margin = margin

    def setTextFormat(self, fmt):
        self._text_format = fmt

# ---------------------------------------------------------------------------
# QLineEdit
# ---------------------------------------------------------------------------

class QLineEdit(QWidget):
    _widget_type = "QLineEdit"

    textChanged = Signal(str)
    returnPressed = Signal()
    editingFinished = Signal()

    class EchoMode:
        Normal = 0
        Password = 2
        NoEcho = 1
        PasswordEchoOnEdit = 3

    text = Prop("", notify=True)
    placeholder = Prop("", in_props=True)
    readOnly = Prop(False, getter="isReadOnly")
    echoMode = Prop(EchoMode.Normal)
    clearButton = Prop(False)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._props["text"] = text
        self._max_length = 32767

    def setPlaceholderText(self, text: str):
        self.setPlaceholder(text)

    def placeholderText(self) -> str:
        return self.placeholder()

    def setMaxLength(self, length: int):
        self._max_length = length

    def setClearButtonEnabled(self, enabled: bool):
        self.setClearButton(enabled)

    def clear(self):
        self.setText("")

    def selectAll(self):
        pass

    def _handle_event(self, event_type, value):
        if event_type == "textChanged":
            # Update local value without triggering a server-to-client notify broadcast
            self._props["text"] = value
            self.textChanged.emit(value)
        elif event_type == "returnPressed":
            self.returnPressed.emit()
        elif event_type == "editingFinished":
            self.editingFinished.emit()

# ---------------------------------------------------------------------------
# QTextEdit
# ---------------------------------------------------------------------------

class QTextEdit(QWidget):
    _widget_type = "QTextEdit"

    textChanged = Signal()

    plainText = Prop("", notify=True, in_props=False)  # exposed as "text" below
    html = Prop("", notify=True, in_props=False)  # not part of the wire payload (matches original)
    readOnly = Prop(False, getter="isReadOnly")
    placeholder = Prop("")

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._props["plainText"] = text

    def toPlainText(self) -> str:
        return self.plainText()

    def setText(self, text: str):
        self.setPlainText(text)

    def toHtml(self) -> str:
        return self.html()

    def setPlaceholderText(self, text: str):
        self.setPlaceholder(text)

    def append(self, text: str):
        self.setPlainText(self.plainText() + "\n" + text)

    def clear(self):
        self.setPlainText("")
        self.setHtml("")

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["text"] = self.plainText()
        return props

    def _handle_event(self, event_type, value):
        if event_type == "textChanged":
            # Mirror the browser's value without re-notifying it (avoids an echo).
            self._props["plainText"] = value
            self.textChanged.emit()

# ---------------------------------------------------------------------------
# QComboBox
# ---------------------------------------------------------------------------

class QComboBox(QWidget):
    _widget_type = "QComboBox"

    currentIndexChanged = Signal(int)
    currentTextChanged = Signal(str)

    # Was hand-tracked as `self._current_index` with a manual `_notify()` call
    # in every mutator plus a `currentIndexChanged.emit()` duplicated in
    # `_handle_event`; as a Prop, storage/notify/getter/setter are generated
    # and `currentIndexChanged` is emitted for free whenever the value
    # actually changes (previously only emitted from the browser-event path).
    currentIndex = Prop(-1, notify=True, signal="currentIndexChanged", cast=int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[str] = []
        self._editable = False

    def addItem(self, text: str, data=None):
        self._items.append(text)
        if self.currentIndex() < 0:
            self.setCurrentIndex(0)
        self._notify("items", self._items)

    def addItems(self, texts: list[str]):
        for t in texts:
            self._items.append(t)
        if self.currentIndex() < 0 and self._items:
            self.setCurrentIndex(0)
        self._notify("items", self._items)

    def insertItem(self, index: int, text: str):
        self._items.insert(index, text)

    def removeItem(self, index: int):
        if 0 <= index < len(self._items):
            self._items.pop(index)
            if self.currentIndex() >= len(self._items):
                self.setCurrentIndex(len(self._items) - 1)

    def clear(self):
        self._items.clear()
        self.setCurrentIndex(-1)
        self._notify("items", [])

    def currentText(self) -> str:
        idx = self.currentIndex()
        if 0 <= idx < len(self._items):
            return self._items[idx]
        return ""

    def setCurrentText(self, text: str):
        if text in self._items:
            self.setCurrentIndex(self._items.index(text))

    def count(self) -> int:
        return len(self._items)

    def itemText(self, index: int) -> str:
        return self._items[index] if 0 <= index < len(self._items) else ""

    def setEditable(self, editable: bool):
        self._editable = editable

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["items"] = self._items
        props["editable"] = self._editable
        return props

    def _handle_event(self, event_type, value):
        if event_type == "currentIndexChanged":
            self.setCurrentIndex(int(value))
            self.currentTextChanged.emit(self.currentText())

# ---------------------------------------------------------------------------
# QCheckBox
# ---------------------------------------------------------------------------

class QCheckBox(QWidget):
    _widget_type = "QCheckBox"

    stateChanged = Signal(int)
    toggled = Signal(bool)

    text = Prop("", notify=True)
    checked = Prop(False, notify=True, getter="isChecked")

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._props["text"] = text
        self._tristate = False

    def checkState(self):
        return Qt.Checked if self.isChecked() else Qt.Unchecked

    def setTristate(self, tri: bool):
        self._tristate = tri

    def _handle_event(self, event_type, value):
        if event_type == "toggled":
            self.setChecked(bool(value))
            self.stateChanged.emit(2 if self.isChecked() else 0)
            self.toggled.emit(self.isChecked())

# ---------------------------------------------------------------------------
# QRadioButton
# ---------------------------------------------------------------------------

class QRadioButton(QWidget):
    _widget_type = "QRadioButton"

    toggled = Signal(bool)

    text = Prop("", notify=True)
    checked = Prop(False, notify=True, getter="isChecked")

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._props["text"] = text

    def _handle_event(self, event_type, value):
        if event_type == "toggled":
            self.setChecked(bool(value))
            self.toggled.emit(self.isChecked())

# ---------------------------------------------------------------------------
# QSlider
# ---------------------------------------------------------------------------

class _RangedMixin:
    """Shared logic for widgets with a bounded, notify+signal `value` Prop
    (QSlider, QSpinBox, QDoubleSpinBox). Each still declares its own
    `value`/`minimum`/`maximum` Prop (so defaults/cast can differ), but the
    clamp-then-store-then-conditionally-emit rule — previously duplicated
    3 times, and silently *missing* on QDoubleSpinBox — is written once.
    """

    def setRange(self, min_val, max_val):
        self.setMinimum(min_val)
        self.setMaximum(max_val)

    def setValue(self, val):
        val = max(self.minimum(), min(self.maximum(), val))
        self._raw_set_value(val)

class QSlider(_RangedMixin, QWidget):
    _widget_type = "QSlider"

    valueChanged = Signal(int)
    sliderMoved = Signal(int)

    value = Prop(0, notify=True, signal="valueChanged")
    minimum = Prop(0)
    maximum = Prop(99)
    singleStep = Prop(1)

    def __init__(self, orientation=None, parent=None):
        super().__init__(parent)
        self._orientation = orientation or Qt.Horizontal
        self._page_step = 10
        self._tick_position = 0
        self._tick_interval = 0

    def setPageStep(self, step: int):
        self._page_step = step

    def setTickPosition(self, pos):
        self._tick_position = pos

    def setTickInterval(self, interval: int):
        self._tick_interval = interval

    def setOrientation(self, orientation):
        self._orientation = orientation

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["orientation"] = int(self._orientation)
        return props

    def _handle_event(self, event_type, value):
        if event_type == "valueChanged":
            self.setValue(int(value))
            self.sliderMoved.emit(self.value())

# ---------------------------------------------------------------------------
# QProgressBar
# ---------------------------------------------------------------------------

class QProgressBar(QWidget):
    _widget_type = "QProgressBar"

    # Note: unlike QSlider/QSpinBox, real QProgressBar.setValue() does not
    # clamp to [minimum, maximum] here — matches the pre-existing behavior.
    value = Prop(0, notify=True)
    minimum = Prop(0)
    maximum = Prop(100)
    textVisible = Prop(True)
    format = Prop("%p%")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orientation = Qt.Horizontal

    def setRange(self, min_val: int, max_val: int):
        self.setMinimum(min_val)
        self.setMaximum(max_val)

    def setOrientation(self, orientation):
        self._orientation = orientation

# ---------------------------------------------------------------------------
# QSpinBox / QDoubleSpinBox
# ---------------------------------------------------------------------------

class QSpinBox(_RangedMixin, QWidget):
    _widget_type = "QSpinBox"

    valueChanged = Signal(int)

    value = Prop(0, notify=True, signal="valueChanged", cast=int)
    minimum = Prop(0)
    maximum = Prop(99)
    singleStep = Prop(1)
    prefix = Prop("")
    suffix = Prop("")

    def _handle_event(self, event_type, value):
        if event_type == "valueChanged":
            self.setValue(int(value))

class QDoubleSpinBox(QSpinBox):
    _widget_type = "QDoubleSpinBox"

    # Redeclared with a float default/cast — everything else (clamping,
    # notify, conditional valueChanged emission) is inherited from
    # QSpinBox/_RangedMixin. The original hand-written override of this
    # setValue() never emitted valueChanged at all; going through the
    # shared engine fixes that for free.
    value = Prop(0.0, notify=True, signal="valueChanged", cast=float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._decimals = 2

    def setDecimals(self, decimals: int):
        self._decimals = decimals

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["decimals"] = self._decimals
        props["step"] = self.singleStep()
        return props

    def _handle_event(self, event_type, value):
        if event_type == "valueChanged":
            self.setValue(float(value))

# ---------------------------------------------------------------------------
# QTabWidget
# ---------------------------------------------------------------------------

class QTabWidget(QWidget):
    _widget_type = "QTabWidget"

    currentChanged = Signal(int)

    currentIndex = Prop(0, notify=True, signal="currentChanged", cast=int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs: list[dict] = []  # [{text, icon, widget}]
        self._tab_position = 0

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

    def setTabPosition(self, pos):
        self._tab_position = pos

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

# ---------------------------------------------------------------------------
# QGroupBox
# ---------------------------------------------------------------------------

class QGroupBox(QWidget):
    _widget_type = "QGroupBox"

    toggled = Signal(bool)

    title = Prop("", notify=True)
    checkable = Prop(False, getter="isCheckable")
    checked = Prop(True, getter="isChecked")

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._props["title"] = title

# ---------------------------------------------------------------------------
# QScrollArea
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# QStackedWidget
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# QListWidget
# ---------------------------------------------------------------------------

class QListWidgetItem:
    """Not a QWidget (no `_wid`/state registration), but its properties still
    follow the same declare-once shape, so `Prop` (with `notify=False`, the
    default) generates the accessors here too instead of hand-writing them."""

    text = Prop("")
    selected = Prop(False, getter="isSelected")

    def __init__(self, text: str = "", parent=None):
        self._props: dict = {name: p.default for name, p in self._declared_props.items()}
        self._props["text"] = text
        self._icon = QIcon()
        self._data: dict = {}
        self._flags = 0
        self._font = QFont()
        self._foreground = None
        self._background = None
        if parent is not None:
            parent.addItem(self)

    def setIcon(self, icon):
        self._icon = icon

    def icon(self):
        return self._icon

    def setData(self, role: int, value):
        self._data[role] = value

    def data(self, role: int):
        return self._data.get(role)

    def setFlags(self, flags):
        self._flags = flags

    def setFont(self, font):
        self._font = font

    def setForeground(self, brush):
        self._foreground = brush

    def setBackground(self, brush):
        self._background = brush

    def to_dict(self) -> dict:
        d = {"text": self.text()}
        if self._icon and not self._icon.isNull():
            d["icon"] = self._icon.text()
        if self.isSelected():
            d["selected"] = True
        return d


_register_props(QListWidgetItem)

class QListWidget(QWidget):
    _widget_type = "QListWidget"

    currentRowChanged = Signal(int)
    itemClicked = Signal(object)
    itemDoubleClicked = Signal(object)

    currentRow = Prop(-1, notify=True, signal="currentRowChanged", cast=int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[QListWidgetItem] = []

    def addItem(self, item):
        if isinstance(item, str):
            item = QListWidgetItem(item)
        self._items.append(item)
        self._notify("items", [i.to_dict() for i in self._items])

    def addItems(self, texts: list[str]):
        for t in texts:
            self._items.append(QListWidgetItem(t))
        self._notify("items", [i.to_dict() for i in self._items])

    def insertItem(self, row: int, item):
        if isinstance(item, str):
            item = QListWidgetItem(item)
        self._items.insert(row, item)

    def takeItem(self, row: int):
        if 0 <= row < len(self._items):
            return self._items.pop(row)

    def clear(self):
        self._items.clear()
        self.setCurrentRow(-1)
        self._notify("items", [])

    def count(self) -> int:
        return len(self._items)

    def item(self, row: int):
        return self._items[row] if 0 <= row < len(self._items) else None

    def currentItem(self):
        return self.item(self.currentRow())

    def row(self, item):
        try:
            return self._items.index(item)
        except ValueError:
            return -1

    def setAlternatingRowColors(self, alt: bool):
        pass

    def setSelectionMode(self, mode):
        pass

    def setSpacing(self, spacing: int):
        pass

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["items"] = [i.to_dict() for i in self._items]
        return props

    def _handle_event(self, event_type, value):
        if event_type == "currentRowChanged":
            row = int(value)
            self.setCurrentRow(row)
            if 0 <= row < len(self._items):
                self.itemClicked.emit(self._items[row])

# ---------------------------------------------------------------------------
# QSplitter
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# QMenuBar / QMenu / QAction / QToolBar / QStatusBar (stubs)
# ---------------------------------------------------------------------------

class QAction:
    triggered = Signal()

    text = Prop("")
    enabled = Prop(True, getter="isEnabled")
    checkable = Prop(False, getter="isCheckable")
    checked = Prop(False, getter="isChecked")

    def __init__(self, *args, parent=None):
        self._props: dict = {name: p.default for name, p in self._declared_props.items()}
        text = args[0] if args and isinstance(args[0], str) else ""
        if len(args) > 1 and isinstance(args[0], (QIcon, str)):
            text = args[1] if len(args) > 1 else ""
        self._props["text"] = text
        self._icon = QIcon()
        self._shortcut = ""
        self._parent = parent

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

# ---------------------------------------------------------------------------
# QDialog
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# QMessageBox (static methods)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# QButtonGroup
# ---------------------------------------------------------------------------

class QButtonGroup:
    buttonClicked = Signal(int)

    def __init__(self, parent=None):
        self._buttons: list[tuple[QWidget, int]] = []
        self._exclusive = True
        self._parent = parent

    def addButton(self, button, btn_id: int = -1):
        self._buttons.append((button, btn_id))

    def setExclusive(self, exclusive: bool):
        self._exclusive = exclusive

    def button(self, btn_id: int):
        for btn, bid in self._buttons:
            if bid == btn_id:
                return btn
        return None

    def checkedId(self) -> int:
        for btn, bid in self._buttons:
            if hasattr(btn, 'isChecked') and btn.isChecked():
                return bid
        return -1

# ---------------------------------------------------------------------------
# QSizePolicy
# ---------------------------------------------------------------------------

class QSizePolicy:
    Fixed = 0
    Minimum = 1
    Maximum = 4
    Preferred = 5
    Expanding = 7
    MinimumExpanding = 3
    Ignored = 13

    def __init__(self, h_policy=Preferred, v_policy=Preferred):
        self._h = h_policy
        self._v = v_policy

    def setHorizontalStretch(self, stretch: int):
        pass

    def setVerticalStretch(self, stretch: int):
        pass

# ---------------------------------------------------------------------------
# QSpacerItem / QWidgetItem
# ---------------------------------------------------------------------------

class QSpacerItem:
    def __init__(self, w=0, h=0, h_policy=QSizePolicy.Minimum, v_policy=QSizePolicy.Minimum):
        self._w = w
        self._h = h

class QWidgetItem:
    def __init__(self, widget):
        self._widget = widget
