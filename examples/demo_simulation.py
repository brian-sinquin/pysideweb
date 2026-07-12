"""
PySideWeb Simulation Application — CPU & Memory Monitor and Particle Simulator

This is a premium simulation control center using standard PySide6 APIs,
fully intercepted and rendered on the web via PySideWeb.
"""

import pysideweb  # noqa: F401  Must come before any PySide6 import!

import random
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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


class SimulationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ Quantum Reactor Simulation Console")
        self.resize(600, 750)

        # Simulator State
        self._reactor_active = False
        self._reactor_temp = 285.0
        self._coolant_flow = 50
        self._magnetic_field = 80
        self._power_generation = 0.0
        self._anomalies = []

        # Main Tab Widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Add simulation tabs
        self.tabs.addTab(self._create_dashboard_tab(), "📊 Monitor")
        self.tabs.addTab(self._create_reactor_tab(), "⚛️ Reactor Controls")
        self.tabs.addTab(self._create_logs_tab(), "📜 Event Logs")

        # QTimer for Simulation ticks
        self.sim_timer = QTimer()
        self.sim_timer.timeout.connect(self._simulation_tick)
        self.sim_timer.start(500)  # Tick every 500ms

    def _create_dashboard_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("Simulation Status Dashboard")
        header._extra_classes = ["heading"]
        layout.addWidget(header)

        # Status cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.temp_card = self._create_card("🔥 Temp", "285.0 °C", "Normal Operation")
        self.power_card = self._create_card("⚡ Power Output", "0.0 MW", "Idle")
        self.stability_card = self._create_card("🛡️ Shield Integrity", "100%", "Stable")

        cards_layout.addWidget(self.temp_card)
        cards_layout.addWidget(self.power_card)
        cards_layout.addWidget(self.stability_card)

        cards_container = QWidget()
        cards_container.setLayout(cards_layout)
        layout.addWidget(cards_container)

        # Visual Indicators Group
        metrics_group = QGroupBox("Core Telemetry Indicators")
        metrics_layout = QVBoxLayout()
        metrics_layout.setSpacing(12)

        # Reactor Temperature progress
        metrics_layout.addWidget(QLabel("Core Thermal Capacity:"))
        self.temp_bar = QProgressBar()
        self.temp_bar.setRange(0, 1000)
        self.temp_bar.setValue(285)
        metrics_layout.addWidget(self.temp_bar)

        # Core Stability progress
        metrics_layout.addWidget(QLabel("Magnetic Shield Containment Level:"))
        self.containment_bar = QProgressBar()
        self.containment_bar.setRange(0, 100)
        self.containment_bar.setValue(100)
        metrics_layout.addWidget(self.containment_bar)

        metrics_group.setLayout(metrics_layout)
        layout.addWidget(metrics_group)

        # Quick Control Panel
        control_group = QGroupBox("Operations Console")
        control_layout = QHBoxLayout()

        self.btn_toggle_reactor = QPushButton("🚀 Ignite Reactor Core")
        self.btn_toggle_reactor._extra_classes = ["primary"]
        self.btn_toggle_reactor.clicked.connect(self._toggle_reactor)
        control_layout.addWidget(self.btn_toggle_reactor)

        self.btn_scram = QPushButton("🚨 EMERGENCY SCRAM")
        self.btn_scram.setEnabled(False)
        self.btn_scram.clicked.connect(self._scram_reactor)
        control_layout.addWidget(self.btn_scram)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def _create_reactor_tab(self) -> QWidget:
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Reactor Parameters tuning")
        header._extra_classes = ["heading"]
        layout.addWidget(header)

        # Slider 1: Coolant flow rate
        coolant_group = QGroupBox("Coolant Regulation System")
        coolant_layout = QVBoxLayout()
        coolant_layout.addWidget(QLabel("Adjust Coolant Flow Rate (%):"))

        self.coolant_slider = QSlider(Qt.Horizontal)
        self.coolant_slider.setRange(0, 100)
        self.coolant_slider.setValue(self._coolant_flow)
        self.coolant_slider.valueChanged.connect(self._on_coolant_changed)
        coolant_layout.addWidget(self.coolant_slider)

        coolant_group.setLayout(coolant_layout)
        layout.addWidget(coolant_group)

        # Slider 2: Magnetic containment field
        mag_group = QGroupBox("Magnetic Containment Regulators")
        mag_layout = QVBoxLayout()
        mag_layout.addWidget(QLabel("Magnetic Containment Field Intensity (%):"))

        self.mag_slider = QSlider(Qt.Horizontal)
        self.mag_slider.setRange(20, 120)
        self.mag_slider.setValue(self._magnetic_field)
        self.mag_slider.valueChanged.connect(self._on_mag_changed)
        mag_layout.addWidget(self.mag_slider)

        mag_group.setLayout(mag_layout)
        layout.addWidget(mag_group)

        # Checkboxes for manual override flags
        override_group = QGroupBox("Containment Safety Interlocks")
        override_layout = QVBoxLayout()
        override_layout.setSpacing(8)

        self.chk_safety_valve = QCheckBox("Auxiliary Vent Valve Open")
        override_layout.addWidget(self.chk_safety_valve)

        self.chk_overdrive = QCheckBox("Reactor Overdrive Mode (⚠️ Hazard)")
        override_layout.addWidget(self.chk_overdrive)

        override_group.setLayout(override_layout)
        layout.addWidget(override_group)

        # Control knobs
        params_group = QGroupBox("Target Frequency Setting")
        params_layout = QHBoxLayout()

        params_layout.addWidget(QLabel("Target Sync Frequency:"))
        self.spin_freq = QSpinBox()
        self.spin_freq.setRange(50, 500)
        self.spin_freq.setValue(120)
        self.spin_freq.setSuffix(" Hz")
        params_layout.addWidget(self.spin_freq)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)

        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)
        tab.setLayout(outer_layout)
        return tab

    def _create_logs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QLabel("Simulation Event Log")
        header._extra_classes = ["heading"]
        layout.addWidget(header)

        self.log_list = QListWidget()
        self.log_list.addItem("Simulation Console Initialized.")
        self.log_list.addItem("Magnetic field generators ready.")
        self.log_list.addItem("Waiting for user reactor core ignition...")
        layout.addWidget(self.log_list)

        clear_btn = QPushButton("🧹 Clear Log Console")
        clear_btn.clicked.connect(self._clear_logs)
        layout.addWidget(clear_btn)

        tab.setLayout(layout)
        return tab

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

        self.title_label = QLabel(title)
        self.title_label._extra_classes = ["subheading"]
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label._extra_classes = ["caption"]
        layout.addWidget(self.subtitle_label)

        card.setLayout(layout)
        # Store refs dynamically to set texts later
        card.title_lbl = self.title_label
        card.sub_lbl = self.subtitle_label
        return card

    # ── Simulation Logic & Slots ────────────────────────────────

    def _toggle_reactor(self):
        self._reactor_active = not self._reactor_active
        if self._reactor_active:
            self.btn_toggle_reactor.setText("🛑 Shutdown Reactor Core")
            self.btn_toggle_reactor._extra_classes = ["primary"]
            self.btn_scram.setEnabled(True)
            self._log_event("🟢 Reactor Core Ignition Sequence Completed.")
        else:
            self.btn_toggle_reactor.setText("🚀 Ignite Reactor Core")
            self.btn_toggle_reactor._extra_classes = ["primary"]
            self.btn_scram.setEnabled(False)
            self._log_event("🔴 Reactor Shutdown Sequence Completed.")

    def _scram_reactor(self):
        self._reactor_active = False
        self._reactor_temp = 285.0
        self._power_generation = 0.0
        self.btn_toggle_reactor.setText("🚀 Ignite Reactor Core")
        self.btn_scram.setEnabled(False)
        self._log_event("💥 REACTOR CORES SCRAMMED. Coolant dumped.")
        self.statusBar().showMessage("SYSTEM STATUS: SCRAM TRIGGERED • TEMPERATURE COOLDOWN IN PROGRESS")

    def _on_coolant_changed(self, value):
        self._coolant_flow = value
        self._log_event(f"Coolant flow regulator set to {value}%.")

    def _on_mag_changed(self, value):
        self._magnetic_field = value
        self._log_event(f"Magnetic containment fields output adjusted to {value}%.")

    def _clear_logs(self):
        self.log_list.clear()

    def _log_event(self, text):
        item = QListWidgetItem(text)
        self.log_list.addItem(item)

    def _simulation_tick(self):
        if self._reactor_active:
            # Temperature increases if coolant is too low or overdrive is enabled
            heat_gain = 15.0 if self.chk_overdrive.isChecked() else 8.0
            cooling = (self._coolant_flow / 10.0) * 1.2
            temp_delta = heat_gain - cooling

            self._reactor_temp += temp_delta + random.uniform(-2, 2)
            if self._reactor_temp < 100:
                self._reactor_temp = 100.0

            # Power Generation is proportional to Temperature and Magnetic field
            self._power_generation = (self._reactor_temp * 0.8) * (self._magnetic_field / 100.0)

            # Check magnetic containment failure hazard
            shield_level = 100
            if self._magnetic_field < 50:
                shield_level -= (50 - self._magnetic_field) * 1.5
            if self._reactor_temp > 700:
                shield_level -= (self._reactor_temp - 700) * 0.1
            shield_level = max(0, min(100, int(shield_level)))

            # Update dashboard indicators
            self.temp_card.title_lbl.setText(f"{self._reactor_temp:.1f} °C")
            self.power_card.title_lbl.setText(f"{self._power_generation:.1f} MW")
            self.stability_card.title_lbl.setText(f"{shield_level}%")

            self.temp_bar.setValue(int(min(self._reactor_temp, 1000)))
            self.containment_bar.setValue(shield_level)

            if shield_level < 30:
                self.stability_card.sub_lbl.setText("🚨 CRITICAL LEAK WARNING")
                self.statusBar().showMessage(f"WARNING: MAGNETIC CONFINEMENT BREAKING • SHIELD INTEGRITY {shield_level}%")
                if random.random() < 0.2:
                    self._log_event("⚠️ ALERT: High thermal distortion detected in core magnetic lock.")
            else:
                self.stability_card.sub_lbl.setText("Shield Active")
                self.statusBar().showMessage(f"SYSTEM: RUNNING • POWER OUTPUT: {self._power_generation:.1f} MW")
        else:
            # Cooling down reactor slowly to ambient temp (50C)
            if self._reactor_temp > 50.0:
                self._reactor_temp -= min(5.0, self._reactor_temp - 50.0)
            self._power_generation = 0.0

            self.temp_card.title_lbl.setText(f"{self._reactor_temp:.1f} °C")
            self.power_card.title_lbl.setText("0.0 MW")
            self.stability_card.title_lbl.setText("100%")

            self.temp_bar.setValue(int(self._reactor_temp))
            self.containment_bar.setValue(100)


def main():
    app = QApplication(sys.argv)
    window = SimulationApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
