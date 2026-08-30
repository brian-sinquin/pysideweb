"""pysideweb.widgets.views - QListWidget / QTableWidget / QTreeWidget."""

from __future__ import annotations

from .. import state
from ..core import (
    Prop,
    QFont,
    QIcon,
    Signal,
    _AutoAttr,
    _register_props,
)
from .base import QWidget


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


class QTableWidgetItem:
    """A single cell value. Like QListWidgetItem, not a QWidget."""

    text = Prop("")
    selected = Prop(False, getter="isSelected")

    ItemIsEditable = 2

    def __init__(self, text: str = ""):
        self._props: dict = {name: p.default for name, p in self._declared_props.items()}
        self._props["text"] = str(text)
        self._flags = 0
        self._text_alignment = 0
        self._table = None
        self._row = -1
        self._col = -1

    def setFlags(self, flags):
        self._flags = int(flags)

    def flags(self) -> int:
        return self._flags

    def setTextAlignment(self, align):
        self._text_alignment = int(align)

    def textAlignment(self) -> int:
        return self._text_alignment

    def row(self) -> int:
        return self._row

    def column(self) -> int:
        return self._col

    def to_dict(self) -> dict:
        d = {"text": self.text()}
        if self._text_alignment:
            d["align"] = self._text_alignment
        if self._flags & self.ItemIsEditable:
            d["editable"] = True
        return d


_register_props(QTableWidgetItem)

class QTableWidget(QWidget):
    _widget_type = "QTableWidget"

    cellClicked = Signal(int, int)
    cellChanged = Signal(int, int)
    currentCellChanged = Signal(int, int, int, int)
    itemChanged = Signal(object)
    itemSelectionChanged = Signal()

    def __init__(self, rows: int = 0, columns: int = 0, parent=None):
        super().__init__(parent)
        self._rows = 0
        self._cols = 0
        self._cells: list[list[QTableWidgetItem | None]] = []
        self._h_headers: list[str] = []
        self._v_headers: list[str] = []
        self._cur_row = -1
        self._cur_col = -1
        if rows:
            self.setRowCount(rows)
        if columns:
            self.setColumnCount(columns)

    # -- dimensions --
    def setRowCount(self, n: int):
        n = max(0, int(n))
        if n < self._rows:
            self._cells = self._cells[:n]
        else:
            for _ in range(n - self._rows):
                self._cells.append([None] * self._cols)
        self._rows = n
        self._sync()

    def setColumnCount(self, n: int):
        n = max(0, int(n))
        for r in range(self._rows):
            row = self._cells[r]
            if n < self._cols:
                self._cells[r] = row[:n]
            else:
                self._cells[r] = row + [None] * (n - self._cols)
        self._cols = n
        if len(self._h_headers) > n:
            self._h_headers = self._h_headers[:n]
        self._sync()

    def rowCount(self) -> int:
        return self._rows

    def columnCount(self) -> int:
        return self._cols

    # -- items --
    def setItem(self, row: int, col: int, item: QTableWidgetItem):
        if not (0 <= row < self._rows and 0 <= col < self._cols):
            return
        if isinstance(item, str):
            item = QTableWidgetItem(item)
        item._table, item._row, item._col = self, row, col
        self._cells[row][col] = item
        self._sync()

    def item(self, row: int, col: int):
        if 0 <= row < self._rows and 0 <= col < self._cols:
            return self._cells[row][col]
        return None

    def takeItem(self, row: int, col: int):
        it = self.item(row, col)
        if it is not None:
            self._cells[row][col] = None
            self._sync()
        return it

    def setHorizontalHeaderLabels(self, labels: list[str]):
        self._h_headers = [str(x) for x in labels]
        self._sync()

    def setVerticalHeaderLabels(self, labels: list[str]):
        self._v_headers = [str(x) for x in labels]
        self._sync()

    def clearContents(self):
        for r in range(self._rows):
            self._cells[r] = [None] * self._cols
        self._sync()

    def clear(self):
        self.clearContents()
        self._h_headers = []
        self._v_headers = []
        self._sync()

    def currentRow(self) -> int:
        return self._cur_row

    def currentColumn(self) -> int:
        return self._cur_col

    def setCurrentCell(self, row: int, col: int):
        self._select(row, col)

    # -- stubs commonly called on tables --
    def setEditTriggers(self, *a):
        pass

    def setSelectionBehavior(self, *a):
        pass

    def setSelectionMode(self, *a):
        pass

    def horizontalHeader(self):
        return _AutoAttr()

    def verticalHeader(self):
        return _AutoAttr()

    def resizeColumnsToContents(self):
        pass

    def setColumnWidth(self, *a):
        pass

    # -- internals --
    def _cells_wire(self):
        return [
            [(c.to_dict() if c is not None else None) for c in row]
            for row in self._cells
        ]

    def _sync(self):
        state.notify_full_refresh()

    def _select(self, row: int, col: int):
        prev_r, prev_c = self._cur_row, self._cur_col
        self._cur_row, self._cur_col = row, col
        if (row, col) != (prev_r, prev_c):
            self.currentCellChanged.emit(row, col, prev_r, prev_c)
            self.itemSelectionChanged.emit()
        state.notify_full_refresh()

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["rows"] = self._rows
        props["cols"] = self._cols
        props["hHeaders"] = self._h_headers
        props["vHeaders"] = self._v_headers
        props["cells"] = self._cells_wire()
        props["currentRow"] = self._cur_row
        props["currentColumn"] = self._cur_col
        return props

    def _handle_event(self, event_type, value):
        if event_type == "cellClicked":
            row, col = int(value["row"]), int(value["col"])
            self._select(row, col)
            self.cellClicked.emit(row, col)
        elif event_type == "cellChanged":
            row, col = int(value["row"]), int(value["col"])
            text = str(value.get("text", ""))
            it = self.item(row, col)
            if it is None:
                it = QTableWidgetItem(text)
                it._table, it._row, it._col = self, row, col
                self._cells[row][col] = it
            else:
                it.setText(text)
            self.cellChanged.emit(row, col)
            self.itemChanged.emit(it)


class QTreeWidgetItem:
    """A node in a QTreeWidget. Holds one string per column and child items."""

    def __init__(self, *args):
        # QTreeWidgetItem() | (parent) | (parent, [texts]) | ([texts])
        parent = None
        texts: list[str] = []
        for a in args:
            if isinstance(a, (list, tuple)):
                texts = [str(x) for x in a]
            elif isinstance(a, (QTreeWidgetItem, QTreeWidget)):
                parent = a
        self._texts = texts
        self._children: list[QTreeWidgetItem] = []
        self._parent_item: QTreeWidgetItem | None = None
        self._tree: QTreeWidget | None = None
        self._expanded = False
        self._selected = False
        if isinstance(parent, QTreeWidgetItem):
            parent.addChild(self)
        elif isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(self)

    def setText(self, col: int, text: str):
        while len(self._texts) <= col:
            self._texts.append("")
        self._texts[col] = str(text)
        self._touch()

    def text(self, col: int) -> str:
        return self._texts[col] if 0 <= col < len(self._texts) else ""

    def addChild(self, child: QTreeWidgetItem):
        child._parent_item = self
        child._tree = self._tree
        self._children.append(child)
        self._touch()

    def addChildren(self, children):
        for c in children:
            self.addChild(c)

    def child(self, i: int):
        return self._children[i] if 0 <= i < len(self._children) else None

    def childCount(self) -> int:
        return len(self._children)

    def parent(self):
        return self._parent_item

    def setExpanded(self, expanded: bool):
        self._expanded = bool(expanded)
        self._touch()

    def isExpanded(self) -> bool:
        return self._expanded

    def setSelected(self, selected: bool):
        self._selected = bool(selected)
        self._touch()

    def isSelected(self) -> bool:
        return self._selected

    def _touch(self):
        if self._tree is not None:
            self._tree._sync()

    def to_dict(self) -> dict:
        return {
            "texts": list(self._texts),
            "expanded": self._expanded,
            "selected": self._selected,
            "children": [c.to_dict() for c in self._children],
        }



class QTreeWidget(QWidget):
    _widget_type = "QTreeWidget"

    itemClicked = Signal(object, int)
    itemExpanded = Signal(object)
    itemCollapsed = Signal(object)
    currentItemChanged = Signal(object, object)
    itemSelectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._top: list[QTreeWidgetItem] = []
        self._headers: list[str] = []
        self._current: QTreeWidgetItem | None = None

    def setHeaderLabels(self, labels: list[str]):
        self._headers = [str(x) for x in labels]
        self._sync()

    def setHeaderLabel(self, label: str):
        self._headers = [str(label)]
        self._sync()

    def setColumnCount(self, n: int):
        if len(self._headers) < n:
            self._headers += [""] * (n - len(self._headers))
        self._sync()

    def columnCount(self) -> int:
        return max(1, len(self._headers))

    def addTopLevelItem(self, item: QTreeWidgetItem):
        item._parent_item = None
        item._tree = self
        _propagate_tree(item, self)
        self._top.append(item)
        self._sync()

    def addTopLevelItems(self, items):
        for it in items:
            self.addTopLevelItem(it)

    def topLevelItem(self, i: int):
        return self._top[i] if 0 <= i < len(self._top) else None

    def topLevelItemCount(self) -> int:
        return len(self._top)

    def invisibleRootItem(self):
        return _AutoAttr()

    def clear(self):
        self._top.clear()
        self._current = None
        self._sync()

    def expandAll(self):
        _walk_tree(self._top, lambda it: it.__setattr__("_expanded", True))
        self._sync()

    def collapseAll(self):
        _walk_tree(self._top, lambda it: it.__setattr__("_expanded", False))
        self._sync()

    def currentItem(self):
        return self._current

    def setCurrentItem(self, item):
        prev = self._current
        self._current = item
        if item is not prev:
            self.currentItemChanged.emit(item, prev)
            self.itemSelectionChanged.emit()
        self._sync()

    def setEditTriggers(self, *a):
        pass

    def setSelectionMode(self, *a):
        pass

    def header(self):
        return _AutoAttr()

    def _sync(self):
        state.notify_full_refresh()

    def _flat(self):
        """Depth-first list of (item, depth) â€” used to resolve wire paths."""
        out: list[tuple[QTreeWidgetItem, int]] = []

        def rec(items, depth):
            for it in items:
                out.append((it, depth))
                rec(it._children, depth + 1)

        rec(self._top, 0)
        return out

    def _item_at_path(self, path: list[int]):
        items = self._top
        node = None
        for idx in path:
            if not (0 <= idx < len(items)):
                return None
            node = items[idx]
            items = node._children
        return node

    def _get_props(self) -> dict:
        props = super()._get_props()
        props["headers"] = self._headers
        props["tree"] = [it.to_dict() for it in self._top]
        return props

    def _handle_event(self, event_type, value):
        path = [int(i) for i in value.get("path", [])]
        item = self._item_at_path(path)
        if item is None:
            return
        if event_type == "itemClicked":
            self.setCurrentItem(item)
            self.itemClicked.emit(item, int(value.get("col", 0)))
        elif event_type == "itemToggled":
            item.setExpanded(not item._expanded)
            (self.itemExpanded if item._expanded else self.itemCollapsed).emit(item)


def _propagate_tree(item: QTreeWidgetItem, tree: QTreeWidget) -> None:
    item._tree = tree
    for c in item._children:
        _propagate_tree(c, tree)


def _walk_tree(items, fn) -> None:
    for it in items:
        fn(it)
        _walk_tree(it._children, fn)

