"""Tests for pysideweb's universal fallback: importing/using PySide6 API
surface pysideweb doesn't implement (third-party libraries such as
pyqtgraph, not just apps written directly against pysideweb) must degrade
to a harmless no-op instead of crashing.
"""

import json

from PySide6.QtCore import QTransform
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pysideweb import state


class TestUnknownWidgetClass:
    def test_is_a_real_widget(self):
        view = QGraphicsView()
        assert isinstance(view, QWidget)
        assert view._wid

    def test_unimplemented_method_calls_are_absorbed(self):
        view = QGraphicsView()
        # Must not raise, and must support chaining (Qt code often does
        # `widget.someCall().another()`).
        result = view.setScene(QGraphicsScene()).fitInView(0, 0, 100, 100)
        assert result is not None

    def test_participates_in_the_widget_tree(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QPushButton("real"))
        layout.addWidget(QGraphicsView())
        container.show()

        tree = state.serialize_widget(container)
        json.dumps(tree)  # must be JSON-serializable
        types_in_tree = {c["type"] for c in tree["children"]}
        assert "QPushButton" in types_in_tree
        assert "QGraphicsView" in types_in_tree

    def test_repeated_import_returns_the_same_class(self):
        from PySide6.QtWidgets import QGraphicsView as GV2

        assert GV2 is QGraphicsView

    def test_oversized_constructor_call_does_not_raise(self):
        # QWidget.__init__ only accepts (parent=None, flags=None); a real
        # Qt class we don't implement can have any constructor shape.
        view = QGraphicsView(1, 2, 3, 4, 5)
        assert view._wid

    def test_positional_parent_is_still_picked_up(self):
        parent = QWidget()
        view = QGraphicsView(parent)
        assert view.parent() is parent

    def test_subclassing_with_custom_init_and_unimplemented_calls(self):
        # Mirrors how real third-party widgets subclass a Qt base class and
        # call methods pysideweb has never heard of from __init__.
        class MyPlotWidget(QGraphicsView):
            def __init__(self):
                super().__init__()
                self.plot([1, 2, 3])
                self.setBackground("w")

        mp = MyPlotWidget()
        assert mp._wid


class TestUnknownValueClass:
    def test_construction_and_chained_calls_are_absorbed(self):
        t = QTransform()
        result = t.rotate(45).translate(1, 2).scale(2, 2)
        assert result is not None

    def test_is_falsy(self):
        # So `if some_unimplemented_value():` degrades to "do nothing"
        # rather than "pretend it worked".
        assert not QTransform()

    def test_iterates_as_empty(self):
        assert list(QTransform()) == []


class TestUnknownSubmodule:
    def test_from_import_of_wholly_unknown_submodule(self):
        from PySide6.QtCharts import QChart

        assert QChart is not None

    def test_bare_import_of_wholly_unknown_submodule(self):
        import PySide6.QtBluetooth  # noqa: F401

    def test_repeated_import_returns_the_same_module(self):
        import PySide6.QtCharts as a
        import PySide6.QtCharts as b

        assert a is b


class TestPrivateAttributesStillRaise:
    """The fallback must not swallow pysideweb's own internal duck typing
    (hasattr(widget, "_children") and friends throughout state.py/
    layouts.py) -- only public, Qt-API-looking names are absorbed."""

    def test_unknown_widget_private_attr_raises(self):
        view = QGraphicsView()
        assert not hasattr(view, "_some_private_thing_that_does_not_exist")

    def test_real_widget_private_attr_still_raises(self):
        btn = QPushButton("x")
        assert not hasattr(btn, "_some_private_thing_that_does_not_exist")
