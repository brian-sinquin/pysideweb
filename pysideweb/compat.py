"""Compatibility helpers using the runtime's existing fallback machinery."""

from .core import _AutoAttr

UnmappedAPI = _AutoAttr


def UnmappedWidget(class_name: str = "UnmappedWidget", parent=None):
    """Construct the same named placeholder used for unknown Qt widget classes."""
    from .interceptor import _unknown_widget_class

    return _unknown_widget_class(class_name)(parent=parent)
