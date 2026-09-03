"""Compatibility facade over the live registry; no separate widget state."""

from .state import (
    add_change_listener,
    add_root,
    drain_changes,
    full_tree_json,
    get_roots,
    get_widget,
    notify_change,
    notify_full_refresh,
    register_widget,
    remove_root,
    serialize_widget,
    unregister_widget,
)

add_listener = add_change_listener

__all__ = [
    "add_listener", "add_root", "drain_changes", "full_tree_json", "get_roots",
    "get_widget", "notify_change", "notify_full_refresh", "register_widget",
    "remove_root", "serialize_widget", "unregister_widget",
]
