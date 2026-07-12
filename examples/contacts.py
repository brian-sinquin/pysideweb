"""Contacts — a master–detail record manager built with plain PySide6.

A list of people on the left, an editable detail form on the right. Select a
record to load it, edit and save, add a new contact, or delete one. A clean,
professional two-pane layout. Renders in the browser thanks to PySideWeb.

    uv run python examples/contacts.py

Then open http://localhost:8765.
"""

import pysideweb  # noqa: F401  Must come before any PySide6 import!

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ── Palette (light, neutral) ───────────────────────────────────────────
BG = "#f4f5f7"
SURFACE = "#ffffff"
BORDER = "#dfe3e8"
TEXT = "#1a2029"
MUTED = "#697586"
ACCENT = "#3b5bdb"
DANGER = "#c0392b"


class Contact:
    def __init__(self, name="", email="", phone="", company="", notes=""):
        self.name = name
        self.email = email
        self.phone = phone
        self.company = company
        self.notes = notes


SEED = [
    Contact("Amara Osei", "amara.osei@example.com", "+1 415 555 0132",
            "Northwind Analytics", "Prefers email. Renewal due in Q3."),
    Contact("Daniel Roth", "d.roth@example.com", "+1 212 555 0177",
            "Roth & Lane LLP", "Introduced by Priya. Interested in the team plan."),
    Contact("Priya Nair", "priya@example.com", "+44 20 7946 0958",
            "Meridian Design", "Design partner. Fast responder."),
    Contact("Marcus Feld", "marcus.feld@example.com", "+49 30 5557 0021",
            "Feld Robotics", "Evaluating enterprise tier."),
]


class Contacts(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Contacts")
        self.contacts = list(SEED)
        self.current = 0

        root = QWidget()
        root.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(18)

        outer.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(self._build_list_panel(), stretch=2)
        body.addWidget(self._build_detail_panel(), stretch=3)
        outer.addLayout(body)

        self._refresh_list()
        self._load(self.current)

    # -- Header --
    def _build_header(self):
        row = QHBoxLayout()
        col = QVBoxLayout()
        title = QLabel("Contacts")
        title.setStyleSheet(f"color: {TEXT}; font-size: 24px; font-weight: 600;")
        self.subtitle = QLabel("")
        self.subtitle.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
        col.addWidget(title)
        col.addWidget(self.subtitle)
        row.addLayout(col)
        row.addStretch()

        add = QPushButton("New contact")
        add.setStyleSheet(
            f"background-color: {ACCENT}; color: #ffffff; font-size: 14px; "
            f"font-weight: 600; padding: 9px 18px; border: none; border-radius: 6px;"
        )
        add.clicked.connect(self._add)
        row.addWidget(add)
        return row

    # -- Left: list --
    def _build_list_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            f"background-color: {SURFACE}; border: 1px solid {BORDER}; "
            f"border-radius: 8px; padding: 8px;"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        self.list = QListWidget()
        self.list.setStyleSheet(
            f"background-color: transparent; color: {TEXT}; border: none; "
            f"font-size: 14px;"
        )
        self.list.currentRowChanged.connect(self._on_select)
        layout.addWidget(self.list)
        return panel

    # -- Right: detail form --
    def _build_detail_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            f"background-color: {SURFACE}; border: 1px solid {BORDER}; "
            f"border-radius: 8px; padding: 24px;"
        )
        layout = QVBoxLayout(panel)
        layout.setSpacing(16)

        self.name = self._input()
        self.email = self._input()
        self.phone = self._input()
        self.company = self._input()

        self.notes = QTextEdit()
        self.notes.setStyleSheet(
            f"background-color: {SURFACE}; color: {TEXT}; padding: 10px; "
            f"border: 1px solid {BORDER}; border-radius: 6px;"
        )

        layout.addWidget(self._field("Name", self.name))
        layout.addWidget(self._field("Email", self.email))
        layout.addWidget(self._field("Phone", self.phone))
        layout.addWidget(self._field("Company", self.company))
        layout.addWidget(self._field("Notes", self.notes))

        actions = QHBoxLayout()
        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        actions.addWidget(self.status)
        actions.addStretch()

        delete = QPushButton("Delete")
        delete.setStyleSheet(
            f"background-color: {SURFACE}; color: {DANGER}; font-size: 14px; "
            f"padding: 9px 16px; border: 1px solid {BORDER}; border-radius: 6px;"
        )
        delete.clicked.connect(self._delete)

        save = QPushButton("Save")
        save.setStyleSheet(
            f"background-color: {ACCENT}; color: #ffffff; font-size: 14px; "
            f"font-weight: 600; padding: 9px 18px; border: none; border-radius: 6px;"
        )
        save.clicked.connect(self._save)

        actions.addWidget(delete)
        actions.addWidget(save)
        layout.addLayout(actions)
        layout.addStretch()
        return panel

    def _input(self):
        edit = QLineEdit()
        edit.setStyleSheet(
            f"background-color: {SURFACE}; color: {TEXT}; padding: 8px 10px; "
            f"border: 1px solid {BORDER}; border-radius: 6px;"
        )
        return edit

    def _field(self, label_text, widget):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {MUTED}; font-size: 13px; font-weight: 500;")
        v.addWidget(label)
        v.addWidget(widget)
        return box

    # -- Behaviour --
    def _refresh_list(self):
        self.list.clear()
        for c in self.contacts:
            self.list.addItem(c.name or "(unnamed)")
        self.subtitle.setText(f"{len(self.contacts)} contacts")
        if 0 <= self.current < len(self.contacts):
            self.list.setCurrentRow(self.current)

    def _on_select(self, row):
        if 0 <= row < len(self.contacts):
            self.current = row
            self._load(row)

    def _load(self, row):
        if not (0 <= row < len(self.contacts)):
            return
        c = self.contacts[row]
        self.name.setText(c.name)
        self.email.setText(c.email)
        self.phone.setText(c.phone)
        self.company.setText(c.company)
        self.notes.setPlainText(c.notes)
        self.status.setText("")

    def _save(self):
        if not (0 <= self.current < len(self.contacts)):
            return
        c = self.contacts[self.current]
        c.name = self.name.text().strip()
        c.email = self.email.text().strip()
        c.phone = self.phone.text().strip()
        c.company = self.company.text().strip()
        c.notes = self.notes.toPlainText().strip()
        self._refresh_list()
        self.status.setText("Saved.")
        self.status.setStyleSheet(f"color: {ACCENT}; font-size: 13px;")

    def _add(self):
        self.contacts.append(Contact(name="New contact"))
        self.current = len(self.contacts) - 1
        self._refresh_list()
        self._load(self.current)
        self.status.setText("New contact created.")
        self.status.setStyleSheet(f"color: {MUTED}; font-size: 13px;")

    def _delete(self):
        if not (0 <= self.current < len(self.contacts)):
            return
        del self.contacts[self.current]
        self.current = max(0, self.current - 1)
        self._refresh_list()
        if self.contacts:
            self._load(self.current)
        else:
            for w in (self.name, self.email, self.phone, self.company):
                w.setText("")
            self.notes.setPlainText("")
        self.status.setText("Contact deleted.")
        self.status.setStyleSheet(f"color: {MUTED}; font-size: 13px;")


def main():
    app = QApplication([])
    window = Contacts()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
