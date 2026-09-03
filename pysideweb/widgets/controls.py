"""pysideweb.widgets.controls - buttons, text inputs, sliders, progress."""

from __future__ import annotations

from ..core import (
    Prop,
    QIcon,
    Qt,
    Signal,
    _register_props,
)
from .base import QWidget, _RangedMixin


class _TextWidget(QWidget):
    """Shared text property and constructor for text-bearing controls."""

    text = Prop("", notify=True)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._props["text"] = text


class QPushButton(_TextWidget):
    _widget_type = "QPushButton"

    clicked = Signal()

    checked = Prop(False, notify=True, getter="isChecked")
    checkable = Prop(False, getter="isCheckable")
    flat = Prop(False, getter="isFlat")

    def __init__(self, text: str = "", parent=None, icon=None):
        super().__init__(text, parent)
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


class QLabel(_TextWidget):
    _widget_type = "QLabel"

    linkActivated = Signal(str)

    alignment = Prop(0, cast=int)
    wordWrap = Prop(False)
    # None of these four had a getter in the hand-written version (only the
    # setter existed) â€” Prop adds one for free.
    scaledContents = Prop(False, getter="hasScaledContents")
    indent = Prop(-1)
    margin = Prop(0)
    textFormat = Prop(0)  # PlainText

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._pixmap = None
        self._buddy = None

    def setPixmap(self, pixmap):
        self._pixmap = pixmap

    def setTextInteractionFlags(self, flags):
        pass

    def setOpenExternalLinks(self, open_links: bool):
        pass

    def setBuddy(self, buddy):
        self._buddy = buddy


class QLineEdit(_TextWidget):
    _widget_type = "QLineEdit"

    textChanged = Signal(str)
    returnPressed = Signal()
    editingFinished = Signal()

    class EchoMode:
        Normal = 0
        Password = 2
        NoEcho = 1
        PasswordEchoOnEdit = 3

    placeholder = Prop("", in_props=True)
    readOnly = Prop(False, getter="isReadOnly")
    echoMode = Prop(EchoMode.Normal)
    clearButton = Prop(False)
    # Not part of the wire payload (renderer.js never read it, same as
    # before) -- in_props=False keeps that, while still getting a real
    # maxLength()/setMaxLength() pair instead of a write-only attribute.
    maxLength = Prop(32767, in_props=False)

    def setPlaceholderText(self, text: str):
        self.setPlaceholder(text)

    def placeholderText(self) -> str:
        return self.placeholder()

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

    def setPlainText(self, text: str):
        previous = self.plainText()
        self._props["plainText"] = text
        self._notify("text", text)  # same field as full-tree serialization
        if text != previous:
            self.textChanged.emit()

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
    editable = Prop(False, getter="isEditable")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[str] = []

    def addItem(self, text: str, data=None):
        self._items.append(text)
        if self.currentIndex() < 0:
            self.setCurrentIndex(0)
        self._notify("items", self._items)

    def addItems(self, texts: list[str]):
        self._items.extend(texts)
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

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["items"] = self._items
        return props

    def _handle_event(self, event_type, value):
        if event_type == "currentIndexChanged":
            self.setCurrentIndex(int(value))
            self.currentTextChanged.emit(self.currentText())


class QCheckBox(_TextWidget):
    _widget_type = "QCheckBox"

    stateChanged = Signal(int)
    toggled = Signal(bool)

    checked = Prop(False, notify=True, getter="isChecked")
    tristate = Prop(False, getter="isTristate")

    def checkState(self):
        return Qt.Checked if self.isChecked() else Qt.Unchecked

    def _handle_event(self, event_type, value):
        if event_type == "toggled":
            self.setChecked(bool(value))
            self.stateChanged.emit(2 if self.isChecked() else 0)
            self.toggled.emit(self.isChecked())


class QRadioButton(_TextWidget):
    _widget_type = "QRadioButton"

    toggled = Signal(bool)

    checked = Prop(False, notify=True, getter="isChecked")

    def _handle_event(self, event_type, value):
        if event_type == "toggled":
            self.setChecked(bool(value))
            self.toggled.emit(self.isChecked())


class QSlider(_RangedMixin, QWidget):
    _widget_type = "QSlider"

    valueChanged = Signal(int)
    sliderMoved = Signal(int)

    value = Prop(0, notify=True, signal="valueChanged")
    minimum = Prop(0)
    maximum = Prop(99)
    singleStep = Prop(1)
    pageStep = Prop(10)
    tickPosition = Prop(0)
    tickInterval = Prop(0)
    # None of pageStep/tickPosition/tickInterval/orientation had a getter in
    # the hand-written version -- Prop adds one for each, for free.
    orientation = Prop(int(Qt.Horizontal), cast=int)

    def __init__(self, orientation=None, parent=None):
        super().__init__(parent)
        if orientation is not None:
            self.setOrientation(orientation)

    def _handle_event(self, event_type, value):
        if event_type == "valueChanged":
            self.setValue(int(value))
            self.sliderMoved.emit(self.value())


class QDial(_RangedMixin, QWidget):
    """A rotary QAbstractSlider. Rendered as an SVG dial the user drags."""

    _widget_type = "QDial"

    valueChanged = Signal(int)
    sliderMoved = Signal(int)

    value = Prop(0, notify=True, signal="valueChanged", cast=int)
    minimum = Prop(0)
    maximum = Prop(99)
    singleStep = Prop(1)
    notchesVisible = Prop(False)
    wrapping = Prop(False)

    def _handle_event(self, event_type, value):
        if event_type == "valueChanged":
            self.setValue(int(value))
            self.sliderMoved.emit(self.value())


class QProgressBar(QWidget):
    _widget_type = "QProgressBar"

    # Note: unlike QSlider/QSpinBox, real QProgressBar.setValue() does not
    # clamp to [minimum, maximum] here â€” matches the pre-existing behavior.
    value = Prop(0, notify=True)
    minimum = Prop(0)
    maximum = Prop(100)
    textVisible = Prop(True)
    format = Prop("%p%")
    # Never part of the wire payload for QProgressBar (unlike QSlider) --
    # in_props=False keeps that; only a real getter is new here.
    orientation = Prop(int(Qt.Horizontal), cast=int, in_props=False)

    def setRange(self, min_val: int, max_val: int):
        self.setMinimum(min_val)
        self.setMaximum(max_val)


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

    # Redeclared with a float default/cast â€” everything else (clamping,
    # notify, conditional valueChanged emission) is inherited from
    # QSpinBox/_RangedMixin. The original hand-written override of this
    # setValue() never emitted valueChanged at all; going through the
    # shared engine fixes that for free.
    value = Prop(0.0, notify=True, signal="valueChanged", cast=float)
    decimals = Prop(2)

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["step"] = self.singleStep()
        return props

    def _handle_event(self, event_type, value):
        if event_type == "valueChanged":
            self.setValue(float(value))


class QButtonGroup:
    buttonClicked = Signal(int)

    # Not a QWidget (no `_wid`), but same Prop shape as QListWidgetItem/QFont;
    # also fixes a missing isExclusive() getter (setter-only before).
    exclusive = Prop(True, getter="isExclusive")

    def __init__(self, parent=None):
        self._props: dict = {name: p.default for name, p in self._declared_props.items()}
        self._buttons: list[tuple[QWidget, int]] = []
        self._parent = parent

    def addButton(self, button, btn_id: int = -1):
        self._buttons.append((button, btn_id))

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


_register_props(QButtonGroup)
