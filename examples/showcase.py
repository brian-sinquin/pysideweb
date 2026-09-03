"""Interactive feature laboratory. Run: uv run python examples/showcase.py

See showcase.md for the coverage map and known compatibility boundaries.
Importing this module constructs nothing and starts no server or timer.
"""

import pysideweb  # noqa: F401 - install the interceptor BEFORE importing PySide6

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Property, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDial, QDialog,
    QDoubleSpinBox, QFrame, QGraphicsView, QGridLayout, QGroupBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QProgressBar,
    QPushButton, QRadioButton, QScrollArea, QSlider, QSpinBox, QSplitter,
    QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from pysideweb import state


STYLE = """
QWidget { color: #26334d; font-size: 14px; }
QLabel#showcase-title { color: #234dcc; font-size: 26px; font-weight: 700; }
QGroupBox { background: #f5f7fc; border: 1px solid #dce3f1; border-radius: 8px; }
QPushButton { padding: 8px 12px; border-radius: 6px; }
QLineEdit, QTextEdit { background: #ffffff; color: #26334d; }
"""


def named(widget, name):
    widget.setObjectName(name)
    return widget


def button(text, name, callback):
    widget = named(QPushButton(text), name)
    widget.clicked.connect(callback)
    return widget


def row(*widgets):
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    return container


class Counter(QObject):
    changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0

    def get_value(self):
        return self._value

    def set_value(self, value):
        if self._value != value:
            self._value = value
            self.changed.emit(value)

    value = Property(int, get_value, set_value, notify=changed)


class PaintGallery(QWidget):
    """Canvas replay: gradient, path, transforms, text and geometric primitives."""

    def __init__(self):
        super().__init__()
        self.level = 37
        self.setFixedSize(640, 220)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(0, 0, 640, 220)
        gradient.setColorAt(0, QColor('#e9f0ff'))
        gradient.setColorAt(1, QColor('#d8f6e7'))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor('#5374c5'), 2))
        painter.drawRoundedRect(4, 4, 632, 212, 12, 12)
        painter.setBrush(QColor('#5575e7'))
        painter.drawRect(25, 45, max(1, self.level * 2), 35)
        painter.drawEllipse(270, 40, 80, 80)
        painter.drawArc(375, 40, 90, 90, 0, int(self.level * 3.6 * 16))
        path = QPainterPath()
        path.moveTo(25, 155)
        path.cubicTo(90, 90, 160, 210, 230, 145)
        painter.drawPath(path)
        painter.save()
        painter.translate(535, 95)
        painter.rotate(self.level)
        painter.drawRect(-22, -22, 44, 44)
        painter.restore()
        painter.setPen(QColor('#26334d'))
        painter.drawText(270, 175, f'Level {self.level} / 100 — café 日本語')
        painter.end()


class Showcase(QMainWindow):
    """Bounded demo state; periodic work starts only when the user presses Start."""

    SECTIONS = ('Controls', 'Data views', 'Layouts', 'Runtime', 'Painting & styles', 'Compatibility')

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle('PySideWeb · Feature laboratory')
        self.resize(1160, 900)
        self.setObjectName('showcase-window')
        self.events = []
        self.ticks = 0
        self.cards = []
        self.card_serial = 0
        self.counter = Counter(self)
        self.object_probe = QObject(self.counter)
        self.object_probe.setObjectName('counter-probe')
        self.counter.changed.connect(self.counter_changed)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)
        self.once = QTimer(self)
        self.once.setSingleShot(True)
        self.once.timeout.connect(lambda: self.log('Single-shot timer fired'))

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.addWidget(named(QLabel('PySideWeb feature laboratory'), 'showcase-title'))
        outer.addWidget(QLabel('Explore the live API. Open a second browser tab to see shared state.'))
        self.tabs = named(QTabWidget(), 'showcase-tabs')
        outer.addWidget(self.tabs)
        self.log_view = named(QTextEdit('Ready. Choose a section and try its controls.'), 'event-log')
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(125)
        outer.addWidget(self.log_view)
        self.statusBar().showMessage('Ready — local/shared-session demo')
        self.menuBar().addMenu('Feature laboratory (menu header only)')

        for title, build in zip(self.SECTIONS, (
            self.build_controls, self.build_data, self.build_layouts,
            self.build_runtime, self.build_painting, self.build_compatibility,
        ), strict=True):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setSpacing(14)
            build(layout)
            self.tabs.addTab(page, title)
        self.tabs.currentChanged.connect(lambda index: self.log(f'Section: {self.SECTIONS[index]}'))
        self.app.setStyleSheet(STYLE)

    def log(self, message):
        self.events.append(str(message))
        self.events[:] = self.events[-20:]
        self.log_view.setPlainText('\n'.join(self.events))
        self.statusBar().showMessage(str(message))

    def build_controls(self, layout):
        group = QGroupBox('Text, input and selection')
        form = QFormLayout(group)
        self.name = named(QLineEdit('Ada Lovelace'), 'demo-name')
        self.name.setPlaceholderText('Type a name — Unicode is welcome')
        self.name.setToolTip('Updates the preview without losing keyboard focus')
        self.echo = named(QLabel(self.name.text()), 'demo-echo')
        self.name.textChanged.connect(self.echo.setText)
        self.name.editingFinished.connect(lambda: self.log('Name editing finished'))
        self.password = named(QLineEdit('not-a-real-secret'), 'demo-password')
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        notes = named(QTextEdit('Multiline text\nSecond line'), 'demo-notes')
        notes.setFixedHeight(85)
        self.language = named(QComboBox(), 'demo-language')
        self.language.addItems(['English', 'Français', '日本語'])
        self.language.currentTextChanged.connect(lambda text: self.log(f'Language: {text}'))
        for label, field in (('Name', self.name), ('Live preview', self.echo),
                             ('Password (masking only)', self.password), ('Notes', notes),
                             ('Language', self.language)):
            form.addRow(label, field)
        layout.addWidget(group)
        lock = named(QCheckBox('Disable the name field'), 'demo-lock')
        lock.toggled.connect(self.name.setDisabled)
        checkable = named(QPushButton('Checkable button'), 'demo-checkable')
        checkable.setCheckable(True)
        checkable.setIcon(QIcon('✓'))
        checkable.clicked.connect(lambda checked: self.log(f'Button checked: {checked}'))
        self.radios = [named(QRadioButton(text), f'demo-radio-{index}')
                       for index, text in enumerate(('Compact', 'Comfortable'))]
        self.radio_group = QButtonGroup(self)
        for index, radio in enumerate(self.radios):
            self.radio_group.addButton(radio, index)
            # QButtonGroup is a lookup shim; exclusivity is explicit in this demo.
            radio.toggled.connect(lambda checked, i=index: self.choose_density(i, checked))
        self.radios[0].setChecked(True)
        layout.addWidget(row(lock, checkable, *self.radios))

        values = QGroupBox('Linked numeric controls · 0–100')
        grid = QGridLayout(values)
        self.slider = named(QSlider(Qt.Horizontal), 'demo-slider')
        self.vertical = named(QSlider(Qt.Vertical), 'demo-vertical')
        self.vertical.setFixedHeight(100)
        self.spin = named(QSpinBox(), 'demo-spin')
        self.dial = named(QDial(), 'demo-dial')
        self.progress = named(QProgressBar(), 'demo-progress')
        self.numeric = (self.slider, self.vertical, self.spin, self.dial)
        for index, widget in enumerate(self.numeric):
            widget.setRange(0, 100)
            widget.setValue(37)
            widget.valueChanged.connect(self.set_level)
            grid.addWidget(widget, 0, index)
        self.progress.setRange(0, 100)
        self.progress.setValue(37)
        grid.addWidget(self.progress, 1, 0, 1, 4)
        decimal = named(QDoubleSpinBox(), 'demo-decimal')
        decimal.setRange(0, 10)
        decimal.setSingleStep(0.25)
        decimal.setDecimals(2)
        decimal.setValue(1.25)
        decimal.valueChanged.connect(lambda value: self.log(f'Decimal value: {value:.2f}'))
        grid.addWidget(QLabel('Decimal step: 0.25'), 2, 0)
        grid.addWidget(decimal, 2, 1)
        layout.addWidget(values)

    def choose_density(self, selected, checked):
        if checked:
            for index, radio in enumerate(self.radios):
                if index != selected:
                    radio.setChecked(False)

    def set_level(self, value):
        value = max(0, min(100, int(value)))
        for widget in self.numeric:
            blocked = widget.blockSignals(True)
            try:
                widget.setValue(value)
            finally:
                widget.blockSignals(blocked)
        self.progress.setValue(value)
        self.paint.level = value
        self.paint.update()

    def build_data(self, layout):
        layout.addWidget(QLabel('Filter, select and edit cells. Edits are in-memory; Reset restores the sample.'))
        self.filter = named(QLineEdit(), 'demo-filter')
        self.filter.setPlaceholderText('Filter sample records')
        self.filter.textChanged.connect(self.fill_table)
        layout.addWidget(row(self.filter, button('Reset data', 'reset-data', self.reset_data)))
        split = QSplitter(Qt.Horizontal)
        self.categories = named(QListWidget(), 'demo-categories')
        self.categories.addItems(['All', 'Core', 'Widgets', 'Tests'])
        self.categories.currentRowChanged.connect(self.select_category)
        split.addWidget(self.categories)
        self.table = named(QTableWidget(0, 3), 'demo-table')
        self.table.setHorizontalHeaderLabels(['Record', 'Area', 'Score'])
        self.table.cellClicked.connect(lambda r, c: self.log(f'Cell selected: {r}, {c}'))
        self.table.cellChanged.connect(self.edit_cell)
        split.addWidget(self.table)
        self.tree = named(QTreeWidget(), 'demo-tree')
        self.tree.setHeaderLabels(['Area / feature', 'Status'])
        for area in ('Core', 'Widgets', 'Tests'):
            parent = QTreeWidgetItem(self.tree, [area, 'implemented subset'])
            for feature in ('State', 'Events', 'Regression coverage'):
                QTreeWidgetItem(parent, [feature, 'explore'])
        self.tree.expandAll()
        self.tree.itemClicked.connect(lambda item, column: self.log(f'Tree: {item.text(0)}'))
        split.addWidget(self.tree)
        split.setSizes([140, 520, 260])
        layout.addWidget(split)
        layout.addWidget(row(button('Expand tree', 'expand-tree', self.tree.expandAll),
                             button('Collapse tree', 'collapse-tree', self.tree.collapseAll)))
        self.data_status = named(QLabel(), 'data-status')
        layout.addWidget(self.data_status)
        self.reset_data()

    def reset_data(self):
        self.records = [[f'Record {index + 1:02}', ('Core', 'Widgets', 'Tests')[index % 3], str(index * 4)]
                        for index in range(24)]
        self.fill_table(self.filter.text())

    def select_category(self, index):
        if 0 <= index < 4:
            query = ['', 'Core', 'Widgets', 'Tests'][index]
            self.filter.setText(query)
            self.fill_table(query)

    def fill_table(self, query):
        self.filtered = [record for record in self.records if query.casefold() in ' '.join(record).casefold()]
        self.table.setRowCount(len(self.filtered))
        for r, record in enumerate(self.filtered):
            for c, value in enumerate(record):
                self.table.setItem(r, c, QTableWidgetItem(value))
        self.data_status.setText(f'{len(self.filtered)} / {len(self.records)} records')

    def edit_cell(self, r, c):
        if 0 <= r < len(self.filtered) and 0 <= c < 3:
            self.filtered[r][c] = self.table.item(r, c).text()
            self.log(f'Edited row {r + 1}, column {c + 1}')

    def build_layouts(self, layout):
        layout.addWidget(QLabel('Box, form, grid, splitter, scrolling, tabs and stacked pages are all used here.'))
        self.dynamic_tabs = named(QTabWidget(), 'dynamic-tabs')
        self.add_tab()
        layout.addWidget(row(button('Add tab (max 8)', 'add-tab', self.add_tab),
                             button('Remove last tab', 'remove-tab', self.remove_tab)))
        layout.addWidget(self.dynamic_tabs)
        self.stack = named(QStackedWidget(), 'demo-stack')
        for index in range(3):
            self.stack.addWidget(QLabel(f'Stacked page {index + 1}'))
        layout.addWidget(row(button('Next stacked page', 'next-page', self.next_page), self.stack))
        scroll = named(QScrollArea(), 'demo-scroll')
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(190)
        frame = QFrame()
        grid = QGridLayout(frame)
        for index in range(30):
            grid.addWidget(QLabel(f'Grid item {index + 1:02}'), index // 3, index % 3)
        scroll.setWidget(frame)
        layout.addWidget(scroll)
        layout.addStretch()

    def add_tab(self):
        if self.dynamic_tabs.count() < 8:
            number = self.dynamic_tabs.count() + 1
            page = QWidget()
            box = QVBoxLayout(page)
            box.addWidget(QLabel(f'Dynamic page {number}'))
            box.addStretch()
            self.dynamic_tabs.addTab(page, f'Page {number}')

    def remove_tab(self):
        if self.dynamic_tabs.count() > 1:
            index = self.dynamic_tabs.count() - 1
            page = self.dynamic_tabs.widget(index)
            self.dynamic_tabs.removeTab(index)
            page.deleteLater()  # unregister descendants and request a full refresh

    def next_page(self):
        self.stack.setCurrentIndex((self.stack.currentIndex() + 1) % self.stack.count())

    def build_runtime(self, layout):
        self.counter_label = named(QLabel('Counter: 0'), 'demo-counter')
        layout.addWidget(row(self.counter_label,
                             button('Increment Property', 'increment-counter', self.increment_counter),
                             button('Increment with signals blocked', 'block-counter', self.block_counter)))
        self.timer_label = named(QLabel('Timer stopped · ticks: 0'), 'timer-status')
        layout.addWidget(row(self.timer_label,
                             button('Start', 'start-timer', self.start_timer),
                             button('Stop', 'stop-timer', self.stop_timer),
                             button('Single shot', 'single-shot', lambda: self.once.start(100))))
        self.burst_label = named(QLabel('No burst yet'), 'burst-status')
        layout.addWidget(row(self.burst_label, button('Write 1,000 updates', 'burst', self.burst)))
        layout.addWidget(row(button('Add card (max 20)', 'add-card', self.add_card),
                             button('Delete last card', 'delete-card', self.delete_card),
                             button('Request full refresh', 'full-refresh', state.notify_full_refresh)))
        cards = named(QWidget(), 'dynamic-cards')
        self.cards_layout = QVBoxLayout(cards)
        layout.addWidget(cards)
        self.dialog = named(QDialog(), 'demo-dialog')
        self.dialog.setWindowTitle('Non-blocking dialog')
        box = QVBoxLayout(self.dialog)
        box.addWidget(QLabel('Accept/reject emit signals; this shim does not run a nested event loop.'))
        box.addWidget(row(button('Accept', 'accept-dialog', self.dialog.accept),
                          button('Cancel', 'reject-dialog', self.dialog.reject)))
        self.dialog.accepted.connect(lambda: self.log('Dialog accepted'))
        self.dialog.rejected.connect(lambda: self.log('Dialog rejected'))
        layout.addWidget(button('Open dialog', 'open-dialog', self.dialog.show))

    def increment_counter(self):
        self.counter.value += 1

    def counter_changed(self, value):
        self.counter_label.setText(f'Counter: {value}')
        self.log(f'Property notification: {value}; sender matches: {self.sender() is self.counter}')

    def block_counter(self):
        blocked = self.counter.blockSignals(True)
        try:
            self.counter.value += 1
        finally:
            self.counter.blockSignals(blocked)
        self.counter_label.setText(f'Counter: {self.counter.value} (signal blocked)')
        self.log('Value changed without a Property notification')

    def start_timer(self):
        self.timer.start()
        self.timer_label.setText(f'Timer running · ticks: {self.ticks}')

    def stop_timer(self):
        self.timer.stop()
        self.timer_label.setText(f'Timer stopped · ticks: {self.ticks}')

    def tick(self):
        self.ticks += 1
        self.timer_label.setText(f'Timer running · ticks: {self.ticks}')
        self.set_level((self.progress.value() + 1) % 101)

    def burst(self):
        for index in range(1000):
            self.burst_label.setText(f'Burst value: {index + 1} / 1000')
        self.log('1,000 writes; the server coalesces pending writes to the same property')

    def add_card(self):
        if len(self.cards) < 20:
            self.card_serial += 1
            card = named(QLabel(f'Dynamic card {self.card_serial}'), f'card-{self.card_serial}')
            self.cards.append(card)
            self.cards_layout.addWidget(card)
            card.show()

    def delete_card(self):
        if self.cards:
            self.cards.pop().deleteLater()

    def build_painting(self, layout):
        self.paint = named(PaintGallery(), 'paint-gallery')
        layout.addWidget(self.paint)
        layout.addWidget(QLabel('Change numeric controls or start the timer to animate the canvas.'))
        layout.addWidget(row(button('Apply application QSS', 'apply-style', lambda: self.app.setStyleSheet(STYLE)),
                             button('Clear application QSS', 'clear-style', lambda: self.app.setStyleSheet(''))))
        self.rich = named(QLabel('Plain text'), 'demo-rich')
        layout.addWidget(self.rich)
        layout.addWidget(row(button('Rich text sample', 'rich-sample', self.rich_sample),
                             button('Plain Unicode', 'plain-sample',
                                    lambda: self.rich.setText('café · 日本語 · 😀 · < & >'))))
        self.style_probe = named(QLabel('Stylesheet policy probe'), 'style-probe')
        layout.addWidget(self.style_probe)
        layout.addWidget(button('Try blocked resource CSS', 'blocked-style', self.blocked_style))
        layout.addWidget(QLabel('This is a small sanitizer demonstration, not a complete security audit.'))

    def rich_sample(self):
        self.rich.setText('<b>Safe bold</b> and <i>italic</i><script>blocked()</script>'
                          '<a href="javascript:blocked()" onclick="blocked()">unsafe link</a>')

    def blocked_style(self):
        self.style_probe.setStyleSheet('color: red; background-image: url(https://example.invalid/image);')
        self.log(f'Resource stylesheet rejected: {self.style_probe.styleSheet() == ""}')

    def build_compatibility(self, layout):
        layout.addWidget(QLabel('Supported APIs and deliberate boundaries — not every Qt API is implemented.'))
        self.action = QAction('Demo action', self)
        self.action.triggered.connect(lambda: self.log('QAction.triggered received'))
        layout.addWidget(button('Trigger QAction from a button', 'trigger-action', self.action.trigger))
        toolbar = QToolBar('Toolbar compatibility shell')
        toolbar.addWidget(QLabel('QToolBar fallback: child widgets render; native action buttons do not.'))
        layout.addWidget(toolbar)
        fallback = named(QGraphicsView(), 'unsupported-view')
        fallback.setFixedHeight(60)
        layout.addWidget(fallback)
        layout.addWidget(QLabel('QGraphicsView above is a placeholder, not a graphics scene renderer.'))
        geometry = QRect(0, 0, 100, 80)
        layout.addWidget(QLabel(
            f'Values: QRect contains (10, 20): {geometry.contains(QPoint(10, 20))}; '
            f'QSize width: {QSize(640, 480).width()}; QColor: {QColor("royalblue").name()}'
        ))
        layout.addWidget(button('Inspect QObject ownership', 'inspect-object', self.inspect_object))
        layout.addWidget(QLabel('Settings are opt-in: Save writes only the sample display name to '
                                'the PySideWeb feature-laboratory settings file. Never save secrets.'))
        layout.addWidget(row(button('Save sample setting', 'save-setting', self.save_setting),
                             button('Load sample setting', 'load-setting', self.load_setting)))
        layout.addWidget(QLabel('QMessageBox convenience functions currently print to the terminal; '
                                'menus have no action dispatch; QButtonGroup exclusivity is manual here.'))

    def inspect_object(self):
        found = self.counter.findChild(QObject, 'counter-probe')
        self.log(f'QObject findChild: {found is self.object_probe}; '
                 f'parent matches: {self.object_probe.parent() is self.counter}')

    def save_setting(self):
        settings = QSettings('pysideweb', 'feature-laboratory')
        settings.setValue('display-name', self.name.text())
        verified = QSettings('pysideweb', 'feature-laboratory').value('display-name') == self.name.text()
        self.log(f'Settings round trip: {verified}')

    def load_setting(self):
        settings = QSettings('pysideweb', 'feature-laboratory')
        self.name.setText(settings.value('display-name', 'Ada Lovelace', type=str))
        self.echo.setText(self.name.text())
        self.log('Loaded sample setting (or default)')

    def dispose(self):
        self.timer.stop()
        self.once.stop()
        self.dialog.deleteLater()
        self.deleteLater()


def main():
    app = QApplication([])
    window = Showcase(app)
    app.aboutToQuit.connect(window.dispose)
    window.show()
    app.exec()


if __name__ == '__main__':
    main()
