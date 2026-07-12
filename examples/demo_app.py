"""
PySideWeb Demo — Phone-Style Application

A full-featured demo app written in standard PySide6 API.
The only difference: `import pysideweb` at the top intercepts all PySide6
imports and renders the UI in your web browser at http://localhost:8765

Run with:
    uv run python demo_app.py
"""

# ─── THIS IS THE MAGIC LINE ────────────────────────────────────────
import pysideweb  # noqa: F401  Must come before any PySide6 import!
# ────────────────────────────────────────────────────────────────────

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class PhoneApp(QMainWindow):
    """A simulated phone interface with multiple tabs."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("📱 MyPhone — PySideWeb Demo")

        # Central widget with tabs
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Create tabs
        self.tabs.addTab(self._create_home_tab(), "🏠 Home")
        self.tabs.addTab(self._create_messages_tab(), "💬 Messages")
        self.tabs.addTab(self._create_settings_tab(), "⚙️ Settings")
        self.tabs.addTab(self._create_profile_tab(), "👤 Profile")

        # Status bar
        self.statusBar().showMessage("📶 Connected  •  🔋 87%  •  12:42 PM")

        # Timer for dynamic updates
        self._progress_value = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_progress)
        self._timer.start(100)

        # Counter for button demo
        self._click_count = 0

    # ── Home Tab ────────────────────────────────────────────────

    def _create_home_tab(self):
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Welcome header
        header = QLabel("Welcome back, Brian! 👋")
        header._extra_classes = ["heading"]
        layout.addWidget(header)

        subtitle = QLabel("Here's what's happening today")
        subtitle._extra_classes = ["caption"]
        layout.addWidget(subtitle)

        # Search bar
        search = QLineEdit()
        search.setPlaceholderText("🔍  Search anything...")
        search.textChanged.connect(self._on_search)
        layout.addWidget(search)

        # Feature cards row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        card1 = self._create_card("📊", "Analytics", "View your stats")
        card2 = self._create_card("📁", "Files", "12 new files")
        card3 = self._create_card("🔔", "Alerts", "3 unread")

        cards_layout.addWidget(card1)
        cards_layout.addWidget(card2)
        cards_layout.addWidget(card3)

        cards_container = QWidget()
        cards_container.setLayout(cards_layout)
        layout.addWidget(cards_container)

        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(8)

        # Counter button
        self.counter_label = QLabel("Button clicks: 0")
        actions_layout.addWidget(self.counter_label)

        btn_row = QHBoxLayout()
        btn_click = QPushButton("🖱️ Click Me!")
        btn_click._extra_classes = ["primary"]
        btn_click.clicked.connect(self._on_click)
        btn_row.addWidget(btn_click)

        btn_reset = QPushButton("↩️ Reset")
        btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(btn_reset)

        btn_container = QWidget()
        btn_container.setLayout(btn_row)
        actions_layout.addWidget(btn_container)

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        # Progress section
        progress_group = QGroupBox("Download Progress")
        progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Downloading... 0%")
        self.progress_label._extra_classes = ["caption"]
        progress_layout.addWidget(self.progress_label)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        layout.addStretch()

        content.setLayout(layout)
        scroll.setWidget(content)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll)

        page.setLayout(outer)
        return page

    def _create_card(self, icon: str, title: str, subtitle: str) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            "background: rgba(99, 102, 241, 0.08); "
            "border: 1px solid rgba(99, 102, 241, 0.15); "
            "border-radius: 12px; "
            "padding: 16px;"
        )

        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 28px;")
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label._extra_classes = ["subheading"]
        layout.addWidget(title_label)

        sub_label = QLabel(subtitle)
        sub_label._extra_classes = ["caption"]
        layout.addWidget(sub_label)

        card.setLayout(layout)
        return card

    # ── Messages Tab ────────────────────────────────────────────

    def _create_messages_tab(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Messages")
        title._extra_classes = ["heading"]
        layout.addWidget(title)

        # Message list
        self.message_list = QListWidget()
        messages = [
            ("📩", "Alice — Hey, how's the project going?"),
            ("📩", "Bob — Meeting at 3pm tomorrow"),
            ("📨", "Charlie — Sent you the files"),
            ("📩", "Diana — Can you review my PR?"),
            ("📨", "Eve — Thanks for the help!"),
            ("📩", "Frank — Lunch plans?"),
            ("📨", "Grace — Updated the docs"),
            ("📩", "Hank — Build passed ✅"),
        ]

        for icon, text in messages:
            item = QListWidgetItem(f"{icon}  {text}")
            self.message_list.addItem(item)

        self.message_list.currentRowChanged.connect(self._on_message_selected)
        layout.addWidget(self.message_list)

        # Message preview
        self.message_preview = QLabel("Select a message to preview")
        self.message_preview._extra_classes = ["caption"]
        self.message_preview.setWordWrap(True)
        layout.addWidget(self.message_preview)

        # Reply input
        reply_row = QHBoxLayout()

        self.reply_input = QLineEdit()
        self.reply_input.setPlaceholderText("Type a reply...")
        reply_row.addWidget(self.reply_input)

        send_btn = QPushButton("📤 Send")
        send_btn._extra_classes = ["primary"]
        send_btn.clicked.connect(self._on_send_message)
        reply_row.addWidget(send_btn)

        reply_container = QWidget()
        reply_container.setLayout(reply_row)
        layout.addWidget(reply_container)

        page.setLayout(layout)
        return page

    # ── Settings Tab ────────────────────────────────────────────

    def _create_settings_tab(self):
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Settings")
        title._extra_classes = ["heading"]
        layout.addWidget(title)

        # Display settings
        display_group = QGroupBox("Display")
        display_layout = QVBoxLayout()
        display_layout.setSpacing(10)

        # Theme selector
        theme_row = QHBoxLayout()
        theme_label = QLabel("Theme")
        theme_row.addWidget(theme_label)
        theme_combo = QComboBox()
        theme_combo.addItems(["Dark Mode", "Light Mode", "Auto", "High Contrast"])
        theme_row.addWidget(theme_combo)
        theme_container = QWidget()
        theme_container.setLayout(theme_row)
        display_layout.addWidget(theme_container)

        # Brightness slider
        brightness_row = QHBoxLayout()
        bright_label = QLabel("Brightness")
        brightness_row.addWidget(bright_label)
        brightness_slider = QSlider(Qt.Horizontal)
        brightness_slider.setRange(0, 100)
        brightness_slider.setValue(75)
        brightness_row.addWidget(brightness_slider)
        bright_container = QWidget()
        bright_container.setLayout(brightness_row)
        display_layout.addWidget(bright_container)

        # Font size
        font_row = QHBoxLayout()
        font_label = QLabel("Font Size")
        font_row.addWidget(font_label)
        font_spin = QSpinBox()
        font_spin.setRange(10, 24)
        font_spin.setValue(14)
        font_spin.setSuffix(" px")
        font_row.addWidget(font_spin)
        font_container = QWidget()
        font_container.setLayout(font_row)
        display_layout.addWidget(font_container)

        display_group.setLayout(display_layout)
        layout.addWidget(display_group)

        # Notifications
        notif_group = QGroupBox("Notifications")
        notif_layout = QVBoxLayout()
        notif_layout.setSpacing(8)

        push_check = QCheckBox("Enable push notifications")
        push_check.setChecked(True)
        notif_layout.addWidget(push_check)

        sound_check = QCheckBox("Notification sounds")
        sound_check.setChecked(True)
        notif_layout.addWidget(sound_check)

        badge_check = QCheckBox("Show badge count")
        badge_check.setChecked(True)
        notif_layout.addWidget(badge_check)

        preview_check = QCheckBox("Show message preview")
        notif_layout.addWidget(preview_check)

        notif_group.setLayout(notif_layout)
        layout.addWidget(notif_group)

        # Privacy
        privacy_group = QGroupBox("Privacy & Security")
        privacy_layout = QVBoxLayout()
        privacy_layout.setSpacing(8)

        lock_check = QCheckBox("Require Face ID / Password")
        lock_check.setChecked(True)
        privacy_layout.addWidget(lock_check)

        analytics_check = QCheckBox("Share usage analytics")
        privacy_layout.addWidget(analytics_check)

        # Auto-lock timeout
        timeout_row = QHBoxLayout()
        timeout_label = QLabel("Auto-lock timeout")
        timeout_row.addWidget(timeout_label)
        timeout_combo = QComboBox()
        timeout_combo.addItems(["30 seconds", "1 minute", "5 minutes", "15 minutes", "Never"])
        timeout_combo.setCurrentIndex(2)
        timeout_row.addWidget(timeout_combo)
        timeout_container = QWidget()
        timeout_container.setLayout(timeout_row)
        privacy_layout.addWidget(timeout_container)

        privacy_group.setLayout(privacy_layout)
        layout.addWidget(privacy_group)

        # Storage
        storage_group = QGroupBox("Storage")
        storage_layout = QVBoxLayout()

        storage_label = QLabel("Used: 42.3 GB of 128 GB")
        storage_label._extra_classes = ["caption"]
        storage_layout.addWidget(storage_label)

        storage_bar = QProgressBar()
        storage_bar.setRange(0, 128)
        storage_bar.setValue(42)
        storage_layout.addWidget(storage_bar)

        clear_btn = QPushButton("🗑️ Clear Cache")
        clear_btn.clicked.connect(lambda: self.statusBar().showMessage("Cache cleared! ✨"))
        storage_layout.addWidget(clear_btn)

        storage_group.setLayout(storage_layout)
        layout.addWidget(storage_group)

        layout.addStretch()

        content.setLayout(layout)
        scroll.setWidget(content)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll)

        page.setLayout(outer)
        return page

    # ── Profile Tab ─────────────────────────────────────────────

    def _create_profile_tab(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Avatar area
        avatar = QLabel("🧑‍💻")
        avatar.setStyleSheet("font-size: 64px; text-align: center;")
        avatar.setAlignment(Qt.AlignCenter)
        layout.addWidget(avatar)

        name = QLabel("Brian Developer")
        name._extra_classes = ["heading"]
        name.setAlignment(Qt.AlignCenter)
        layout.addWidget(name)

        role = QLabel("Full-Stack Engineer • Paris, France")
        role._extra_classes = ["caption"]
        role.setAlignment(Qt.AlignCenter)
        layout.addWidget(role)

        # Stats row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        stats_layout.addWidget(self._create_stat("127", "Projects"))
        stats_layout.addWidget(self._create_stat("3.2k", "Commits"))
        stats_layout.addWidget(self._create_stat("89", "PRs"))

        stats_container = QWidget()
        stats_container.setLayout(stats_layout)
        layout.addWidget(stats_container)

        # Edit profile
        edit_group = QGroupBox("Edit Profile")
        edit_layout = QVBoxLayout()
        edit_layout.setSpacing(10)

        name_input = QLineEdit("Brian Developer")
        name_input.setPlaceholderText("Full name")
        edit_layout.addWidget(QLabel("Name"))
        edit_layout.addWidget(name_input)

        email_input = QLineEdit("brian@example.com")
        email_input.setPlaceholderText("Email address")
        edit_layout.addWidget(QLabel("Email"))
        edit_layout.addWidget(email_input)

        # Status selector
        edit_layout.addWidget(QLabel("Status"))
        status_combo = QComboBox()
        status_combo.addItems(["🟢 Available", "🟡 Away", "🔴 Do Not Disturb", "⚫ Invisible"])
        edit_layout.addWidget(status_combo)

        save_btn = QPushButton("💾 Save Changes")
        save_btn._extra_classes = ["primary"]
        save_btn.clicked.connect(lambda: self.statusBar().showMessage("Profile saved! ✅"))
        edit_layout.addWidget(save_btn)

        edit_group.setLayout(edit_layout)
        layout.addWidget(edit_group)

        layout.addStretch()

        page.setLayout(layout)
        return page

    def _create_stat(self, value: str, label: str) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            "background: rgba(99, 102, 241, 0.08); "
            "border: 1px solid rgba(99, 102, 241, 0.15); "
            "border-radius: 10px; "
            "padding: 12px;"
        )

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        val_label = QLabel(value)
        val_label._extra_classes = ["subheading"]
        val_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(val_label)

        name_label = QLabel(label)
        name_label._extra_classes = ["caption"]
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)

        card.setLayout(layout)
        return card

    # ── Event Handlers ──────────────────────────────────────────

    def _on_search(self, text):
        self.statusBar().showMessage(f"🔍 Searching: {text}" if text else "📶 Connected  •  🔋 87%  •  12:42 PM")

    def _on_click(self):
        self._click_count += 1
        self.counter_label.setText(f"Button clicks: {self._click_count} 🎉")

    def _on_reset(self):
        self._click_count = 0
        self.counter_label.setText("Button clicks: 0")

    def _on_message_selected(self, row):
        if row >= 0:
            item = self.message_list.item(row)
            if item:
                self.message_preview.setText(f"Preview: {item.text()}")

    def _on_send_message(self):
        text = self.reply_input.text()
        if text:
            item = QListWidgetItem(f"📤  You: {text}")
            self.message_list.addItem(item)
            self.reply_input.setText("")
            self.statusBar().showMessage("Message sent! ✉️")

    def _update_progress(self):
        self._progress_value += 1
        if self._progress_value > 100:
            self._progress_value = 0
        self.progress_bar.setValue(self._progress_value)
        self.progress_label.setText(f"Downloading... {self._progress_value}%")


def main():
    app = QApplication(sys.argv)
    window = PhoneApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
