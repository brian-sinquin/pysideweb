"""The smallest possible PySideWeb app.

Run it, and a button renders in your browser at http://localhost:8765.
Clicking it fires the Python callback below.

    uv run python examples/hello.py
"""

import pysideweb  # noqa: F401  ← intercepts PySide6 imports; must come first

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget


def main() -> None:
    app = QApplication([])

    window = QWidget()
    window.setWindowTitle("Hello, PySideWeb")

    layout = QVBoxLayout(window)
    label = QLabel("You have clicked 0 times.")
    button = QPushButton("Click me")
    layout.addWidget(label)
    layout.addWidget(button)

    clicks = {"n": 0}

    def on_click() -> None:
        clicks["n"] += 1
        label.setText(f"You have clicked {clicks['n']} times.")

    button.clicked.connect(on_click)

    window.show()
    app.exec()


if __name__ == "__main__":
    main()
