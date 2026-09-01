"""Tests for refactored modules."""

import pytest
from pysideweb import (
    core_refactored,
    state_refactored,
    security,
    compat,
    websocket_validator,
    qss_sanitizer,
)


def test_signal_slot_simplified():
    """Signal/Slot mechanism works with simplified implementation."""
    signal = core_refactored.Signal()
    results = []
    
    def slot(value):
        results.append(value)
    
    bound = core_refactored.BoundSignal(signal, object())
    bound.connect(slot)
    bound.emit(42)
    
    assert results == [42]


def test_state_registry():
    """Widget registry works with dataclass model."""
    widget = object()
    wid = state_refactored.register_widget(widget)
    
    assert state_refactored.get_widget(wid) is widget
    state_refactored.unregister_widget(wid)
    assert state_refactored.get_widget(wid) is None


def test_safe_json_encoder():
    """SafeJSONEncoder escapes HTML."""
    encoder = security.SafeJSONEncoder()
    text = "<script>alert(1)</script>"
    encoded = encoder.encode({"text": text})
    
    assert "<script>" not in encoded
    assert "alert" in encoded  # Content preserved, just escaped


def test_unmapped_widget():
    """UnmappedWidget renders gracefully."""
    widget = compat.UnmappedWidget("QGraphicsView")
    assert widget is not None
    assert widget._class_name == "QGraphicsView"


def test_websocket_validation():
    """WebSocket validator rate limits requests."""
    validator = websocket_validator.WebSocketValidator()
    client = "test_client"
    
    # First request should pass
    assert validator.check_rate_limit(client)
    
    # Many requests should trigger limit
    for _ in range(1000):
        validator.check_rate_limit(client)
    
    assert not validator.check_rate_limit(client)


def test_qss_sanitization():
    """QSS sanitizer removes dangerous directives."""
    dangerous = "@import url('evil.css'); QLabel { color: red; }"
    safe = qss_sanitizer.QSSSanitizer.sanitize(dangerous)
    
    assert "@import" not in safe
    assert "color: red" in safe
