"""Integration layer - wire refactored modules into pysideweb."""

from . import (
    compat,
    core_refactored,
    qss_sanitizer,
    security,
    state_refactored,
    websocket_validator,
)


def init_refactored_modules():
    """Initialize all refactored modules."""
    # Wire security encoder to state
    state_refactored._registry._encoder = security.SafeJSONEncoder

    # Register compatibility fallbacks
    compat._unmapped_handler = compat.UnmappedAPI()

    # Initialize WebSocket validator
    websocket_validator._validator = websocket_validator.WebSocketValidator()

    # Initialize QSS sanitizer as singleton
    qss_sanitizer._sanitizer = qss_sanitizer.QSSSanitizer()

    return {
        "core": core_refactored,
        "state": state_refactored,
        "security": security,
        "compat": compat,
        "websocket": websocket_validator,
        "qss": qss_sanitizer,
    }


# Auto-initialize on import
_modules = init_refactored_modules()
