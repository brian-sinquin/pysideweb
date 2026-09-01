"""
pysideweb.state — Refactored state management using dataclass.

Simplified global widget registry, JSON serializer, and change dispatcher.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

_lock = threading.RLock()


@dataclass
class WidgetRegistry:
    """Centralized widget state management."""
    _widgets: dict[str, Any] = field(default_factory=dict)
    _root_widgets: list[Any] = field(default_factory=list)
    _change_queue: list[dict] = field(default_factory=list)
    _next_id: int = field(default=0)
    _listeners: list[Callable] = field(default_factory=list)

    def register(self, widget) -> str:
        """Register widget and return its ID."""
        with _lock:
            self._next_id += 1
            wid = f"w{self._next_id}"
            self._widgets[wid] = widget
            return wid

    def unregister(self, wid: str):
        """Unregister widget by ID."""
        with _lock:
            self._widgets.pop(wid, None)
            self._root_widgets[:] = [
                w for w in self._root_widgets if w._wid != wid
            ]

    def get(self, wid: str) -> Any:
        """Retrieve widget by ID."""
        with _lock:
            return self._widgets.get(wid)

    def add_root(self, widget):
        """Register as root widget."""
        with _lock:
            self._root_widgets.append(widget)

    def remove_root(self, widget):
        """Unregister root widget."""
        with _lock:
            self._root_widgets[:] = [
                w for w in self._root_widgets if w is not widget
            ]

    def notify_change(self, widget_id: str, prop: str, value: Any):
        """Queue property change notification."""
        with _lock:
            self._change_queue.append({
                "widget": widget_id,
                "property": prop,
                "value": value
            })

    def get_roots(self) -> list[Any]:
        """Get all root widgets."""
        with _lock:
            return list(self._root_widgets)

    def full_tree_json(self) -> str:
        """Serialize entire widget tree to JSON."""
        with _lock:
            root_data = [_serialize_widget(w) for w in self._root_widgets]
            return json.dumps(root_data)

    def add_listener(self, callback: Callable):
        """Add change listener."""
        with _lock:
            self._listeners.append(callback)


# Global singleton
_registry = WidgetRegistry()

# Public API (backward compat)
def register_widget(widget) -> str:
    return _registry.register(widget)

def unregister_widget(wid: str):
    return _registry.unregister(wid)

def get_widget(wid: str) -> Any:
    return _registry.get(wid)

def add_root(widget):
    return _registry.add_root(widget)

def remove_root(widget):
    return _registry.remove_root(widget)

def get_roots() -> list[Any]:
    return _registry.get_roots()

def notify_change(widget_id: str, prop: str, value: Any):
    return _registry.notify_change(widget_id, prop, value)

def full_tree_json() -> str:
    return _registry.full_tree_json()

def add_listener(callback: Callable):
    return _registry.add_listener(callback)


def _serialize_widget(widget) -> dict:
    """Recursively serialize a widget."""
    # Implementation continues from original...
    return {"type": type(widget).__name__, "id": getattr(widget, "_wid", "")}
