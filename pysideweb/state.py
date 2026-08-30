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


def _iter_layout_child_widgets(layout):
    """Every widget reachable from `layout`, including through nested
    sub-layouts (addLayout inside addLayout) -- same shape as
    _append_layout_children, but yielding widgets instead of serializing."""
    for item in layout._items:
        widget = getattr(item, "_widget", None)
        if widget is not None:
            yield widget
        sub_layout = getattr(item, "_layout", None)
        if sub_layout is not None:
            yield from _iter_layout_child_widgets(sub_layout)


def unregister_subtree(widget) -> None:
    """Unregister `widget` and every descendant still reachable from it
    (its `_children` and everything placed in its `_layout`, recursively).

    `deleteLater()` used to only unregister the widget itself -- every
    descendant stayed in the id->widget registry (and, through their own
    `_parent`/closures, unreachable-by-nothing-but-still-referenced by
    Python's GC) for the remaining lifetime of the app. A dynamic list or
    tab set that creates and discards subtrees would leak one registry
    entry per discarded widget, forever.
    """
    for child in list(getattr(widget, "_children", ())):
        unregister_subtree(child)
    layout = getattr(widget, "_layout", None)
    if layout is not None:
        for child in _iter_layout_child_widgets(layout):
            unregister_subtree(child)
    unregister_widget(widget._wid)


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
    """Drain all pending changes, coalesced to the latest value per
    (widget, prop) pair.

    The broadcast loop only runs every _BROADCAST_INTERVAL (~50ms), so a
    single drain can accumulate many updates to the same property -- a
    slider mid-drag or text typed character by character both fire a
    notify_change() per event, but only the last value in a batch is ever
    going to matter once it reaches the browser. Sending the intermediate
    ones is pure waste on both ends of the socket. Any `full_refresh`
    markers are likewise collapsed to at most one.
    """
    with _lock:
        changes = list(_change_queue)
        _change_queue.clear()

    if not changes:
        return changes

    updates: dict[tuple[str, str], dict] = {}
    has_full_refresh = False
    for change in changes:
        if change.get("type") == "full_refresh":
            has_full_refresh = True
        else:
            updates[(change["id"], change["prop"])] = change

    result = list(updates.values())
    if has_full_refresh:
        result.append({"type": "full_refresh"})
    return result


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
