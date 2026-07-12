"""
PySideWeb — Render PySide6 applications in your web browser.

Usage:
    import pysideweb  # This line intercepts PySide6 imports
    from PySide6.QtWidgets import QApplication, QMainWindow, ...

That's it! Your PySide6 app will now render at http://localhost:8765
"""

__version__ = "0.1.0"

from .interceptor import install as _install

# Auto-install on import
_install()
