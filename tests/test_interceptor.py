"""The import interceptor should make PySide6 resolve to virtual classes."""


def test_pyside6_is_intercepted():
    import PySide6

    assert PySide6.__version__.endswith("pysideweb")


def test_qtwidgets_imports_resolve():
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget

    assert QPushButton().__class__.__name__ == "QPushButton"
    assert QWidget().__class__.__name__ == "QWidget"
    assert QApplication is not None


def test_qtcore_imports_resolve():
    from PySide6.QtCore import Qt, QTimer, Signal

    assert Qt.AlignCenter is not None
    assert Signal is not None
    assert QTimer is not None


def test_optional_submodules_are_stubbed():
    # These should import without raising even though nothing is implemented.
    import PySide6.QtNetwork  # noqa: F401
    import PySide6.QtSvg  # noqa: F401
