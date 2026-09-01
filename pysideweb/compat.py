"""
pysideweb.compat — Graceful fallback for unmapped Qt APIs.
"""

from pysideweb.widgets import QWidget


class UnmappedWidget(QWidget):
    """Placeholder for any unmapped Qt widget class.

    Renders as empty box with class name, preventing crashes.
    """

    def __init__(self, class_name: str = "UnmappedWidget"):
        super().__init__()
        self._class_name = class_name
        self.setStyleSheet("""
            border: 2px dashed #ccc;
            background: #f9f9f9;
        """)
        # Widget placeholder - no layout needed
        # This is a stub implementation for unmapped widgets

    def paintEvent(self, event):
        """Draw dashed outline with class name."""
        pass


class UnmappedAPI:
    """NoOp fallback for any unimplemented method."""

    def __getattr__(self, name):
        def noop(*args, **kwargs):
            return None
        return noop
