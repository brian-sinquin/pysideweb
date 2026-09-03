"""Compatibility entry point exposing the modules used by the live runtime."""

from . import compat, core, qss_sanitizer, security, state, websocket_validator


def init_refactored_modules():
    """Return canonical modules without replacing registries or installing hooks."""
    return {
        "core": core, "state": state, "security": security, "compat": compat,
        "websocket": websocket_validator, "qss": qss_sanitizer,
    }
