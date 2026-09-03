# Feature laboratory

The largest example in the repository: six interactive sections, all **26 widget
types currently handled by the browser renderer**, an event log, and automated
Python, WebSocket, JavaScript, and browser walkthrough coverage.

This is coverage of the implemented surface, **not every Qt API or every test
permutation**. Security attacks, scheduler races, overload/reference checks and
slow-client stress tests belong in the test suite, not in a running sample app.

## Run

From the repository root:

```bash
uv sync --extra dev
uv run python examples/showcase.py
```

Open [the local app](http://localhost:8765). An alternate port works too:

```bash
PYSIDEWEB_PORT=8766 PYSIDEWEB_NO_BROWSER=1 uv run python examples/showcase.py
```

Use Ctrl+C in the terminal to stop the server. The example is import-safe:
importing it starts no server, timers, or windows. `Showcase(app)` builds the UI;
`dispose()` stops its two timers and unregisters its windows.

## Guided tour and coverage

| Section | Try it | APIs / behavior covered |
| --- | --- | --- |
| Controls | Type Unicode; lock/unlock the name; switch language and radio choice; edit the number and decimal step | QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QCheckBox, QRadioButton, QSlider (both orientations), QDial, QSpinBox, QDoubleSpinBox, QProgressBar; events, focus retention, disabled state, icon, tooltip, masking |
| Data views | Filter 24 records; choose a category; edit a table cell; expand/collapse the tree | QListWidget, QTableWidget and QTreeWidget with their item classes; selection/editing signals; QSplitter; in-memory data updates |
| Layouts | Add/remove nested tabs; advance stacked pages; scroll the grid | QTabWidget, QStackedWidget, QScrollArea, QFrame; QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout; stretch, spacing, margins and size constraints |
| Runtime | Increment with/without signals; start/stop a timer; fire a single shot; burst 1,000 writes; add/delete cards; accept/cancel a dialog | QObject, Signal, Property, sender identity, blockSignals, QTimer; coalescing, disposal, full refresh; non-blocking QDialog |
| Painting & styles | Animate through the numeric controls/timer; clear/reapply QSS; try rich text and blocked resource CSS | QPainter, QPen, QColor, QLinearGradient, QPainterPath; rectangles, ellipses, arcs, curves, text, save/restore, translate/rotate; Canvas replay, application QSS and sanitizer samples |
| Compatibility | Trigger an action; inspect QObject ownership; optionally save/load the display name | QAction, QSettings, QPoint/QRect/QSize, QIcon; QToolBar and QGraphicsView fallback demonstrations; explicit limitations |
| Window chrome | Watch the menu header and status line while interacting | QMainWindow, QWidget, QMenuBar, QMenu, QStatusBar, QGroupBox |
| Shared state | Open a second browser tab, then reload it after changing the first | WebSocket input, broadcasts to both clients, reconnect/full snapshot; **shared application state**, not separate users |

The `event-log` retains only the latest 20 messages. Dynamic tabs are capped at
eight and cards at 20; removal also unregisters descendants. Timers are stopped
by default. No external images, fonts, datasets or accounts are needed.

Settings are the only intentional persistent sample data. Nothing is read or
written until you click Save/Load. Save writes only `display-name` via
`QSettings('pysideweb', 'feature-laboratory')`; the default file is
`$XDG_CONFIG_HOME/pysideweb/pysideweb-feature-laboratory.json` or the equivalent
under the user's `.config` directory. Tests use an isolated temporary directory.
The password field contains a fake value and is never saved; masking is visual,
not encryption or authentication.

## Automated checks

```bash
# Whole package: behavior, compatibility, security boundary and transport tests
uv run pytest -q

# Focused example checks, including two real WebSocket clients and reconnect
uv run pytest tests/test_showcase.py -q

# Renderer protocol/lifecycle, nested tabs/stacks, textarea updates, decimal steps
node --test tests_js/*.test.cjs

# Real-browser walkthrough (install the same runner as CI first)
npm install --no-save --no-package-lock @playwright/test@1.55.1
npx playwright install chromium
npx playwright test --config tests_browser/playwright.config.cjs --grep showcase
```

The browser walkthrough checks all six sections, editing/focus, enabled state,
numeric synchronization, dynamic page removal, timers, dialog acceptance,
sanitization, painting canvas, QSS removal and reconnect persistence. It is wired
into the existing CI renderer job. It has **not been run in this workspace**:
neither Chromium nor the Playwright test package is installed locally.

Additional test families remain separate:

| Tests | Why separate from an interactive example |
| --- | --- |
| `test_server.py`, `test_transport.py` | Invalid Origin/Host, message/rate limits, stalled sockets, queue bounds, oversized snapshots, cancellation and shutdown |
| `test_core.py`, `test_qtcore_compat.py`, `test_compat_corpus.py`, `tests_qt/` | Scheduler timing, value/enum references, compatibility signatures and real-Qt comparisons |
| `test_state.py`, `test_refactored.py`, `test_cleanup.py` | Registry invariants, serialization, disposal and shared-implementation contracts |
| `test_widgets*.py`, `test_painting.py`, `test_qss.py` | Additional widget permutations, paint commands, stylesheet edge cases |
| `test_interceptor.py`, `test_universal_fallback.py` | Import behavior, unsupported modules/classes and strict-mode boundaries |

## Known limits

- Menu headers render, but menu action dispatch is not implemented. The showcase
  triggers `QAction` using a normal button. QToolBar has a fallback shell, not native
  action buttons; QGraphicsView is a placeholder, not a graphics scene.
- QButtonGroup is a lookup shim: this example implements radio exclusivity
  explicitly. QObject ownership inspection uses a QObject subtree; recursive
  lookup/parent semantics for layout-only widgets are not fully Qt-compatible.
- Use QStackedWidget for the functioning page-switch example. QStackedLayout's
  current-index rendering is incomplete; it is not represented as working here.
- QDialog uses asynchronous accept/reject signals. Its `exec()` is not a nested
  event loop. QMessageBox convenience calls currently print, not show a real modal.
- Table edits are in-memory and resettable, without model-backed virtualization.
  The text editor is a plain-text textarea, not a complete Qt rich-text editor.
- The rich-text/CSS examples are probes, not proof of complete XSS protection.
  Keep this unauthenticated, shared-state example on loopback. Do not expose it
  to untrusted users or place real secrets in its widgets.
