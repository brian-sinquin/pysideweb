"""Kanban task board — a realistic productivity app built with plain PySide6.

Add tasks with a priority, then move them across To Do → In Progress → Done.
A progress bar tracks completion. Everything renders in the browser thanks to
PySideWeb.

    uv run python examples/kanban.py

Then open http://localhost:8765.
"""

import pysideweb  # noqa: F401  Must come before any PySide6 import!

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ── Theme ──────────────────────────────────────────────────────────────
BG = "#0f1220"
PANEL = "#191d2e"
BORDER = "#2a3047"
TEXT = "#e8ebf5"
MUTED = "#8b93b0"
ACCENT = "#7c8cff"

PRIORITIES = {
    "High": ("🔴", "#f8717155"),
    "Medium": ("🟡", "#fbbf2455"),
    "Low": ("🟢", "#34d39955"),
}

# Stages, in order. Each has a title and an accent color.
STAGES = [
    ("To Do", "#7c8cff"),
    ("In Progress", "#fbbf24"),
    ("Done", "#34d399"),
]


class Task:
    _seq = 0

    def __init__(self, title, priority):
        Task._seq += 1
        self.id = Task._seq
        self.title = title
        self.priority = priority
        self.stage = 0  # index into STAGES


class Column(QFrame):
    """One Kanban column: header + task list + move controls."""

    def __init__(self, stage_index, board):
        super().__init__()
        self.stage_index = stage_index
        self.board = board
        name, color = STAGES[stage_index]
        self.color = color

        self.setStyleSheet(
            f"background-color: {PANEL}; border-radius: 14px; "
            f"padding: 14px; border: 1px solid {BORDER};"
        )
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.heading = QLabel(name)
        self.heading.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 700;")
        self.count = QLabel("0")
        self.count.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; font-weight: 700; "
            f"background-color: {BG}; padding: 2px 8px; border-radius: 8px;"
        )
        self.count.setAlignment(Qt.AlignRight)
        header.addWidget(self.heading)
        header.addStretch()
        header.addWidget(self.count)
        layout.addLayout(header)

        self.list = QListWidget()
        self.list.setStyleSheet(
            f"background-color: transparent; color: {TEXT}; border: none;"
        )
        layout.addWidget(self.list)

        # Move controls
        controls = QHBoxLayout()
        if stage_index > 0:
            back = QPushButton("◀")
            back.setToolTip("Move selected task back")
            back.setStyleSheet(self._btn_style())
            back.clicked.connect(lambda: self.board.move_selected(self.stage_index, -1))
            controls.addWidget(back)

        delete = QPushButton("🗑")
        delete.setToolTip("Delete selected task")
        delete.setStyleSheet(self._btn_style())
        delete.clicked.connect(lambda: self.board.delete_selected(self.stage_index))
        controls.addWidget(delete)

        if stage_index < len(STAGES) - 1:
            fwd = QPushButton("▶")
            fwd.setToolTip("Advance selected task")
            fwd.setStyleSheet(self._btn_style())
            fwd.clicked.connect(lambda: self.board.move_selected(self.stage_index, +1))
            controls.addWidget(fwd)
        layout.addLayout(controls)

    def _btn_style(self):
        return (
            f"background-color: {BG}; color: {TEXT}; font-size: 14px; "
            f"padding: 8px 14px; border: 1px solid {BORDER}; border-radius: 8px;"
        )

    def render(self, tasks):
        self.list.clear()
        for task in tasks:
            icon = PRIORITIES[task.priority][0]
            self.list.addItem(f"{icon}  {task.title}")
        self.count.setText(str(len(tasks)))


class Kanban(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🗂️ Task Board — PySideWeb")
        self.tasks: list[Task] = []
        self._seed()

        root = QWidget()
        root.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(18)

        outer.addLayout(self._build_header())
        outer.addWidget(self._build_composer())

        columns = QHBoxLayout()
        columns.setSpacing(18)
        self.columns = []
        for i in range(len(STAGES)):
            col = Column(i, self)
            self.columns.append(col)
            columns.addWidget(col)
        outer.addLayout(columns)

        self._render()

    def _seed(self):
        samples = [
            ("Design landing page", "High", 1),
            ("Write API docs", "Medium", 0),
            ("Fix login redirect bug", "High", 2),
            ("Set up CI pipeline", "Medium", 2),
            ("Refactor settings module", "Low", 0),
            ("Plan Q3 roadmap", "Low", 1),
        ]
        for title, prio, stage in samples:
            t = Task(title, prio)
            t.stage = stage
            self.tasks.append(t)

    # -- Header + progress --
    def _build_header(self):
        row = QHBoxLayout()
        col = QVBoxLayout()
        title = QLabel("Task Board")
        title.setStyleSheet(f"color: {TEXT}; font-size: 28px; font-weight: 800;")
        sub = QLabel("Drag-free Kanban — select a task, then use ◀ / ▶ to move it")
        sub.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        col.addWidget(title)
        col.addWidget(sub)
        row.addLayout(col)
        row.addStretch()

        prog_col = QVBoxLayout()
        self.progress_label = QLabel("0% complete")
        self.progress_label.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: 700;")
        self.progress_label.setAlignment(Qt.AlignRight)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(220)
        prog_col.addWidget(self.progress_label)
        prog_col.addWidget(self.progress)
        row.addLayout(prog_col)
        return row

    # -- Composer (add task) --
    def _build_composer(self):
        bar = QFrame()
        bar.setStyleSheet(
            f"background-color: {PANEL}; border-radius: 12px; "
            f"padding: 12px; border: 1px solid {BORDER};"
        )
        row = QHBoxLayout(bar)
        row.setSpacing(10)

        self.input = QLineEdit()
        self.input.setPlaceholderText("New task…")
        self.input.setStyleSheet(
            f"background-color: {BG}; color: {TEXT}; padding: 10px; "
            f"border: 1px solid {BORDER}; border-radius: 8px;"
        )
        self.input.returnPressed.connect(self._add_task)
        row.addWidget(self.input, stretch=1)

        self.priority = QComboBox()
        for p in PRIORITIES:
            self.priority.addItem(p)
        self.priority.setCurrentIndex(1)  # Medium
        self.priority.setStyleSheet(
            f"background-color: {BG}; color: {TEXT}; padding: 10px; "
            f"border: 1px solid {BORDER}; border-radius: 8px;"
        )
        row.addWidget(self.priority)

        add = QPushButton("+ Add Task")
        add.setStyleSheet(
            f"background-color: {ACCENT}; color: #0b0f1f; font-weight: 700; "
            f"padding: 10px 18px; border: none; border-radius: 8px;"
        )
        add.clicked.connect(self._add_task)
        row.addWidget(add)
        return bar

    # -- Data ops --
    def _tasks_in(self, stage_index):
        return [t for t in self.tasks if t.stage == stage_index]

    def _add_task(self):
        title = self.input.text().strip()
        if not title:
            return
        self.tasks.append(Task(title, self.priority.currentText()))
        self.input.setText("")
        self._render()

    def move_selected(self, stage_index, delta):
        row = self.columns[stage_index].list.currentRow()
        tasks = self._tasks_in(stage_index)
        if 0 <= row < len(tasks):
            new_stage = max(0, min(len(STAGES) - 1, stage_index + delta))
            tasks[row].stage = new_stage
            self._render()

    def delete_selected(self, stage_index):
        row = self.columns[stage_index].list.currentRow()
        tasks = self._tasks_in(stage_index)
        if 0 <= row < len(tasks):
            self.tasks.remove(tasks[row])
            self._render()

    # -- Render --
    def _render(self):
        for i, col in enumerate(self.columns):
            col.render(self._tasks_in(i))

        total = len(self.tasks)
        done = len(self._tasks_in(len(STAGES) - 1))
        pct = int(done / total * 100) if total else 0
        self.progress.setValue(pct)
        self.progress_label.setText(f"{pct}% complete · {done}/{total} done")


def main():
    app = QApplication([])
    window = Kanban()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
