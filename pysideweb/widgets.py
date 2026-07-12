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
    BoundSignal,
    QFont,
    QIcon,
    QSize,
    Qt,
    Signal,
)

# ---------------------------------------------------------------------------
# Base: QWidget
# ---------------------------------------------------------------------------

class QWidget:
    """Virtual QWidget — base class for all virtual widgets."""

    _widget_type = "QWidget"

    def __init__(self, parent=None, flags=None):
        self._wid: str = state.register_widget(self)
        self._parent = parent
        self._children: list[QWidget] = []
        self._layout = None
        self._parent_layout = None
        self._visible = True
        self._enabled = True
        self._object_name = ""
        self._style_sheet = ""
        self._tooltip = ""
        self._min_size = QSize(0, 0)
        self._max_size = QSize(16777215, 16777215)
        self._fixed_size = None
        self._size_hint = QSize(-1, -1)
        self._font = QFont()
        self._cursor = None
        self._window_title = ""
        self._geometry = (0, 0, 640, 480)
        self._focus_policy = 0
        self._extra_classes: list[str] = []
        self._custom_props: dict[str, Any] = {}

        if parent is not None and hasattr(parent, '_children'):
            parent._children.append(self)

    # -- Identification --
    def objectName(self) -> str:
        return self._object_name

    def setObjectName(self, name: str):
        self._object_name = name
        self._notify("objectName", name)

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
    def setStyleSheet(self, css: str):
        self._style_sheet = css
        self._notify("styleSheet", css)

    def styleSheet(self) -> str:
        return self._style_sheet

    def setFont(self, font: QFont):
        self._font = font
        self._notify("font", font.to_css())

    def font(self) -> QFont:
        return self._font

    def setToolTip(self, tip: str):
        self._tooltip = tip

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
    def setWindowTitle(self, title: str):
        self._window_title = title
        self._notify("windowTitle", title)

    def windowTitle(self) -> str:
        return self._window_title

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

    def findChild(self, type_=None, name: str = ""):
        for child in self._children:
            if name and child._object_name == name:
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
            "objectName": self._object_name,
            "styleSheet": self._style_sheet,
            "tooltip": self._tooltip,
            "windowTitle": self._window_title,
            "extraClasses": self._extra_classes,
        }
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
        widget._parent = self
        if widget not in self._children:
            self._children.append(widget)
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame_shape = QFrame.NoFrame
        self._frame_shadow = QFrame.Plain
        self._line_width = 1

    def setFrameShape(self, shape: int):
        self._frame_shape = shape

    def setFrameShadow(self, shadow: int):
        self._frame_shadow = shadow

    def setLineWidth(self, w: int):
        self._line_width = w

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["frameShape"] = self._frame_shape
        props["frameShadow"] = self._frame_shadow
        return props


# ---------------------------------------------------------------------------
# QPushButton
# ---------------------------------------------------------------------------

class QPushButton(QWidget):
    _widget_type = "QPushButton"

    clicked = Signal()

    def __init__(self, text: str = "", parent=None, icon=None):
        super().__init__(parent)
        self._text = text
        self._icon = icon or QIcon()
        self._checkable = False
        self._checked = False
        self._flat = False
        self._auto_default = False
        # Bound signal
        self._signal_clicked = BoundSignal(QPushButton.clicked, self)

    @property
    def clicked(self):
        return self._signal_clicked

    @clicked.setter
    def clicked(self, v):
        pass

    def text(self) -> str:
        return self._text

    def setText(self, text: str):
        self._text = text
        self._notify("text", text)

    def setIcon(self, icon):
        self._icon = icon
        self._notify("icon", icon.text() if hasattr(icon, 'text') else str(icon))

    def icon(self):
        return self._icon

    def setCheckable(self, checkable: bool):
        self._checkable = checkable

    def isCheckable(self) -> bool:
        return self._checkable

    def setChecked(self, checked: bool):
        self._checked = checked
        self._notify("checked", checked)

    def isChecked(self) -> bool:
        return self._checked

    def setFlat(self, flat: bool):
        self._flat = flat

    def setDefault(self, default: bool):
        self._auto_default = default

    def setAutoDefault(self, auto: bool):
        self._auto_default = auto

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["text"] = self._text
        props["checkable"] = self._checkable
        props["checked"] = self._checked
        props["flat"] = self._flat
        if self._icon and not self._icon.isNull():
            props["icon"] = self._icon.text()
        return props

    def _handle_event(self, event_type, value):
        if event_type == "clicked":
            if self._checkable:
                self._checked = not self._checked
            self._signal_clicked.emit(self._checked if self._checkable else False)


# ---------------------------------------------------------------------------
# QLabel
# ---------------------------------------------------------------------------

class QLabel(QWidget):
    _widget_type = "QLabel"

    linkActivated = Signal(str)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._text = text
        self._alignment = 0
        self._word_wrap = False
        self._pixmap = None
        self._text_format = 0  # PlainText
        self._indent = -1
        self._margin = 0
        self._buddy = None
        self._scaled_contents = False
        self._signal_linkActivated = BoundSignal(QLabel.linkActivated, self)

    @property
    def linkActivated(self):
        return self._signal_linkActivated

    @linkActivated.setter
    def linkActivated(self, v):
        pass

    def text(self) -> str:
        return self._text

    def setText(self, text: str):
        self._text = text
        self._notify("text", text)

    def setAlignment(self, alignment):
        self._alignment = int(alignment)

    def alignment(self):
        return self._alignment

    def setWordWrap(self, wrap: bool):
        self._word_wrap = wrap

    def wordWrap(self) -> bool:
        return self._word_wrap

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

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["text"] = self._text
        props["alignment"] = self._alignment
        props["wordWrap"] = self._word_wrap
        return props


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

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._text = text
        self._placeholder = ""
        self._read_only = False
        self._max_length = 32767
        self._echo_mode = QLineEdit.EchoMode.Normal
        self._clear_button = False
        self._signal_textChanged = BoundSignal(QLineEdit.textChanged, self)
        self._signal_returnPressed = BoundSignal(QLineEdit.returnPressed, self)
        self._signal_editingFinished = BoundSignal(QLineEdit.editingFinished, self)

    @property
    def textChanged(self):
        return self._signal_textChanged

    @textChanged.setter
    def textChanged(self, v):
        pass

    @property
    def returnPressed(self):
        return self._signal_returnPressed

    @returnPressed.setter
    def returnPressed(self, v):
        pass

    @property
    def editingFinished(self):
        return self._signal_editingFinished

    @editingFinished.setter
    def editingFinished(self, v):
        pass

    def text(self) -> str:
        return self._text

    def setText(self, text: str):
        self._text = text
        self._notify("text", text)

    def setPlaceholderText(self, text: str):
        self._placeholder = text

    def placeholderText(self) -> str:
        return self._placeholder

    def setReadOnly(self, ro: bool):
        self._read_only = ro

    def isReadOnly(self) -> bool:
        return self._read_only

    def setMaxLength(self, length: int):
        self._max_length = length

    def setEchoMode(self, mode: int):
        self._echo_mode = mode

    def setClearButtonEnabled(self, enabled: bool):
        self._clear_button = enabled

    def clear(self):
        self.setText("")

    def selectAll(self):
        pass

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["text"] = self._text
        props["placeholder"] = self._placeholder
        props["readOnly"] = self._read_only
        props["echoMode"] = self._echo_mode
        props["clearButton"] = self._clear_button
        return props

    def _handle_event(self, event_type, value):
        if event_type == "textChanged":
            # Update local value without triggering a server-to-client notify broadcast
            self._text = value
            self._signal_textChanged.emit(value)
        elif event_type == "returnPressed":
            self._signal_returnPressed.emit()
        elif event_type == "editingFinished":
            self._signal_editingFinished.emit()


# ---------------------------------------------------------------------------
# QTextEdit
# ---------------------------------------------------------------------------

class QTextEdit(QWidget):
    _widget_type = "QTextEdit"

    textChanged = Signal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._text = text
        self._html = ""
        self._read_only = False
        self._placeholder = ""
        self._signal_textChanged = BoundSignal(QTextEdit.textChanged, self)

    @property
    def textChanged(self):
        return self._signal_textChanged

    @textChanged.setter
    def textChanged(self, v):
        pass

    def toPlainText(self) -> str:
        return self._text

    def setPlainText(self, text: str):
        self._text = text
        self._notify("text", text)

    def setText(self, text: str):
        self.setPlainText(text)

    def toHtml(self) -> str:
        return self._html

    def setHtml(self, html: str):
        self._html = html
        self._notify("html", html)

    def setReadOnly(self, ro: bool):
        self._read_only = ro

    def setPlaceholderText(self, text: str):
        self._placeholder = text

    def append(self, text: str):
        self._text += "\n" + text
        self._notify("text", self._text)

    def clear(self):
        self._text = ""
        self._html = ""
        self._notify("text", "")

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["text"] = self._text
        props["readOnly"] = self._read_only
        props["placeholder"] = self._placeholder
        return props

    def _handle_event(self, event_type, value):
        if event_type == "textChanged":
            self._text = value
            self._signal_textChanged.emit()


# ---------------------------------------------------------------------------
# QComboBox
# ---------------------------------------------------------------------------

class QComboBox(QWidget):
    _widget_type = "QComboBox"

    currentIndexChanged = Signal(int)
    currentTextChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[str] = []
        self._current_index = -1
        self._editable = False
        self._signal_currentIndexChanged = BoundSignal(QComboBox.currentIndexChanged, self)
        self._signal_currentTextChanged = BoundSignal(QComboBox.currentTextChanged, self)

    @property
    def currentIndexChanged(self):
        return self._signal_currentIndexChanged

    @currentIndexChanged.setter
    def currentIndexChanged(self, v):
        pass

    @property
    def currentTextChanged(self):
        return self._signal_currentTextChanged

    @currentTextChanged.setter
    def currentTextChanged(self, v):
        pass

    def addItem(self, text: str, data=None):
        self._items.append(text)
        if self._current_index < 0:
            self._current_index = 0
        self._notify("items", self._items)

    def addItems(self, texts: list[str]):
        for t in texts:
            self._items.append(t)
        if self._current_index < 0 and self._items:
            self._current_index = 0
        self._notify("items", self._items)

    def insertItem(self, index: int, text: str):
        self._items.insert(index, text)

    def removeItem(self, index: int):
        if 0 <= index < len(self._items):
            self._items.pop(index)
            if self._current_index >= len(self._items):
                self._current_index = len(self._items) - 1

    def clear(self):
        self._items.clear()
        self._current_index = -1
        self._notify("items", [])

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, idx: int):
        self._current_index = idx
        self._notify("currentIndex", idx)

    def currentText(self) -> str:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
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
        props["currentIndex"] = self._current_index
        props["editable"] = self._editable
        return props

    def _handle_event(self, event_type, value):
        if event_type == "currentIndexChanged":
            idx = int(value)
            self._current_index = idx
            self._signal_currentIndexChanged.emit(idx)
            self._signal_currentTextChanged.emit(self.currentText())


# ---------------------------------------------------------------------------
# QCheckBox
# ---------------------------------------------------------------------------

class QCheckBox(QWidget):
    _widget_type = "QCheckBox"

    stateChanged = Signal(int)
    toggled = Signal(bool)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._text = text
        self._checked = False
        self._tristate = False
        self._signal_stateChanged = BoundSignal(QCheckBox.stateChanged, self)
        self._signal_toggled = BoundSignal(QCheckBox.toggled, self)

    @property
    def stateChanged(self):
        return self._signal_stateChanged

    @stateChanged.setter
    def stateChanged(self, v):
        pass

    @property
    def toggled(self):
        return self._signal_toggled

    @toggled.setter
    def toggled(self, v):
        pass

    def text(self) -> str:
        return self._text

    def setText(self, text: str):
        self._text = text
        self._notify("text", text)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        self._checked = checked
        self._notify("checked", checked)

    def checkState(self):
        return Qt.Checked if self._checked else Qt.Unchecked

    def setTristate(self, tri: bool):
        self._tristate = tri

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["text"] = self._text
        props["checked"] = self._checked
        return props

    def _handle_event(self, event_type, value):
        if event_type == "toggled":
            self._checked = bool(value)
            self._signal_stateChanged.emit(2 if self._checked else 0)
            self._signal_toggled.emit(self._checked)


# ---------------------------------------------------------------------------
# QRadioButton
# ---------------------------------------------------------------------------

class QRadioButton(QWidget):
    _widget_type = "QRadioButton"

    toggled = Signal(bool)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._text = text
        self._checked = False
        self._signal_toggled = BoundSignal(QRadioButton.toggled, self)

    @property
    def toggled(self):
        return self._signal_toggled

    @toggled.setter
    def toggled(self, v):
        pass

    def text(self) -> str:
        return self._text

    def setText(self, text: str):
        self._text = text

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        self._checked = checked
        self._notify("checked", checked)

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["text"] = self._text
        props["checked"] = self._checked
        return props

    def _handle_event(self, event_type, value):
        if event_type == "toggled":
            self._checked = bool(value)
            self._signal_toggled.emit(self._checked)


# ---------------------------------------------------------------------------
# QSlider
# ---------------------------------------------------------------------------

class QSlider(QWidget):
    _widget_type = "QSlider"

    valueChanged = Signal(int)
    sliderMoved = Signal(int)

    def __init__(self, orientation=None, parent=None):
        super().__init__(parent)
        self._orientation = orientation or Qt.Horizontal
        self._value = 0
        self._minimum = 0
        self._maximum = 99
        self._single_step = 1
        self._page_step = 10
        self._tick_position = 0
        self._tick_interval = 0
        self._signal_valueChanged = BoundSignal(QSlider.valueChanged, self)
        self._signal_sliderMoved = BoundSignal(QSlider.sliderMoved, self)

    @property
    def valueChanged(self):
        return self._signal_valueChanged

    @valueChanged.setter
    def valueChanged(self, v):
        pass

    @property
    def sliderMoved(self):
        return self._signal_sliderMoved

    @sliderMoved.setter
    def sliderMoved(self, v):
        pass

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        new = max(self._minimum, min(self._maximum, val))
        changed = new != self._value
        self._value = new
        self._notify("value", self._value)
        if changed:  # match Qt: programmatic setValue emits valueChanged
            self._signal_valueChanged.emit(self._value)

    def minimum(self) -> int:
        return self._minimum

    def setMinimum(self, val: int):
        self._minimum = val

    def maximum(self) -> int:
        return self._maximum

    def setMaximum(self, val: int):
        self._maximum = val

    def setRange(self, min_val: int, max_val: int):
        self._minimum = min_val
        self._maximum = max_val

    def setSingleStep(self, step: int):
        self._single_step = step

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
        props["value"] = self._value
        props["minimum"] = self._minimum
        props["maximum"] = self._maximum
        props["orientation"] = int(self._orientation)
        props["singleStep"] = self._single_step
        return props

    def _handle_event(self, event_type, value):
        if event_type == "valueChanged":
            self._value = int(value)
            self._signal_valueChanged.emit(self._value)
            self._signal_sliderMoved.emit(self._value)


# ---------------------------------------------------------------------------
# QProgressBar
# ---------------------------------------------------------------------------

class QProgressBar(QWidget):
    _widget_type = "QProgressBar"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._minimum = 0
        self._maximum = 100
        self._text_visible = True
        self._format = "%p%"
        self._orientation = Qt.Horizontal

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        self._value = val
        self._notify("value", val)

    def minimum(self) -> int:
        return self._minimum

    def setMinimum(self, val: int):
        self._minimum = val

    def maximum(self) -> int:
        return self._maximum

    def setMaximum(self, val: int):
        self._maximum = val

    def setRange(self, min_val: int, max_val: int):
        self._minimum = min_val
        self._maximum = max_val

    def setTextVisible(self, visible: bool):
        self._text_visible = visible

    def setFormat(self, fmt: str):
        self._format = fmt

    def setOrientation(self, orientation):
        self._orientation = orientation

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["value"] = self._value
        props["minimum"] = self._minimum
        props["maximum"] = self._maximum
        props["textVisible"] = self._text_visible
        props["format"] = self._format
        return props


# ---------------------------------------------------------------------------
# QSpinBox / QDoubleSpinBox
# ---------------------------------------------------------------------------

class QSpinBox(QWidget):
    _widget_type = "QSpinBox"

    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._minimum = 0
        self._maximum = 99
        self._single_step = 1
        self._prefix = ""
        self._suffix = ""
        self._signal_valueChanged = BoundSignal(QSpinBox.valueChanged, self)

    @property
    def valueChanged(self):
        return self._signal_valueChanged

    @valueChanged.setter
    def valueChanged(self, v):
        pass

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        new = max(self._minimum, min(self._maximum, val))
        changed = new != self._value
        self._value = new
        self._notify("value", self._value)
        if changed:  # match Qt: programmatic setValue emits valueChanged
            self._signal_valueChanged.emit(self._value)

    def minimum(self) -> int:
        return self._minimum

    def setMinimum(self, val: int):
        self._minimum = val

    def maximum(self) -> int:
        return self._maximum

    def setMaximum(self, val: int):
        self._maximum = val

    def setRange(self, min_val: int, max_val: int):
        self._minimum = min_val
        self._maximum = max_val

    def setSingleStep(self, step: int):
        self._single_step = step

    def setPrefix(self, prefix: str):
        self._prefix = prefix

    def setSuffix(self, suffix: str):
        self._suffix = suffix

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["value"] = self._value
        props["minimum"] = self._minimum
        props["maximum"] = self._maximum
        props["singleStep"] = self._single_step
        props["prefix"] = self._prefix
        props["suffix"] = self._suffix
        return props

    def _handle_event(self, event_type, value):
        if event_type == "valueChanged":
            self._value = int(value)
            self._signal_valueChanged.emit(self._value)


class QDoubleSpinBox(QSpinBox):
    _widget_type = "QDoubleSpinBox"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._decimals = 2
        self._value = 0.0

    def setDecimals(self, decimals: int):
        self._decimals = decimals

    def setValue(self, val: float):
        self._value = max(self._minimum, min(self._maximum, val))
        self._notify("value", self._value)

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["decimals"] = self._decimals
        props["step"] = self._single_step
        return props

    def _handle_event(self, event_type, value):
        if event_type == "valueChanged":
            self._value = float(value)
            self._signal_valueChanged.emit(self._value)


# ---------------------------------------------------------------------------
# QTabWidget
# ---------------------------------------------------------------------------

class QTabWidget(QWidget):
    _widget_type = "QTabWidget"

    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs: list[dict] = []  # [{text, icon, widget}]
        self._current_index = 0
        self._tab_position = 0  # North
        self._signal_currentChanged = BoundSignal(QTabWidget.currentChanged, self)

    @property
    def currentChanged(self):
        return self._signal_currentChanged

    @currentChanged.setter
    def currentChanged(self, v):
        pass

    def addTab(self, widget: QWidget, *args) -> int:
        icon = None
        text = ""
        if len(args) == 1:
            text = args[0]
        elif len(args) == 2:
            icon = args[0]
            text = args[1]
        tab = {"text": text, "icon": icon, "widget": widget}
        widget._parent = self
        if widget not in self._children:
            self._children.append(widget)
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
            if self._current_index >= len(self._tabs):
                self._current_index = max(0, len(self._tabs) - 1)

    def setCurrentIndex(self, index: int):
        self._current_index = index
        self._notify("currentIndex", index)
        self._signal_currentChanged.emit(index)

    def currentIndex(self) -> int:
        return self._current_index

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
        props["currentIndex"] = self._current_index
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

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._checkable = False
        self._checked = True
        self._signal_toggled = BoundSignal(QGroupBox.toggled, self)

    @property
    def toggled(self):
        return self._signal_toggled

    @toggled.setter
    def toggled(self, v):
        pass

    def title(self) -> str:
        return self._title

    def setTitle(self, title: str):
        self._title = title
        self._notify("title", title)

    def setCheckable(self, checkable: bool):
        self._checkable = checkable

    def isCheckable(self) -> bool:
        return self._checkable

    def setChecked(self, checked: bool):
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["title"] = self._title
        props["checkable"] = self._checkable
        props["checked"] = self._checked
        return props


# ---------------------------------------------------------------------------
# QScrollArea
# ---------------------------------------------------------------------------

class QScrollArea(QWidget):
    _widget_type = "QScrollArea"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widget_inside = None
        self._widget_resizable = True

    def setWidget(self, widget: QWidget):
        self._widget_inside = widget
        widget._parent = self
        if widget not in self._children:
            self._children.append(widget)

    def widget(self):
        return self._widget_inside

    def setWidgetResizable(self, resizable: bool):
        self._widget_resizable = resizable

    def setHorizontalScrollBarPolicy(self, policy):
        pass

    def setVerticalScrollBarPolicy(self, policy):
        pass

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["widgetResizable"] = self._widget_resizable
        if self._widget_inside:
            props["innerWidgetId"] = self._widget_inside._wid
        return props


# ---------------------------------------------------------------------------
# QStackedWidget
# ---------------------------------------------------------------------------

class QStackedWidget(QWidget):
    _widget_type = "QStackedWidget"

    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages: list[QWidget] = []
        self._current_index = 0
        self._signal_currentChanged = BoundSignal(QStackedWidget.currentChanged, self)

    @property
    def currentChanged(self):
        return self._signal_currentChanged

    @currentChanged.setter
    def currentChanged(self, v):
        pass

    def addWidget(self, widget: QWidget) -> int:
        widget._parent = self
        self._pages.append(widget)
        if widget not in self._children:
            self._children.append(widget)
        return len(self._pages) - 1

    def setCurrentIndex(self, index: int):
        self._current_index = index
        self._notify("currentIndex", index)
        self._signal_currentChanged.emit(index)

    def currentIndex(self) -> int:
        return self._current_index

    def currentWidget(self):
        if 0 <= self._current_index < len(self._pages):
            return self._pages[self._current_index]
        return None

    def count(self) -> int:
        return len(self._pages)

    def widget(self, index: int):
        return self._pages[index] if 0 <= index < len(self._pages) else None

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["currentIndex"] = self._current_index
        props["pageIds"] = [p._wid for p in self._pages]
        return props

    def _handle_event(self, event_type, value):
        if event_type == "currentChanged":
            self.setCurrentIndex(int(value))


# ---------------------------------------------------------------------------
# QListWidget
# ---------------------------------------------------------------------------

class QListWidgetItem:
    def __init__(self, text: str = "", parent=None):
        self._text = text
        self._icon = QIcon()
        self._selected = False
        self._data: dict = {}
        self._flags = 0
        self._font = QFont()
        self._foreground = None
        self._background = None
        if parent is not None:
            parent.addItem(self)

    def text(self) -> str:
        return self._text

    def setText(self, text: str):
        self._text = text

    def setIcon(self, icon):
        self._icon = icon

    def icon(self):
        return self._icon

    def setSelected(self, selected: bool):
        self._selected = selected

    def isSelected(self) -> bool:
        return self._selected

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
        d = {"text": self._text}
        if self._icon and not self._icon.isNull():
            d["icon"] = self._icon.text()
        if self._selected:
            d["selected"] = True
        return d


class QListWidget(QWidget):
    _widget_type = "QListWidget"

    currentRowChanged = Signal(int)
    itemClicked = Signal(object)
    itemDoubleClicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[QListWidgetItem] = []
        self._current_row = -1
        self._signal_currentRowChanged = BoundSignal(QListWidget.currentRowChanged, self)
        self._signal_itemClicked = BoundSignal(QListWidget.itemClicked, self)

    @property
    def currentRowChanged(self):
        return self._signal_currentRowChanged

    @currentRowChanged.setter
    def currentRowChanged(self, v):
        pass

    @property
    def itemClicked(self):
        return self._signal_itemClicked

    @itemClicked.setter
    def itemClicked(self, v):
        pass

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
        self._current_row = -1
        self._notify("items", [])

    def count(self) -> int:
        return len(self._items)

    def item(self, row: int):
        return self._items[row] if 0 <= row < len(self._items) else None

    def currentRow(self) -> int:
        return self._current_row

    def setCurrentRow(self, row: int):
        self._current_row = row
        self._notify("currentRow", row)

    def currentItem(self):
        return self.item(self._current_row)

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
        props["currentRow"] = self._current_row
        return props

    def _handle_event(self, event_type, value):
        if event_type == "currentRowChanged":
            row = int(value)
            self._current_row = row
            self._signal_currentRowChanged.emit(row)
            if 0 <= row < len(self._items):
                self._signal_itemClicked.emit(self._items[row])


# ---------------------------------------------------------------------------
# QSplitter
# ---------------------------------------------------------------------------

class QSplitter(QWidget):
    _widget_type = "QSplitter"

    def __init__(self, orientation=None, parent=None):
        super().__init__(parent)
        self._orientation = orientation or Qt.Horizontal
        self._widgets: list[QWidget] = []
        self._sizes: list[int] = []

    def addWidget(self, widget: QWidget):
        widget._parent = self
        self._widgets.append(widget)
        if widget not in self._children:
            self._children.append(widget)

    def setSizes(self, sizes: list[int]):
        self._sizes = sizes

    def setOrientation(self, orientation):
        self._orientation = orientation

    def setHandleWidth(self, w: int):
        pass

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["orientation"] = int(self._orientation)
        props["widgetIds"] = [w._wid for w in self._widgets]
        props["sizes"] = self._sizes
        return props


# ---------------------------------------------------------------------------
# QMenuBar / QMenu / QAction / QToolBar / QStatusBar (stubs)
# ---------------------------------------------------------------------------

class QAction:
    triggered = Signal()

    def __init__(self, *args, parent=None):
        self._text = args[0] if args and isinstance(args[0], str) else ""
        if len(args) > 1 and isinstance(args[0], (QIcon, str)):
            self._text = args[1] if len(args) > 1 else ""
        self._icon = QIcon()
        self._enabled = True
        self._checkable = False
        self._checked = False
        self._shortcut = ""
        self._signal_triggered = BoundSignal(QAction.triggered, self)
        self._parent = parent

    @property
    def triggered(self):
        return self._signal_triggered

    @triggered.setter
    def triggered(self, v):
        pass

    def setText(self, text: str):
        self._text = text

    def text(self) -> str:
        return self._text

    def setEnabled(self, enabled: bool):
        self._enabled = enabled

    def setCheckable(self, checkable: bool):
        self._checkable = checkable

    def setChecked(self, checked: bool):
        self._checked = checked

    def setShortcut(self, shortcut):
        self._shortcut = str(shortcut)

    def setIcon(self, icon):
        self._icon = icon


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
            {"title": m._title, "actions": [a._text for a in m._actions]}
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
        if widget not in self._children:
            self._children.append(widget)

    def setMovable(self, movable: bool):
        pass

    def setToolButtonStyle(self, style):
        pass


class QStatusBar(QWidget):
    _widget_type = "QStatusBar"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._message = ""

    def showMessage(self, msg: str, timeout: int = 0):
        self._message = msg
        self._notify("message", msg)

    def clearMessage(self):
        self._message = ""
        self._notify("message", "")

    def addWidget(self, widget, stretch: int = 0):
        if widget not in self._children:
            self._children.append(widget)

    def addPermanentWidget(self, widget, stretch: int = 0):
        self.addWidget(widget, stretch)

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["message"] = self._message
        return props


# ---------------------------------------------------------------------------
# QDialog
# ---------------------------------------------------------------------------

class QDialog(QWidget):
    _widget_type = "QDialog"

    Accepted = 1
    Rejected = 0

    accepted = Signal()
    rejected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = QDialog.Rejected
        self._modal = True
        self._signal_accepted = BoundSignal(QDialog.accepted, self)
        self._signal_rejected = BoundSignal(QDialog.rejected, self)

    @property
    def accepted(self):
        return self._signal_accepted

    @accepted.setter
    def accepted(self, v):
        pass

    @property
    def rejected(self):
        return self._signal_rejected

    @rejected.setter
    def rejected(self, v):
        pass

    def exec(self) -> int:
        self.show()
        return self._result

    def exec_(self) -> int:
        return self.exec()

    def accept(self):
        self._result = QDialog.Accepted
        self._signal_accepted.emit()
        self.hide()

    def reject(self):
        self._result = QDialog.Rejected
        self._signal_rejected.emit()
        self.hide()

    def setModal(self, modal: bool):
        self._modal = modal

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["modal"] = self._modal
        return props


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
        self._signal_buttonClicked = BoundSignal(QButtonGroup.buttonClicked, self)

    @property
    def buttonClicked(self):
        return self._signal_buttonClicked

    @buttonClicked.setter
    def buttonClicked(self, v):
        pass

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
