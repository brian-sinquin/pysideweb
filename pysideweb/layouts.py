"""
pysideweb.layouts — Virtual layout classes mapping to CSS Flexbox / Grid.

Each layout stores an ordered list of items (widgets or nested layouts)
with optional stretch factors, spacing, and margins.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Layout items
# ---------------------------------------------------------------------------

class _LayoutItem:
    """Wrapper for an item inside a layout."""
    def __init__(self, widget=None, layout=None, stretch: int = 0,
                 row: int = 0, col: int = 0, row_span: int = 1, col_span: int = 1,
                 alignment: int = 0):
        self._widget = widget
        self._layout = layout
        self._stretch = stretch
        self._row = row
        self._col = col
        self._row_span = row_span
        self._col_span = col_span
        self._alignment = alignment

    @property
    def _wid(self):
        if self._widget:
            return self._widget._wid
        return None


class _Stretch:
    """Represents a stretch spacer in a layout."""
    def __init__(self, factor: int = 1):
        self._factor = factor
        self._wid = f"stretch_{id(self)}"
        self._widget_type = "Stretch"
        self._children = []

    def _get_props(self):
        return {"factor": self._factor}

    def _handle_event(self, event_type, value):
        pass


# ---------------------------------------------------------------------------
# Base layout
# ---------------------------------------------------------------------------

class QLayout:
    """Base class for all virtual layouts."""

    def __init__(self, parent=None):
        self._parent = parent
        self._items: list[Any] = []
        self._spacing = 6
        self._margins = (9, 9, 9, 9)  # left, top, right, bottom
        self._layout_type = "QLayout"

        if parent is not None and hasattr(parent, '_layout'):
            parent._layout = self

    def addWidget(self, widget, stretch: int = 0, alignment: int = 0):
        """Default box-style add: append a plain item. QVBoxLayout/QHBoxLayout use
        this as-is; QGridLayout/QFormLayout/QStackedLayout override it for their
        own item shapes."""
        item = _LayoutItem(widget=widget, stretch=stretch, alignment=alignment)
        self._items.append(item)
        if hasattr(widget, '_parent_layout'):
            widget._parent_layout = self

    def setSpacing(self, spacing: int):
        self._spacing = spacing

    def spacing(self) -> int:
        return self._spacing

    def setContentsMargins(self, left: int, top: int, right: int, bottom: int):
        self._margins = (left, top, right, bottom)

    def contentsMargins(self):
        from .core import QMargins
        return QMargins(*self._margins)

    def count(self) -> int:
        return len(self._items)

    def addLayout(self, layout, stretch: int = 0):
        item = _LayoutItem(layout=layout, stretch=stretch)
        self._items.append(item)

    def addStretch(self, factor: int = 1):
        self._items.append(_Stretch(factor))

    def addSpacing(self, size: int):
        # Represented as a fixed-size stretch
        spacer = _Stretch(0)
        spacer._fixed_size = size
        self._items.append(spacer)

    def insertWidget(self, index: int, widget, stretch: int = 0):
        item = _LayoutItem(widget=widget, stretch=stretch)
        self._items.insert(index, item)

    def removeWidget(self, widget):
        self._items = [
            item for item in self._items
            if not (hasattr(item, '_widget') and item._widget is widget)
        ]

    def _get_props(self) -> dict:
        return {
            "type": self._layout_type,
            "spacing": self._spacing,
            "margins": list(self._margins),
        }


# ---------------------------------------------------------------------------
# QVBoxLayout
# ---------------------------------------------------------------------------

class QVBoxLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout_type = "QVBoxLayout"


# ---------------------------------------------------------------------------
# QHBoxLayout
# ---------------------------------------------------------------------------

class QHBoxLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout_type = "QHBoxLayout"


# ---------------------------------------------------------------------------
# QGridLayout
# ---------------------------------------------------------------------------

class QGridLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout_type = "QGridLayout"
        self._col_stretches: dict[int, int] = {}
        self._row_stretches: dict[int, int] = {}

    def addWidget(self, widget, row: int = 0, col: int = 0,
                  row_span: int = 1, col_span: int = 1, alignment: int = 0):
        item = _LayoutItem(
            widget=widget, row=row, col=col,
            row_span=row_span, col_span=col_span, alignment=alignment
        )
        self._items.append(item)

    def setColumnStretch(self, col: int, stretch: int):
        self._col_stretches[col] = stretch

    def setRowStretch(self, row: int, stretch: int):
        self._row_stretches[row] = stretch

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["colStretches"] = self._col_stretches
        props["rowStretches"] = self._row_stretches
        # Compute grid dimensions
        max_row = max((item._row + item._row_span for item in self._items
                       if isinstance(item, _LayoutItem)), default=1)
        max_col = max((item._col + item._col_span for item in self._items
                       if isinstance(item, _LayoutItem)), default=1)
        props["rows"] = max_row
        props["cols"] = max_col
        # Per-item grid positions
        props["gridItems"] = [
            {
                "id": item._widget._wid if item._widget else None,
                "row": item._row, "col": item._col,
                "rowSpan": item._row_span, "colSpan": item._col_span,
            }
            for item in self._items if isinstance(item, _LayoutItem) and item._widget
        ]
        return props


# ---------------------------------------------------------------------------
# QFormLayout
# ---------------------------------------------------------------------------

class QFormLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout_type = "QFormLayout"
        self._rows: list[tuple] = []

    def addRow(self, label, field=None):
        if field is None:
            # Single widget spanning full width
            item = _LayoutItem(widget=label)
            self._items.append(item)
            self._rows.append((None, label))
        else:
            # label (string or widget) + field widget
            from .widgets import QLabel
            if isinstance(label, str):
                label_widget = QLabel(label)
            else:
                label_widget = label
            item_label = _LayoutItem(widget=label_widget)
            item_field = _LayoutItem(widget=field)
            self._items.append(item_label)
            self._items.append(item_field)
            self._rows.append((label_widget, field))

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["formRows"] = [
            {
                "labelId": row[0]._wid if row[0] else None,
                "fieldId": row[1]._wid if row[1] else None,
            }
            for row in self._rows
        ]
        return props


# ---------------------------------------------------------------------------
# QStackedLayout
# ---------------------------------------------------------------------------

class QStackedLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout_type = "QStackedLayout"
        self._current_index = 0

    def addWidget(self, widget, stretch: int = 0, alignment: int = 0):
        item = _LayoutItem(widget=widget)
        self._items.append(item)

    def setCurrentIndex(self, index: int):
        self._current_index = index

    def currentIndex(self) -> int:
        return self._current_index

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["currentIndex"] = self._current_index
        return props
