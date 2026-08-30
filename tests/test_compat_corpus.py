"""Compatibility corpus: realistic PySide6 snippets must build and serialize
without raising. This is the direct "does unmodified Qt code run?" metric --
each scenario exercises a mix of API surface the way real apps combine it.
"""

import pytest

from pysideweb import state


def scenario_counter():
    from PySide6.QtCore import QTimer, Slot
    from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

    class Counter(QWidget):
        def __init__(self):
            super().__init__()
            self._n = 0
            lay = QVBoxLayout(self)
            self.label = QLabel("0")
            btn = QPushButton("Increment")
            btn.clicked.connect(self.bump)
            lay.addWidget(self.label)
            lay.addWidget(btn)
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.bump)

        @Slot()
        def bump(self):
            self._n += 1
            self.label.setText(str(self._n))

    c = Counter()
    c.bump()
    c.setWindowTitle("Counter")
    c.show()
    return c


def scenario_form_with_settings():
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import (
        QCheckBox,
        QFormLayout,
        QLineEdit,
        QMainWindow,
        QSpinBox,
        QWidget,
    )

    win = QMainWindow()
    win.setWindowTitle("Prefs")
    central = QWidget()
    form = QFormLayout(central)
    name = QLineEdit()
    age = QSpinBox()
    age.setRange(0, 120)
    notify = QCheckBox("Email me")
    form.addRow("Name", name)
    form.addRow("Age", age)
    form.addRow(notify)
    win.setCentralWidget(central)

    settings = QSettings("PySideWebTests", "corpus")
    name.setText(settings.value("name", "Anon"))
    age.setValue(int(settings.value("age", 30)))
    win.show()
    return win


def scenario_model_free_list():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

    w = QWidget()
    lay = QVBoxLayout(w)
    lst = QListWidget()
    for i in range(5):
        it = QListWidgetItem(f"Row {i}")
        it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        lst.addItem(it)
    lst.setCurrentRow(2)
    lay.addWidget(lst)
    w.show()
    return w


def scenario_custom_paint():
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QBrush, QColor, QPainter, QPen
    from PySide6.QtWidgets import QWidget

    class Swatch(QWidget):
        def __init__(self):
            super().__init__()
            self.setFixedSize(200, 120)

        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor("#334455"), 2))
            p.setBrush(QBrush(QColor("steelblue")))
            p.drawRoundedRect(QRectF(4, 4, 192, 112), 8, 8)
            p.setPen(Qt.white)
            p.drawText(16, 60, "hello")
            p.end()

    s = Swatch()
    s.update()
    s.show()
    return s


def scenario_signals_between_objects():
    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtWidgets import QLabel, QSlider, QVBoxLayout, QWidget

    class Model(QObject):
        changed = Signal(int)

        def __init__(self):
            super().__init__()
            self._v = 0

        def set(self, v):
            if v != self._v:
                self._v = v
                self.changed.emit(v)

    w = QWidget()
    lay = QVBoxLayout(w)
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, 100)
    label = QLabel("0")
    model = Model()
    slider.valueChanged.connect(model.set)
    model.changed.connect(lambda v: label.setText(str(v)))
    lay.addWidget(slider)
    lay.addWidget(label)
    slider._handle_event("valueChanged", 42)
    w.show()
    assert label.text() == "42"
    return w


def scenario_menu_and_actions():
    from PySide6.QtGui import QAction, QKeySequence
    from PySide6.QtWidgets import QMainWindow

    win = QMainWindow()
    menu = win.menuBar().addMenu("&File")
    act = QAction("Save", win)
    act.setShortcut(QKeySequence("Ctrl+S"))
    triggered = []
    act.triggered.connect(lambda: triggered.append(1))
    menu.addAction(act)
    act.trigger()
    assert triggered == [1]
    win.show()
    return win


def scenario_unknown_thirdparty_widget():
    # A stand-in for a library that subclasses a class pysideweb doesn't model.
    from PySide6.QtWidgets import QGraphicsView, QVBoxLayout, QWidget

    class PlotWidget(QGraphicsView):
        def __init__(self):
            super().__init__()
            self.setInteractive(True)
            self.centerOn(0, 0)

    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addWidget(PlotWidget())
    w.show()
    return w


SCENARIOS = [
    scenario_counter,
    scenario_form_with_settings,
    scenario_model_free_list,
    scenario_custom_paint,
    scenario_signals_between_objects,
    scenario_menu_and_actions,
    scenario_unknown_thirdparty_widget,
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda f: f.__name__)
def test_scenario_builds_and_serializes(scenario):
    scenario()
    tree = state.full_tree_json()
    assert isinstance(tree, str) and len(tree) > 2
    # Re-serialize (exercises the per-widget _get_props again, incl. paint).
    state.serialize_full_tree()
