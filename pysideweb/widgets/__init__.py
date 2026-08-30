"""pysideweb.widgets - virtual QtWidgets classes.

Split across submodules for navigability; everything is re-exported here so
`from pysideweb.widgets import QPushButton` and the interceptor's reflective
discovery both keep working.
"""

from .base import QWidget
from .chrome import QAction, QMenu, QMenuBar, QStatusBar, QToolBar
from .containers import (
    QDialog,
    QFrame,
    QGroupBox,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabWidget,
)
from .controls import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDial,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTextEdit,
)
from .misc import QSizePolicy, QSpacerItem, QWidgetItem
from .views import (
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
)

__all__ = [
    "QAction", "QButtonGroup", "QCheckBox", "QComboBox", "QDial", "QDialog",
    "QDoubleSpinBox", "QFrame", "QGroupBox", "QLabel", "QLineEdit",
    "QListWidget", "QListWidgetItem", "QMainWindow", "QMenu", "QMenuBar",
    "QMessageBox", "QProgressBar", "QPushButton", "QRadioButton", "QScrollArea",
    "QSizePolicy", "QSlider", "QSpacerItem", "QSpinBox", "QSplitter",
    "QStackedWidget", "QStatusBar", "QTabWidget", "QTableWidget",
    "QTableWidgetItem", "QTextEdit", "QToolBar", "QTreeWidget",
    "QTreeWidgetItem", "QWidget", "QWidgetItem",
]
