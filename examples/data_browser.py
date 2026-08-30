"""Data browser — QTreeWidget, QTableWidget, and QDial, themed with a QSS
stylesheet.

A file-tree on the left, a details table on the right, and a dial that filters
the table by a minimum size. Everything is styled through a single
``setStyleSheet`` call — PySideWeb translates the Qt Style Sheet to scoped CSS.

    uv run python examples/data_browser.py

Then open http://localhost:8765.
"""

import pysideweb  # noqa: F401  Must come before any PySide6 import!

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDial,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

STYLE = """
QWidget { background: #f6f7f9; color: #1f2733; font-size: 13px; }
QLabel#heading { font-size: 15px; font-weight: 700; color: #0f1b2d; }
QLabel { color: #55617a; font-weight: 600; }
QTreeWidget, QTableWidget {
    background: #ffffff;
    border: 1px solid #d9dee7;
    border-radius: 8px;
}
QTreeWidget::item:selected { background: #e6efff; color: #1c4fd6; }
QTableWidget::item:selected { background: #e6efff; }
"""

# (path, size_kb) rows; the tree mirrors the directory structure.
FILES = [
    ("src", None, [
        ("src/app.py", 6.4),
        ("src/models.py", 3.1),
        ("src/views.py", 9.8),
    ]),
    ("tests", None, [
        ("tests/test_app.py", 4.2),
        ("tests/test_models.py", 2.0),
    ]),
    ("docs", None, [
        ("docs/guide.md", 12.5),
        ("docs/api.md", 7.7),
    ]),
]


class DataBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data browser")

        central = QWidget()
        central.setStyleSheet(STYLE)
        root = QHBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(18)

        # -- Left: file tree --
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(_heading("Project"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Size (kB)"])
        for folder, _size, children in FILES:
            node = QTreeWidgetItem(self.tree, [folder, ""])
            for path, size in children:
                QTreeWidgetItem(node, [path.split("/")[-1], f"{size:.1f}"])
        self.tree.expandAll()
        self.tree.itemClicked.connect(self._on_tree_click)
        left.addWidget(self.tree)
        root.addLayout(left)

        # -- Right: filter dial + table --
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(_heading("Files"))

        filter_row = QHBoxLayout()
        self.dial = QDial()
        self.dial.setRange(0, 15)
        self.dial.setValue(0)
        self.dial.valueChanged.connect(self._apply_filter)
        self.filter_label = QLabel("Min size: 0.0 kB")
        filter_row.addWidget(self.dial)
        filter_row.addWidget(self.filter_label)
        filter_row.addStretch(1)
        right.addLayout(filter_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Path", "Size (kB)", "Kind"])
        self.table.cellClicked.connect(self._on_cell_click)
        right.addWidget(self.table)

        self.status = QLabel("")
        right.addWidget(self.status)
        root.addLayout(right)

        self.setCentralWidget(central)

        self._all_rows = [
            (path, size, "test" if "test" in path else "doc" if path.endswith(".md") else "code")
            for _f, _s, kids in FILES for path, size in kids
        ]
        self._apply_filter(0)

    def _apply_filter(self, threshold_tenths: int):
        minimum = threshold_tenths
        self.filter_label.setText(f"Min size: {minimum:.1f} kB")
        rows = [r for r in self._all_rows if r[1] >= minimum]
        self.table.setRowCount(len(rows))
        for i, (path, size, kind) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(path))
            size_item = QTableWidgetItem(f"{size:.1f}")
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 1, size_item)
            self.table.setItem(i, 2, QTableWidgetItem(kind))
        self.status.setText(f"{len(rows)} of {len(self._all_rows)} files")

    def _on_tree_click(self, item, _column):
        if item.childCount() == 0:
            self.status.setText(f"Selected {item.text(0)} ({item.text(1)} kB)")

    def _on_cell_click(self, row, _column):
        path_item = self.table.item(row, 0)
        if path_item is not None:
            self.status.setText(f"Row {row}: {path_item.text()}")


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("heading")
    return label


if __name__ == "__main__":
    app = QApplication([])
    win = DataBrowser()
    win.resize(880, 560)
    win.show()
    app.exec()
