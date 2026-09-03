"""Exercise the example's real callbacks and its wire representation headlessly."""

import asyncio
import json
import runpy
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from PySide6.QtWidgets import QApplication, QTextEdit

from pysideweb import server, state

SHOWCASE = Path(__file__).resolve().parents[1] / 'examples' / 'showcase.py'


def walk(node):
    yield node
    for child in node['children']:
        yield from walk(child)


@pytest.fixture
def showcase(monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    previous_style = state.get_app_stylesheet()
    app = QApplication.instance() or QApplication([])
    window = runpy.run_path(str(SHOWCASE))['Showcase'](app)
    window.show()
    try:
        yield window
    finally:
        window.dispose()
        app.setStyleSheet(previous_style)


def test_import_has_no_widgets_timers_or_server_side_effects():
    roots = state.get_roots()
    registered = set(state._widgets)
    runpy.run_path(str(SHOWCASE))
    assert state.get_roots() == roots
    assert set(state._widgets) == registered


def test_showcase_covers_renderer_widget_families(showcase):
    showcase.dialog.show()
    nodes = [node for root in state.serialize_full_tree() for node in walk(root)]
    types = {node['type'] for node in nodes}
    assert {
        'QMainWindow', 'QWidget', 'QFrame', 'QGroupBox', 'QScrollArea', 'QSplitter',
        'QTabWidget', 'QStackedWidget', 'QDialog', 'QMenuBar', 'QStatusBar',
        'QPushButton', 'QLabel', 'QLineEdit', 'QTextEdit', 'QComboBox',
        'QCheckBox', 'QRadioButton', 'QSlider', 'QDial', 'QProgressBar',
        'QSpinBox', 'QDoubleSpinBox', 'QListWidget', 'QTableWidget', 'QTreeWidget',
    } <= types
    names = [node['props'].get('objectName') for node in nodes if node['props'].get('objectName')]
    assert len(names) == len(set(names))
    assert showcase.tabs.count() == 6
    assert not showcase.timer.isActive() and not showcase.once.isActive()
    assert len(json.loads(state.full_tree_json())['roots']) == 2


def test_controls_and_data_callbacks(showcase):
    showcase.name._handle_event('textChanged', 'café 日本語 😀')
    assert showcase.echo.text() == 'café 日本語 😀'
    showcase.slider._handle_event('valueChanged', 72)
    assert all(widget.value() == 72 for widget in showcase.numeric)
    assert showcase.progress.value() == showcase.paint.level == 72
    showcase.radios[1]._handle_event('toggled', True)
    assert not showcase.radios[0].isChecked() and showcase.radios[1].isChecked()
    showcase.categories._handle_event('currentRowChanged', 2)
    assert showcase.table.rowCount() == 8
    assert showcase.filter.text() == 'Widgets'
    showcase.table._handle_event('cellChanged', {'row': 0, 'col': 0, 'text': 'Edited'})
    assert showcase.filtered[0][0] == 'Edited'
    showcase.fill_table('Edited')
    assert showcase.table.rowCount() == 1
    showcase.filter.setText('')
    showcase.reset_data()
    assert showcase.table.rowCount() == 24


def test_property_signals_log_and_burst(showcase):
    showcase.increment_counter()
    assert showcase.counter.value == 1
    assert 'sender matches: True' in showcase.events[-1]
    showcase.block_counter()
    assert showcase.counter.value == 2
    assert not showcase.counter.signalsBlocked()
    state.drain_changes()
    showcase.burst()
    updates = state.drain_changes()
    burst = [item for item in updates if item.get('id') == showcase.burst_label._wid]
    assert len(burst) == 1 and burst[0]['value'] == 'Burst value: 1000 / 1000'
    assert any(item.get('id') == showcase.log_view._wid and item['prop'] == 'text' for item in updates)
    for index in range(30):
        showcase.log(f'entry {index}')
    assert len(showcase.events) == 20
    assert showcase.log_view.toPlainText().endswith('entry 29')


def test_dynamic_lifecycle_and_dialog(showcase):
    registered = set(state._widgets)
    for _ in range(12):
        showcase.add_tab()
    assert showcase.dynamic_tabs.count() == 8
    for _ in range(12):
        showcase.remove_tab()
    assert showcase.dynamic_tabs.count() == 1
    assert set(state._widgets) == registered
    for _ in range(25):
        showcase.add_card()
    assert len(showcase.cards) == 20
    for _ in range(25):
        showcase.delete_card()
    assert not showcase.cards and set(state._widgets) == registered
    assert 'Dynamic card' not in state.full_tree_json()
    showcase.next_page()
    assert showcase.stack.currentIndex() == 1
    showcase.dialog.show()
    showcase.dialog.accept()
    assert not showcase.dialog.isVisible() and showcase.events[-1] == 'Dialog accepted'
    showcase.dialog.show()
    showcase.dialog.reject()
    assert showcase.events[-1] == 'Dialog rejected'


def test_painting_style_settings_and_object_inspection(showcase, tmp_path):
    assert not list(tmp_path.rglob('*.json'))
    showcase.set_level(81)
    paint = state.serialize_widget(showcase.paint)['props']['paint']
    assert {'drawRect', 'drawEllipse', 'drawArc', 'drawPath', 'rotate', 'save', 'restore'} <= {
        command['op'] for command in paint['commands']
    }
    showcase.blocked_style()
    assert showcase.style_probe.styleSheet() == ''
    showcase.name.setText('Saved Unicode 日本語')
    showcase.save_setting()
    showcase.name.setText('different')
    showcase.load_setting()
    assert showcase.name.text() == showcase.echo.text() == 'Saved Unicode 日本語'
    assert len(list(tmp_path.rglob('*.json'))) == 1
    showcase.inspect_object()
    assert showcase.events[-1] == 'QObject findChild: True; parent matches: True'


def test_timer_controls_and_disposal(showcase):
    showcase.start_timer()
    assert showcase.timer.isActive()
    showcase.stop_timer()
    assert not showcase.timer.isActive()
    showcase.tick()  # deterministic callback coverage; scheduler timing has its own tests
    assert showcase.ticks == 1 and showcase.progress.value() == 38
    showcase.once.start(60_000)
    owned = {node['id'] for node in walk(state.serialize_widget(showcase))}
    showcase.dispose()
    assert not showcase.once.isActive() and not showcase.timer.isActive()
    assert all(state.get_widget(wid) is None for wid in owned)


def test_text_edit_plain_text_updates_match_full_tree():
    editor = QTextEdit('old')
    calls = []
    editor.textChanged.connect(lambda: calls.append(editor.toPlainText()))
    try:
        editor.setPlainText('new')
        changes = state.drain_changes()
        assert {'type': 'update', 'id': editor._wid, 'prop': 'text', 'value': 'new'} in changes
        assert state.serialize_widget(editor)['props']['text'] == 'new'
        editor.append('line')
        assert calls[-1] == 'new\nline'
        editor.clear()
        assert calls[-1] == ''
        state.drain_changes()
        editor._handle_event('textChanged', 'browser edit')
        assert calls[-1] == 'browser edit'
        assert not state.drain_changes()  # browser edits must not echo back
    finally:
        editor.deleteLater()


def test_showcase_real_websocket_shared_state_and_reconnect(showcase, monkeypatch):
    async def scenario():
        async with TestClient(TestServer(server._create_app())) as client:
            monkeypatch.setattr(server, '_server_loop', asyncio.get_running_loop())
            first = await client.ws_connect('/ws')
            second = await client.ws_connect('/ws')
            for ws in (first, second):
                assert (await ws.receive_json(timeout=2))['type'] == 'full_tree'
            state.drain_changes()
            # User input crosses the real wire; both clients receive its echo.
            await first.send_json({'id': showcase.name._wid, 'event': 'textChanged', 'value': 'Wire 日本語'})
            for ws in (first, second):
                message = await ws.receive_json(timeout=2)
                assert any(change.get('id') == showcase.echo._wid and change.get('value') == 'Wire 日本語'
                           for change in message['updates'])
            await first.close()
            replacement = await client.ws_connect('/ws')
            tree = await replacement.receive_json(timeout=2)
            nodes = [node for root in tree['roots'] for node in walk(root)]
            assert next(node for node in nodes if node['id'] == showcase.name._wid)['props']['text'] == 'Wire 日本語'
            await replacement.close()
            await second.close()
        assert not server._clients

    asyncio.run(scenario())
