"""Tests for virtual widgets and browser-event handling."""

from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class TestQPushButton:
    def test_text_roundtrip(self):
        b = QPushButton("Save")
        assert b.text() == "Save"
        b.setText("Cancel")
        assert b.text() == "Cancel"

    def test_click_event_fires_signal(self):
        b = QPushButton("Go")
        fired = []
        b.clicked.connect(lambda *_: fired.append(True))
        b._handle_event("clicked", None)
        assert fired == [True]

    def test_checkable_toggles(self):
        b = QPushButton("Toggle")
        b.setCheckable(True)
        b._handle_event("clicked", None)
        assert b.isChecked() is True
        b._handle_event("clicked", None)
        assert b.isChecked() is False


class TestQLabel:
    def test_text(self):
        assert QLabel("Hi").text() == "Hi"


class TestQLineEdit:
    def test_text_changed_event(self):
        e = QLineEdit()
        seen = []
        e.textChanged.connect(seen.append)
        e._handle_event("textChanged", "hello")
        assert e.text() == "hello"
        assert seen == ["hello"]


class TestQSlider:
    def test_value_changed_event(self):
        s = QSlider()
        seen = []
        s.valueChanged.connect(seen.append)
        s._handle_event("valueChanged", 30)
        assert s.value() == 30
        assert seen == [30]


class TestLayout:
    def test_add_widget_registers_child_in_tree(self):
        from pysideweb import state

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QPushButton("A"))
        layout.addWidget(QLabel("B"))
        w.show()

        tree = state.serialize_widget(w)
        types_in_tree = _collect_types(tree)
        assert "QPushButton" in types_in_tree
        assert "QLabel" in types_in_tree


def _collect_types(node: dict) -> set[str]:
    found = {node["type"]}
    for child in node.get("children", []):
        found |= _collect_types(child)
    return found
