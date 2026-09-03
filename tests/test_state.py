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


def test_listener_can_read_state_without_deadlock():
    import threading

    widget = QWidget()
    observed = []

    def listener():
        observed.append(state.get_widget(widget._wid))

    state.add_change_listener(listener)
    state.add_change_listener(listener)
    worker = threading.Thread(target=lambda: state.notify_change(widget._wid, 'text', 'x'),
                              daemon=True)
    try:
        worker.start()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert observed == [widget]
    finally:
        state.remove_change_listener(listener)


def test_pending_changes_coalesce_before_drain():
    state.drain_changes()
    for value in range(10000):
        state.notify_change('w1', 'value', value)
    assert len(state._change_queue) == 1
    assert state.drain_changes() == [
        {'type': 'update', 'id': 'w1', 'prop': 'value', 'value': 9999},
    ]


def test_delete_later_detaches_widget_from_layout_and_tree():
    root = QWidget()
    layout = QVBoxLayout(root)
    survivor = QLabel("keep")
    deleted = QLabel("remove")
    layout.addWidget(survivor)
    layout.addWidget(deleted)
    root.show()

    deleted.deleteLater()

    assert layout.count() == 1
    assert deleted._parent_layout is None
    assert state.get_widget(deleted._wid) is None
    tree = json.loads(state.full_tree_json())
    assert [child["props"]["text"] for child in tree["roots"][0]["children"]] == ["keep"]
