"""Smart Home control panel — a realistic app built with plain PySide6.

Toggle devices per room, dim lights, set a thermostat, and trigger scenes.
A QTimer drives a live energy meter that reflects whatever is currently on.
Everything renders in the browser thanks to PySideWeb.

    uv run python examples/smart_home.py

Then open http://localhost:8765.
"""

import pysideweb  # noqa: F401  Must come before any PySide6 import!

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# ── Theme ──────────────────────────────────────────────────────────────
BG = "#101418"
PANEL = "#1a2029"
CARD = "#222b36"
BORDER = "#313c4a"
TEXT = "#eef2f6"
MUTED = "#93a1b0"
ACCENT = "#ffb454"   # warm "on" glow
COOL = "#4fc3f7"


def card_style(bg=CARD, radius=14, pad=18):
    return (
        f"background-color: {bg}; border-radius: {radius}px; "
        f"padding: {pad}px; border: 1px solid {BORDER};"
    )


class Device:
    def __init__(self, name, icon, watts, dimmable=False):
        self.name = name
        self.icon = icon
        self.watts = watts          # power draw at full when on
        self.dimmable = dimmable
        self.on = False
        self.level = 100            # brightness %, only if dimmable

    def usage(self):
        if not self.on:
            return 0.0
        factor = (self.level / 100) if self.dimmable else 1.0
        return self.watts * factor


class RoomCard(QFrame):
    """A room with a set of toggleable (optionally dimmable) devices."""

    def __init__(self, room_name, devices, on_change):
        super().__init__()
        self.devices = devices
        self.on_change = on_change
        self._toggles = {}   # device → QCheckBox
        self._sliders = {}   # device → QSlider
        self.setStyleSheet(card_style())

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(room_name)
        title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        for dev in devices:
            layout.addWidget(self._device_row(dev))

    def _device_row(self, dev: Device):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        row = QHBoxLayout()
        toggle = QCheckBox(f"{dev.icon}  {dev.name}")
        toggle.setChecked(dev.on)
        toggle.setStyleSheet(f"color: {TEXT}; font-size: 14px;")
        toggle.toggled.connect(lambda checked, d=dev: self._set_on(d, checked))
        self._toggles[dev] = toggle
        row.addWidget(toggle)
        row.addStretch()
        v.addLayout(row)

        if dev.dimmable:
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(dev.level)
            slider.valueChanged.connect(lambda val, d=dev: self._set_level(d, val))
            self._sliders[dev] = slider
            v.addWidget(slider)
        return box

    def _set_on(self, dev, checked):
        dev.on = checked
        self.on_change()

    def _set_level(self, dev, val):
        dev.level = val
        if val > 0 and not dev.on:
            dev.on = True
        self.on_change()

    def sync(self):
        """Push model state back into the widgets (after a scene change)."""
        for dev, toggle in self._toggles.items():
            toggle.setChecked(dev.on)
        for dev, slider in self._sliders.items():
            slider.setValue(dev.level)


class SmartHome(QMainWindow):
    ENERGY_BUDGET = 3000  # watts, meter full-scale

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🏠 Smart Home — PySideWeb")

        # Model: rooms → devices
        self.rooms = {
            "Living Room": [
                Device("Ceiling Light", "💡", 60, dimmable=True),
                Device("Smart TV", "📺", 120),
                Device("Speakers", "🔊", 40),
            ],
            "Kitchen": [
                Device("Under-cabinet", "💡", 45, dimmable=True),
                Device("Coffee Maker", "☕", 900),
                Device("Dishwasher", "🍽️", 1200),
            ],
            "Bedroom": [
                Device("Lamp", "🛏️", 30, dimmable=True),
                Device("Air Purifier", "🌀", 55),
                Device("Phone Charger", "🔌", 15),
            ],
            "Office": [
                Device("Desk Light", "💡", 40, dimmable=True),
                Device("Computer", "🖥️", 250),
                Device("Monitor", "🖥️", 60),
            ],
        }
        self.thermostat = 21  # °C

        root = QWidget()
        root.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(20)

        outer.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(20)
        body.addLayout(self._build_rooms(), stretch=3)
        body.addWidget(self._build_sidebar(), stretch=1)
        outer.addLayout(body)

        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(700)
        self._refresh()

    # -- Header --
    def _build_header(self):
        row = QHBoxLayout()
        col = QVBoxLayout()
        title = QLabel("Smart Home")
        title.setStyleSheet(f"color: {TEXT}; font-size: 28px; font-weight: 800;")
        sub = QLabel("Control panel")
        sub.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        col.addWidget(title)
        col.addWidget(sub)
        row.addLayout(col)
        row.addStretch()

        self.summary = QLabel()
        self.summary.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        self.summary.setAlignment(Qt.AlignRight)
        row.addWidget(self.summary)
        return row

    # -- Rooms grid --
    def _build_rooms(self):
        col = QVBoxLayout()
        heading = QLabel("Rooms")
        heading.setStyleSheet(f"color: {MUTED}; font-size: 14px; font-weight: 700;")
        col.addWidget(heading)

        grid = QGridLayout()
        grid.setSpacing(16)
        self.room_cards = []
        for i, (name, devices) in enumerate(self.rooms.items()):
            card = RoomCard(name, devices, self._refresh)
            self.room_cards.append(card)
            grid.addWidget(card, i // 2, i % 2)
        col.addLayout(grid)
        col.addStretch()
        return col

    # -- Sidebar: energy + thermostat + scenes --
    def _build_sidebar(self):
        panel = QFrame()
        panel.setStyleSheet(card_style(bg=PANEL, pad=20))
        layout = QVBoxLayout(panel)
        layout.setSpacing(14)

        # Energy meter
        e_head = QLabel("⚡ Live Energy")
        e_head.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: 700;")
        layout.addWidget(e_head)

        self.energy_value = QLabel("0 W")
        self.energy_value.setStyleSheet(f"color: {ACCENT}; font-size: 32px; font-weight: 800;")
        layout.addWidget(self.energy_value)

        self.energy_bar = QProgressBar()
        self.energy_bar.setRange(0, self.ENERGY_BUDGET)
        self.energy_bar.setTextVisible(False)
        layout.addWidget(self.energy_bar)

        self.energy_hint = QLabel()
        self.energy_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        layout.addWidget(self.energy_hint)

        layout.addWidget(self._divider())

        # Thermostat
        t_head = QLabel("🌡️ Thermostat")
        t_head.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: 700;")
        layout.addWidget(t_head)

        self.temp_label = QLabel(f"{self.thermostat}°C")
        self.temp_label.setStyleSheet(f"color: {COOL}; font-size: 28px; font-weight: 800;")
        self.temp_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.temp_label)

        temp_row = QHBoxLayout()
        minus = QPushButton("−")
        plus = QPushButton("+")
        for b in (minus, plus):
            b.setStyleSheet(
                f"background-color: {CARD}; color: {TEXT}; font-size: 20px; "
                f"font-weight: 700; padding: 6px; border: 1px solid {BORDER}; "
                f"border-radius: 8px;"
            )
        minus.clicked.connect(lambda: self._nudge_temp(-1))
        plus.clicked.connect(lambda: self._nudge_temp(+1))
        temp_row.addWidget(minus)
        temp_row.addWidget(plus)
        layout.addLayout(temp_row)

        layout.addWidget(self._divider())

        # Scenes
        s_head = QLabel("🎬 Scenes")
        s_head.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: 700;")
        layout.addWidget(s_head)

        for label, handler in [
            ("🌅  Morning", self._scene_morning),
            ("🎥  Movie Night", self._scene_movie),
            ("🚪  Away", self._scene_away),
            ("🌙  Good Night", self._scene_night),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                f"background-color: {CARD}; color: {TEXT}; font-size: 14px; "
                f"text-align: left; padding: 10px 14px; border: 1px solid {BORDER}; "
                f"border-radius: 8px;"
            )
            btn.clicked.connect(handler)
            layout.addWidget(btn)

        layout.addStretch()
        return panel

    def _divider(self):
        d = QFrame()
        d.setStyleSheet(f"background-color: {BORDER}; max-height: 1px;")
        d.setFixedHeight(1)
        return d

    # -- Thermostat --
    def _nudge_temp(self, delta):
        self.thermostat = max(15, min(30, self.thermostat + delta))
        self.temp_label.setText(f"{self.thermostat}°C")
        color = COOL if self.thermostat <= 22 else ACCENT
        self.temp_label.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: 800;")

    # -- Scenes --
    def _all_devices(self):
        for devices in self.rooms.values():
            yield from devices

    def _set_all(self, predicate):
        for dev in self._all_devices():
            dev.on = predicate(dev)
        self._sync_rooms()

    def _scene_morning(self):
        for dev in self._all_devices():
            dev.on = dev.icon in ("💡", "☕", "🖥️")
            if dev.dimmable:
                dev.level = 80
        self._nudge_temp(22 - self.thermostat)
        self._sync_rooms()

    def _scene_movie(self):
        for dev in self._all_devices():
            dev.on = dev.name in ("Smart TV", "Speakers")
            if dev.dimmable:
                dev.level = 15
                dev.on = dev.name == "Ceiling Light"
        self._sync_rooms()

    def _scene_away(self):
        self._set_all(lambda d: False)

    def _scene_night(self):
        for dev in self._all_devices():
            dev.on = dev.name in ("Lamp", "Air Purifier")
            if dev.name == "Lamp":
                dev.level = 25
        self._nudge_temp(19 - self.thermostat)
        self._sync_rooms()

    def _sync_rooms(self):
        # Scenes mutate many devices; push that state back into each room's
        # toggles/sliders, then refresh the meter.
        for card in self.room_cards:
            card.sync()
        self._refresh()

    # -- Live refresh --
    def _refresh(self):
        total = sum(dev.usage() for dev in self._all_devices())
        on_count = sum(1 for dev in self._all_devices() if dev.on)
        self.energy_value.setText(f"{total:,.0f} W")
        self.energy_bar.setValue(int(min(total, self.ENERGY_BUDGET)))

        if total < 500:
            state = "Efficient 🟢"
        elif total < 1500:
            state = "Moderate 🟡"
        else:
            state = "High usage 🔴"
        self.energy_hint.setText(f"{state} — {on_count} devices on")

        est_daily = total * 24 / 1000  # kWh/day if held constant
        self.summary.setText(
            f"{on_count} devices on · {total:,.0f} W now · ~{est_daily:.1f} kWh/day"
        )


def main():
    app = QApplication([])
    window = SmartHome()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
