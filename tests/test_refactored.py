"""Behavioral coverage for consolidation of the experimental modules."""

import io
import json
import threading

import pytest
from PySide6.QtCore import Property, QObject, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from pysideweb import core, core_refactored, integration, state, state_refactored
from pysideweb.compat import UnmappedAPI, UnmappedWidget
from pysideweb.qss_sanitizer import QSSSanitizer
from pysideweb.security import SafeJSONEncoder
from pysideweb.websocket_validator import WebSocketValidator


def test_compatibility_modules_share_live_objects():
    assert core_refactored.Signal is core.Signal
    assert integration.init_refactored_modules()['state'] is state
    window = QWidget()
    QVBoxLayout(window).addWidget(QLabel('child'))
    window.show()
    assert state_refactored.get_widget(window._wid) is window
    tree = json.loads(state_refactored.full_tree_json())
    assert tree['type'] == 'full_tree'
    assert tree['roots'][0]['children'][0]['props']['text'] == 'child'
    state_refactored.notify_change(window._wid, 'enabled', False)
    assert any(c.get('prop') == 'enabled' for c in state.drain_changes())


@pytest.mark.parametrize('value', ['<script>&"\u2028', {'<key>': ['</script>', '&']}])
def test_json_round_trip_and_streaming(value):
    encoded = json.dumps(value, cls=SafeJSONEncoder, ensure_ascii=False)
    assert '<' not in encoded and '&' not in encoded
    assert json.loads(encoded) == value
    stream = io.StringIO()
    json.dump(value, stream, cls=SafeJSONEncoder)
    assert json.loads(stream.getvalue()) == value


def test_json_does_not_expose_arbitrary_object_attributes():
    with pytest.raises(TypeError):
        json.dumps(object(), cls=SafeJSONEncoder)


def test_qt_property_direct_and_decorator_forms():
    class Model(QObject):
        changed = Signal(int)

        def __init__(self):
            super().__init__()
            self._value = 1

        @Property(int, notify=changed)
        def value(self):
            return self._value

        @value.setter
        def value(self, value):
            self._value = value
            self.changed.emit(value)

        readonly = Property(int, lambda self: self._value)

    obj = Model()
    seen = []
    obj.changed.connect(seen.append)
    obj.value = 7
    assert obj.value == obj.readonly == 7
    assert seen == [7]
    with pytest.raises(AttributeError):
        obj.readonly = 8


def test_signal_disconnect_bound_method_and_blocking():
    class Model(QObject):
        changed = Signal(int)

    obj = Model()
    received = []
    obj.changed.connect(received.append)
    obj.blockSignals(True)
    obj.changed.emit(1)
    obj.blockSignals(False)
    obj.changed.disconnect(received.append)
    obj.changed.emit(2)
    assert received == []


def test_sender_isolated_between_threads():
    class Model(QObject):
        changed = Signal()

    first, second = Model(), Model()
    barrier = threading.Barrier(2)
    observed = []

    def slot(owner):
        barrier.wait(timeout=2)
        observed.append((owner, owner.sender()))
        barrier.wait(timeout=2)

    first.changed.connect(lambda: slot(first))
    second.changed.connect(lambda: slot(second))
    threads = [threading.Thread(target=obj.changed.emit) for obj in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
    assert len(observed) == 2
    assert all(owner is sender for owner, sender in observed)
    assert first.sender() is None


def test_fallback_helpers_use_runtime_placeholder():
    widget = UnmappedWidget('MissingControl')
    assert state.serialize_widget(widget)['type'] == 'MissingControl'
    assert not UnmappedAPI().anything().another()


@pytest.mark.parametrize('css', [
    '@import url("evil.css"); QLabel { color: red; }',
    'background: u/**/rl(https://example.com)',
    r'background: u\72l(https://example.com)',
    'width: expression (alert(1))',
    'behavior: something',
    'QLabel { color: red } /* unfinished',
])
def test_unsafe_styles_rejected_in_live_paths(css):
    assert QSSSanitizer.sanitize(css) == ''
    widget = QWidget()
    widget.setStyleSheet(css)
    assert state.serialize_widget(widget)['props']['styleSheet'] == ''
    state.set_app_stylesheet(css)
    assert json.loads(state.full_tree_json())['appStyleSheetCss'] == ''


def test_safe_styles_preserved():
    css = 'QLabel { color: red; padding: 4px; }'
    assert QSSSanitizer.sanitize(css) == css
    state.set_app_stylesheet(css)
    try:
        assert '#app .qlabel' in json.loads(state.full_tree_json())['appStyleSheetCss']
    finally:
        state.set_app_stylesheet('')


def test_hmac_requires_signature_and_rate_limit_resets(monkeypatch):
    validator = WebSocketValidator('secret')
    assert validator.validate_message('client', 'message') == (False, 'Invalid signature')
    assert not validator.validate_signature('message', 'bad')
    assert not validator.validate_signature('message', '☃')
    import hashlib
    import hmac
    signature = hmac.new(b'secret', b'message', hashlib.sha256).hexdigest()
    assert validator.validate_signature('message', signature)
    monkeypatch.setattr('pysideweb.websocket_validator.time.monotonic', lambda: 100)
    validator.rate_limit_per_minute = 1
    assert validator.check_rate_limit('new')
    assert not validator.check_rate_limit('new')
    monkeypatch.setattr('pysideweb.websocket_validator.time.monotonic', lambda: 160)
    assert validator.check_rate_limit('new')
