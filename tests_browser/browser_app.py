"""Deterministic application used by the Chromium end-to-end tests."""

import pysideweb  # noqa: F401 - must precede PySide6 imports

from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PaintProbe(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor("#ff0000"), 2))
        painter.drawRect(2, 2, 40, 20)
        painter.end()


app = QApplication([])
app.setStyleSheet("QLabel { color: #123456; }")

window = QWidget()
window.setObjectName("e2e-root")
layout = QVBoxLayout(window)

status = QLabel("waiting-for-update")
status.setObjectName("ordering-status")
ordering_button = QPushButton("Trigger ordering update")
ordering_button.setObjectName("ordering-button")
ordering_button.clicked.connect(lambda: status.setText("update-preserved"))
layout.addWidget(status)
layout.addWidget(ordering_button)

editor = QLineEdit("initial")
editor.setObjectName("editor")
echo = QLabel("initial")
echo.setObjectName("echo")
editor.textChanged.connect(echo.setText)
layout.addWidget(editor)
layout.addWidget(echo)

rich = QLabel("plain")
rich.setObjectName("rich-output")
rich_button = QPushButton("Render rich text")
rich_button.setObjectName("rich-button")
rich_button.clicked.connect(
    lambda: rich.setText(
        '<b id="kept-no">safe</b><script>bad()</script>'
        '<a href="javascript:bad()" onclick="bad()">link</a>'
    )
)
layout.addWidget(rich)
layout.addWidget(rich_button)

disposable = QLabel("remove me")
disposable.setObjectName("disposable")
dispose_button = QPushButton("Dispose")
dispose_button.setObjectName("dispose-button")
dispose_button.clicked.connect(disposable.deleteLater)
layout.addWidget(disposable)
layout.addWidget(dispose_button)

style_button = QPushButton("Clear app style")
style_button.setObjectName("style-button")
style_button.clicked.connect(lambda: app.setStyleSheet(""))
layout.addWidget(style_button)

paint = PaintProbe()
paint.setObjectName("paint-probe")
paint.resize(80, 40)
layout.addWidget(paint)

window.show()

app.exec()
