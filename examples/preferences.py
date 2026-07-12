"""Preferences — an application settings screen built with plain PySide6.

A restrained, professional layout: grouped sections of labelled controls with a
Save / Reset action bar. Demonstrates line edits, dropdowns, checkboxes, and a
slider working together. Renders in the browser thanks to PySideWeb.

    uv run python examples/preferences.py

Then open http://localhost:8765.
"""

import pysideweb  # noqa: F401  Must come before any PySide6 import!

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
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

DEFAULTS = {
    "display_name": "Jordan Avery",
    "language": 0,       # English
    "timezone": 2,       # UTC
    "theme": 0,          # System
    "density": 1,        # Comfortable
    "email_updates": True,
    "product_news": False,
    "desktop_alerts": True,
    "analytics": True,
}


def section_style():
    return (
        f"background-color: {SURFACE}; border: 1px solid {BORDER}; "
        f"border-radius: 8px; padding: 20px;"
    )


class Preferences(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Preferences")

        root = QWidget()
        root.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(40, 32, 40, 32)
        outer.setSpacing(20)

        title = QLabel("Preferences")
        title.setStyleSheet(f"color: {TEXT}; font-size: 24px; font-weight: 600;")
        subtitle = QLabel("Manage your account and application settings.")
        subtitle.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        # -- General --
        self.display_name = QLineEdit(DEFAULTS["display_name"])
        self._style_input(self.display_name)

        self.language = self._combo(["English", "Français", "Deutsch", "日本語"])
        self.timezone = self._combo(
            ["Pacific (UTC−8)", "Eastern (UTC−5)", "UTC", "Central European (UTC+1)"]
        )
        outer.addWidget(self._section("General", [
            ("Display name", self.display_name),
            ("Language", self.language),
            ("Time zone", self.timezone),
        ]))

        # -- Appearance --
        self.theme = self._combo(["System", "Light", "Dark"])
        self.density = QSlider(Qt.Horizontal)
        self.density.setRange(0, 2)
        self.density.setValue(DEFAULTS["density"])
        self.density_label = QLabel()
        self.density.valueChanged.connect(self._update_density_label)
        density_row = QWidget()
        dv = QHBoxLayout(density_row)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(12)
        dv.addWidget(self.density, stretch=1)
        dv.addWidget(self.density_label)
        outer.addWidget(self._section("Appearance", [
            ("Theme", self.theme),
            ("Interface density", density_row),
        ]))

        # -- Notifications --
        self.email_updates = self._check("Email me account and security updates",
                                         DEFAULTS["email_updates"])
        self.product_news = self._check("Send occasional product news",
                                        DEFAULTS["product_news"])
        self.desktop_alerts = self._check("Show desktop alerts",
                                          DEFAULTS["desktop_alerts"])
        self.analytics = self._check("Share anonymous usage analytics",
                                     DEFAULTS["analytics"])
        outer.addWidget(self._section("Notifications & Privacy", [
            (None, self.email_updates),
            (None, self.product_news),
            (None, self.desktop_alerts),
            (None, self.analytics),
        ]))

        # -- Action bar --
        outer.addLayout(self._action_bar())
        outer.addStretch()

        self._update_density_label(self.density.value())

    # -- Builders --
    def _section(self, heading, rows):
        frame = QFrame()
        frame.setStyleSheet(section_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(16)

        head = QLabel(heading)
        head.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: 600;")
        layout.addWidget(head)

        for label_text, widget in rows:
            layout.addWidget(self._row(label_text, widget))
        return frame

    def _row(self, label_text, widget):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        if label_text is not None:
            label = QLabel(label_text)
            label.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
            label.setFixedWidth(160)
            h.addWidget(label)
        h.addWidget(widget, stretch=1)
        return row

    def _combo(self, items):
        combo = QComboBox()
        for item in items:
            combo.addItem(item)
        combo.setStyleSheet(
            f"background-color: {SURFACE}; color: {TEXT}; padding: 8px 10px; "
            f"border: 1px solid {BORDER}; border-radius: 6px;"
        )
        return combo

    def _check(self, text, checked):
        box = QCheckBox(text)
        box.setChecked(checked)
        box.setStyleSheet(f"color: {TEXT}; font-size: 14px;")
        return box

    def _style_input(self, widget):
        widget.setStyleSheet(
            f"background-color: {SURFACE}; color: {TEXT}; padding: 8px 10px; "
            f"border: 1px solid {BORDER}; border-radius: 6px;"
        )

    def _action_bar(self):
        bar = QHBoxLayout()
        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        bar.addWidget(self.status)
        bar.addStretch()

        reset = QPushButton("Reset")
        reset.setStyleSheet(
            f"background-color: {SURFACE}; color: {TEXT}; font-size: 14px; "
            f"padding: 9px 18px; border: 1px solid {BORDER}; border-radius: 6px;"
        )
        reset.clicked.connect(self._reset)

        save = QPushButton("Save changes")
        save.setStyleSheet(
            f"background-color: {ACCENT}; color: #ffffff; font-size: 14px; "
            f"font-weight: 600; padding: 9px 18px; border: none; border-radius: 6px;"
        )
        save.clicked.connect(self._save)

        bar.addWidget(reset)
        bar.addWidget(save)
        return bar

    # -- Behaviour --
    def _update_density_label(self, value):
        self.density_label.setText(["Compact", "Comfortable", "Spacious"][value])
        self.density_label.setStyleSheet(f"color: {TEXT}; font-size: 14px;")

    def _save(self):
        name = self.display_name.text().strip() or "—"
        theme = self.theme.currentText()
        self.status.setText(f"Saved. Display name “{name}”, {theme} theme.")
        self.status.setStyleSheet(f"color: {ACCENT}; font-size: 13px;")

    def _reset(self):
        self.display_name.setText(DEFAULTS["display_name"])
        self.language.setCurrentIndex(DEFAULTS["language"])
        self.timezone.setCurrentIndex(DEFAULTS["timezone"])
        self.theme.setCurrentIndex(DEFAULTS["theme"])
        self.density.setValue(DEFAULTS["density"])
        self.email_updates.setChecked(DEFAULTS["email_updates"])
        self.product_news.setChecked(DEFAULTS["product_news"])
        self.desktop_alerts.setChecked(DEFAULTS["desktop_alerts"])
        self.analytics.setChecked(DEFAULTS["analytics"])
        self.status.setText("Reset to defaults.")
        self.status.setStyleSheet(f"color: {MUTED}; font-size: 13px;")


def main():
    app = QApplication([])
    window = Preferences()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
