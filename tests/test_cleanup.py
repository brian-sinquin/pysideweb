"""Behavior contracts for shared implementations used by public Qt classes."""

import pytest
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QWidget,
)

from pysideweb import state


@pytest.mark.parametrize('widget_type', [QCheckBox, QLabel, QLineEdit, QPushButton, QRadioButton])
def test_shared_text_property_isolated_and_notifies(widget_type):
    parent = QWidget()
    first, second = widget_type('first', parent), widget_type('second')
    assert first.parent() is parent
    assert first.text() == 'first'
    first.setText('changed')
    assert second.text() == 'second'
    assert state.serialize_widget(first)['props']['text'] == 'changed'
    assert any(change.get('id') == first._wid and change.get('prop') == 'text'
               for change in state.drain_changes())


@pytest.mark.parametrize('painting_type', [QBrush, QPainter, QPainterPath, QPen])
def test_shared_painting_fallback_preserves_lookup_rules(painting_type):
    instance = painting_type()
    assert not instance.unsupportedOperation().anotherOperation()
    with pytest.raises(AttributeError):
        _ = instance._missing_internal
