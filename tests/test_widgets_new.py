"""Tests for QDial, QTableWidget, and QTreeWidget."""

from PySide6.QtWidgets import (
    QDial,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
)

from pysideweb import state


def _props(w):
    return state.serialize_widget(w)["props"]


class TestQDial:
    def test_range_and_value_signal(self):
        d = QDial()
        d.setRange(0, 200)
        seen = []
        d.valueChanged.connect(seen.append)
        d._handle_event("valueChanged", 150)
        assert d.value() == 150
        assert seen == [150]

    def test_value_clamped(self):
        d = QDial()
        d.setRange(0, 10)
        d.setValue(99)
        assert d.value() == 10

    def test_exposed_in_props(self):
        d = QDial()
        d.setValue(3)
        p = _props(d)
        assert p["value"] == 3 and p["minimum"] == 0 and p["maximum"] == 99


class TestQTableWidget:
    def test_dimensions(self):
        t = QTableWidget(3, 4)
        assert t.rowCount() == 3 and t.columnCount() == 4
        t.setRowCount(2)
        assert t.rowCount() == 2
        assert len(t._cells) == 2 and len(t._cells[0]) == 4

    def test_set_and_get_item(self):
        t = QTableWidget(2, 2)
        t.setItem(0, 1, QTableWidgetItem("hi"))
        assert t.item(0, 1).text() == "hi"
        assert t.item(0, 1).row() == 0 and t.item(0, 1).column() == 1

    def test_headers_and_wire(self):
        t = QTableWidget(1, 2)
        t.setHorizontalHeaderLabels(["A", "B"])
        t.setItem(0, 0, QTableWidgetItem("x"))
        p = _props(t)
        assert p["hHeaders"] == ["A", "B"]
        assert p["cells"] == [[{"text": "x"}, None]]

    def test_cell_clicked_selects_and_signals(self):
        t = QTableWidget(2, 2)
        clicks = []
        t.cellClicked.connect(lambda r, c: clicks.append((r, c)))
        t._handle_event("cellClicked", {"row": 1, "col": 0})
        assert clicks == [(1, 0)]
        assert (t.currentRow(), t.currentColumn()) == (1, 0)

    def test_cell_edited_creates_item_and_signals(self):
        t = QTableWidget(1, 1)
        changed = []
        t.cellChanged.connect(lambda r, c: changed.append((r, c)))
        t._handle_event("cellChanged", {"row": 0, "col": 0, "text": "typed"})
        assert t.item(0, 0).text() == "typed"
        assert changed == [(0, 0)]

    def test_editable_flag_in_wire(self):
        it = QTableWidgetItem("e")
        it.setFlags(QTableWidgetItem.ItemIsEditable)
        t = QTableWidget(1, 1)
        t.setItem(0, 0, it)
        assert _props(t)["cells"][0][0]["editable"] is True


class TestQTreeWidget:
    def test_build_and_wire(self):
        tw = QTreeWidget()
        tw.setHeaderLabels(["Name", "Size"])
        root = QTreeWidgetItem(tw, ["src", ""])
        QTreeWidgetItem(root, ["main.py", "2kb"])
        QTreeWidgetItem(tw, ["README", "1kb"])
        p = _props(tw)
        assert p["headers"] == ["Name", "Size"]
        assert p["tree"][0]["texts"] == ["src", ""]
        assert p["tree"][0]["children"][0]["texts"] == ["main.py", "2kb"]
        assert len(p["tree"]) == 2

    def test_expand_all(self):
        tw = QTreeWidget()
        root = QTreeWidgetItem(tw, ["a"])
        QTreeWidgetItem(root, ["b"])
        assert _props(tw)["tree"][0]["expanded"] is False
        tw.expandAll()
        assert _props(tw)["tree"][0]["expanded"] is True

    def test_item_clicked_resolves_path(self):
        tw = QTreeWidget()
        root = QTreeWidgetItem(tw, ["a"])
        QTreeWidgetItem(root, ["b"])
        got = []
        tw.itemClicked.connect(lambda it, col: got.append((it.text(0), col)))
        tw._handle_event("itemClicked", {"path": [0, 0], "col": 0})
        assert got == [("b", 0)]
        assert tw.currentItem().text(0) == "b"

    def test_item_toggled_flips_expansion(self):
        tw = QTreeWidget()
        root = QTreeWidgetItem(tw, ["a"])
        QTreeWidgetItem(root, ["b"])
        expanded = []
        tw.itemExpanded.connect(lambda it: expanded.append(it.text(0)))
        tw._handle_event("itemToggled", {"path": [0]})
        assert tw.topLevelItem(0).isExpanded() is True
        assert expanded == ["a"]

    def test_child_added_after_toplevel_still_bound_to_tree(self):
        tw = QTreeWidget()
        root = QTreeWidgetItem(["a"])
        tw.addTopLevelItem(root)
        child = QTreeWidgetItem(["b"])
        root.addChild(child)
        assert child._tree is tw
        assert _props(tw)["tree"][0]["children"][0]["texts"] == ["b"]
