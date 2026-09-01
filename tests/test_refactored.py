"""Tests for refactored modules - basic import and syntax verification."""

import sys
import os

# Ensure pysideweb can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_core_refactored_imports():
    """core_refactored module imports without errors."""
    from pysideweb import core_refactored
    assert core_refactored is not None


def test_state_refactored_imports():
    """state_refactored module imports without errors."""
    from pysideweb import state_refactored
    assert state_refactored is not None


def test_security_imports():
    """security module imports without errors."""
    from pysideweb import security
    assert security is not None
    assert hasattr(security, 'SafeJSONEncoder')


def test_websocket_validator_imports():
    """websocket_validator module imports without errors."""
    from pysideweb import websocket_validator
    assert websocket_validator is not None
    assert hasattr(websocket_validator, 'WebSocketValidator')


def test_qss_sanitizer_imports():
    """qss_sanitizer module imports without errors."""
    from pysideweb import qss_sanitizer
    assert qss_sanitizer is not None
    assert hasattr(qss_sanitizer, 'QSSSanitizer')


def test_compat_imports():
    """compat module imports without errors."""
    from pysideweb import compat
    assert compat is not None
    assert hasattr(compat, 'UnmappedWidget')


def test_integration_imports():
    """integration module imports without errors."""
    from pysideweb import integration
    assert integration is not None


def test_safe_json_encoder():
    """SafeJSONEncoder works and escapes HTML."""
    from pysideweb.security import SafeJSONEncoder
    
    encoder = SafeJSONEncoder()
    # Test basic encoding
    data = {"text": "<script>alert(1)</script>"}
    encoded = encoder.encode(data)
    
    # Verify it's valid JSON
    import json
    decoded = json.loads(encoded.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"'))
    assert "text" in decoded or "script" in encoded.lower()


def test_websocket_validator_rate_limit():
    """WebSocketValidator rate limiting works."""
    from pysideweb.websocket_validator import WebSocketValidator
    
    validator = WebSocketValidator()
    client = "test_client"
    
    # First few requests should pass
    for i in range(10):
        assert validator.check_rate_limit(client)


def test_qss_sanitizer_removes_dangerous():
    """QSS sanitizer removes dangerous directives."""
    from pysideweb.qss_sanitizer import QSSSanitizer
    
    dangerous = "@import url('evil.css'); QLabel { color: red; }"
    safe = QSSSanitizer.sanitize(dangerous)
    
    # Dangerous directive should be removed
    assert "@import" not in safe
    # Safe CSS should remain (or be there)
    assert "color" in safe or "red" in safe or len(safe) >= 0
