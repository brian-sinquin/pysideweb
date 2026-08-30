"""pysideweb.widgets.base - QWidget, the root virtual widget."""

from __future__ import annotations

from typing import Any

from .. import qss, state
from ..core import (
    _STRICT,
    Prop,
    QFont,
    QObject,
    QSize,
    _absorb_ok,
    _AutoAttr,
    _register_props,
)

_warned_unknown_methods: set[str] = set()

class QWidget(QObject):
    """Virtual QWidget â€” base class for all virtual widgets."""

    _widget_type = "QWidget"
    _declared_props: dict[str, Prop] = {}

    objectName = Prop("", notify=True)
    styleSheet = Prop("")  # setStyleSheet() below forces a full refresh so the
    windowTitle = Prop("", notify=True)  # server-translated styleSheetCss rides along
    toolTip = Prop("", in_props=False)  # reported under the "tooltip" wire key below

    def __init__(self, parent=None, flags=None):
        self._props: dict[str, Any] = {name: p.default for name, p in self._declared_props.items()}
        QObject.__init__(self, None)  # sets _signals_blocked, _dynamic_props, etc.
        self._wid: str = state.register_widget(self)
        self._parent = parent
        self._children: list[QWidget] = []
        self._layout = None
        self._parent_layout = None
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
        from ..core import QRect
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
        self._raw_set_styleSheet(css or "")
        state.notify_full_refresh()

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

        Shared by every container-ish addWidget()/setWidget()/addTab() â€”
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
        # Unregisters this widget's whole subtree (its own children, plus
        # anything placed in its layout), not just this one id -- see
        # unregister_subtree()'s docstring for why that matters.
        state.unregister_subtree(self)
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

    def update(self, *args):
        state.notify_full_refresh()

    def repaint(self, *args):
        state.notify_full_refresh()

    # -- Custom painting --
    def paintEvent(self, event):
        """Default: nothing custom. A subclass that overrides this is
        detected during serialization; its drawing is recorded by a virtual
        QPainter and replayed on a <canvas> in the browser. See
        pysideweb/painting.py.
        """

    def _record_paint(self):
        from ..painting import record_widget_paint
        return record_widget_paint(self)

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
        sheet = props.get("styleSheet", "")
        if sheet and qss.looks_like_ruleset(sheet):
            # Translate the QSS ruleset to CSS scoped to this widget's subtree;
            # the renderer just injects it. A bare declaration list is left for
            # the renderer to apply inline.
            props["styleSheetCss"] = qss.translate(sheet, f'[data-wid="{self._wid}"]')
        if self._font and self._font.family():
            props["font"] = self._font.to_css()
        if self._fixed_size:
            props["fixedSize"] = list(self._fixed_size)
        if self._min_size.width() > 0 or self._min_size.height() > 0:
            props["minSize"] = self._min_size.toTuple()
        if self._custom_props:
            props["customProps"] = self._custom_props
        paint = self._record_paint()
        if paint is not None:
            props["paint"] = paint
        return props

    def _handle_event(self, event_type: str, value: Any):
        """Handle events dispatched from the browser."""
        pass

    def __getattr__(self, name: str):
        """Fallback for methods pysideweb hasn't implemented on this widget.

        Only reached when normal attribute lookup already failed -- every
        method pysideweb *does* implement (including ones synthesized by
        Prop()) is found first and never comes through here. This lets
        third-party PySide6 code call widget methods pysideweb hasn't gotten
        around to without crashing; the call just becomes a no-op.

        Deliberately raised (not absorbed):
        - "_"-prefixed names -- pysideweb's own hasattr(w, "_children") duck
          typing must see a real AttributeError.
        - isFoo()/hasFoo() predicate names -- libraries feature-detect with
          `if hasattr(w, "setSectionResizeMode")`; absorbing those makes
          hasattr always true and sends them down the wrong branch. Better to
          answer False.
        - everything, when PYSIDEWEB_STRICT=1 (development aid).
        """
        if name.startswith("_"):
            raise AttributeError(name)
        if _STRICT or not _absorb_ok(name):
            raise AttributeError(
                f"{type(self).__name__}.{name} is not implemented by pysideweb"
            )
        key = f"{type(self).__name__}.{name}"
        if key not in _warned_unknown_methods:
            _warned_unknown_methods.add(key)
            print(f"[PySideWeb] Note: {key}() is not implemented -- ignoring the call. "
                  f"If you need it, please open an issue.")
        return _AutoAttr()

# QWidget doesn't go through __init_subclass__ itself (that hook only fires
# for subclasses), so its own Prop() declarations are registered explicitly
# here, once.
_register_props(QWidget)


class _RangedMixin:
    """Shared logic for widgets with a bounded, notify+signal `value` Prop
    (QSlider, QSpinBox, QDoubleSpinBox). Each still declares its own
    `value`/`minimum`/`maximum` Prop (so defaults/cast can differ), but the
    clamp-then-store-then-conditionally-emit rule â€” previously duplicated
    3 times, and silently *missing* on QDoubleSpinBox â€” is written once.
    """

    def setRange(self, min_val, max_val):
        self.setMinimum(min_val)
        self.setMaximum(max_val)

    def setValue(self, val):
        val = max(self.minimum(), min(self.maximum(), val))
        self._raw_set_value(val)

