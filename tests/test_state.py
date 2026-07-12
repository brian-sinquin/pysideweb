"""Tests for the widget registry, serializer, and event dispatcher."""

import json

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pysideweb import state


def test_register_and_lookup():
    w = QWidget()
    assert state.get_widget(w._wid) is w


def test_roots_tracking():
    w = QWidget()
    w.show()
    assert w in state.get_roots()
    state.remove_root(w)
    assert w not in state.get_roots()


def test_full_tree_json_is_valid():
    w = QWidget()
    w.show()
    payload = json.loads(state.full_tree_json())
    assert payload["type"] == "full_tree"
    assert isinstance(payload["roots"], list)
    assert len(payload["roots"]) >= 1


def test_change_queue_drains():
    w = QWidget()
    state.notify_change(w._wid, "text", "x")
    changes = state.drain_changes()
    assert any(c.get("prop") == "text" for c in changes)
    # Second drain is empty.
    assert state.drain_changes() == []


def test_dispatch_event_routes_to_widget():
    b = QPushButton("Go")
    fired = []
    b.clicked.connect(lambda *_: fired.append(True))
    state.dispatch_event({"id": b._wid, "event": "clicked", "value": None})
    assert fired == [True]


def test_dispatch_event_unknown_widget_is_noop():
    # Should not raise for an unknown id.
    state.dispatch_event({"id": "does-not-exist", "event": "clicked"})


def test_doubly_nested_layouts_serialize():
    # A layout nested inside another sub-layout must serialize without error.
    # (Regression: _serialize_layout_as_container used to choke on nested layouts.)
    w = QWidget()
    outer = QVBoxLayout(w)

    row = QHBoxLayout()          # sub-layout of outer
    inner = QVBoxLayout()        # sub-layout of the sub-layout
    inner.addWidget(QLabel("deep"))
    row.addLayout(inner)
    outer.addLayout(row)
    w.show()

    tree = json.loads(state.full_tree_json())
    # Walk the tree and confirm the deeply nested label made it through.
    def texts(node):
        out = [node.get("props", {}).get("text")]
        for c in node.get("children", []):
            out += texts(c)
        return out

    assert "deep" in texts(tree["roots"][0])
