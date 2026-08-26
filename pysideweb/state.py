"""
pysideweb.state — Global widget registry, JSON serializer, diff engine, event dispatcher.

This module is the central nervous system of PySideWeb. Every virtual widget
registers itself here. The server queries this module to build the JSON tree
and compute diffs for WebSocket broadcasts.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Global widget registry
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_widgets: dict[str, Any] = {}  # id → widget
_root_widgets: list[Any] = []  # top-level windows
_change_queue: list[dict] = []
_next_id = 0
_listeners: list[Callable] = []


def _gen_id() -> str:
    global _next_id
    with _lock:
        _next_id += 1
        return f"w{_next_id}"


def register_widget(widget) -> str:
    wid = _gen_id()
    with _lock:
        _widgets[wid] = widget
    return wid


def unregister_widget(wid: str):
    with _lock:
        _widgets.pop(wid, None)
        _root_widgets[:] = [w for w in _root_widgets if w._wid != wid]


def get_widget(wid: str):
    with _lock:
        return _widgets.get(wid)


def add_root(widget):
    with _lock:
        if widget not in _root_widgets:
            _root_widgets.append(widget)


def remove_root(widget):
    with _lock:
        _root_widgets[:] = [w for w in _root_widgets if w is not widget]


def get_roots():
    with _lock:
        return list(_root_widgets)


# ---------------------------------------------------------------------------
# Change notification
# ---------------------------------------------------------------------------

def notify_change(widget_id: str, prop: str, value: Any):
    """Queue a property change for broadcast."""
    with _lock:
        _change_queue.append({
            "type": "update",
            "id": widget_id,
            "prop": prop,
            "value": value,
        })
        for listener in _listeners:
            try:
                listener()
            except Exception:
                pass


def notify_full_refresh():
    """Signal that a full tree re-render is needed."""
    with _lock:
        _change_queue.append({"type": "full_refresh"})
        for listener in _listeners:
            try:
                listener()
            except Exception:
                pass


def drain_changes() -> list[dict]:
    """Drain and return all pending changes."""
    with _lock:
        changes = list(_change_queue)
        _change_queue.clear()
        return changes


def add_change_listener(listener: Callable):
    with _lock:
        _listeners.append(listener)


# ---------------------------------------------------------------------------
# Tree serialization
# ---------------------------------------------------------------------------

def _append_layout_children(layout, out: list[dict]) -> None:
    """Serialize a layout's items (widgets, nested layouts, direct widgets/spacers) into `out`.

    Shared by `serialize_widget` and `_serialize_layout_as_container` — both used to
    walk `layout._items` by hand with the same three-way branch.
    """
    for item in layout._items:
        if getattr(item, '_widget', None) is not None:
            out.append(serialize_widget(item._widget))
        elif getattr(item, '_layout', None) is not None:
            # Nested layout (e.g. addLayout inside addLayout)
            out.append(_serialize_layout_as_container(item._layout))
        elif getattr(item, '_wid', None) is not None:
            # Direct widget or stretch spacer
            out.append(serialize_widget(item))


def serialize_widget(widget) -> dict:
    """Serialize a single widget and all its children to a JSON-compatible dict."""
    data = {
        "id": widget._wid,
        "type": widget._widget_type,
        "props": widget._get_props(),
        "children": [],
    }

    # Serialize layout children
    if getattr(widget, '_layout', None) is not None:
        layout = widget._layout
        data["layout"] = layout._get_props()
        _append_layout_children(layout, data["children"])

    # Serialize direct children (added via setParent or addWidget), skipping any
    # already pulled in through the layout above.
    if hasattr(widget, '_children'):
        seen = {c["id"] for c in data["children"]}
        for child in widget._children:
            if child._wid not in seen:
                seen.add(child._wid)
                data["children"].append(serialize_widget(child))

    return data


def _serialize_layout_as_container(layout) -> dict:
    """Serialize a sub-layout as a virtual container widget."""
    data = {
        "id": f"layout_{id(layout)}",
        "type": "QWidget",
        "props": {"visible": True, "enabled": True},
        "layout": layout._get_props(),
        "children": [],
    }
    _append_layout_children(layout, data["children"])
    return data


def serialize_full_tree() -> list[dict]:
    """Serialize all root widgets into a JSON tree."""
    roots = get_roots()
    return [serialize_widget(r) for r in roots]


def full_tree_json() -> str:
    return json.dumps({"type": "full_tree", "roots": serialize_full_tree()})


# ---------------------------------------------------------------------------
# Event dispatch (browser → Python)
# ---------------------------------------------------------------------------

def dispatch_event(event: dict):
    """Route a browser event to the appropriate widget signal."""
    wid = event.get("id")
    event_type = event.get("event")
    value = event.get("value")

    widget = get_widget(wid)
    if widget is None:
        return

    widget._handle_event(event_type, value)
