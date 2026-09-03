# Architecture

PySideWeb makes unmodified PySide6 code render in a browser. It does this by replacing the
`PySide6` package at runtime with a pure-Python implementation whose widgets are serialized
to JSON and streamed to a web front end. Nothing native (Qt, a display server, a compiled
binding) is involved.

## The big picture

```
 Your app                pysideweb (Python)                  Browser
┌──────────┐   import   ┌─────────────┐  serialize  ┌──────────────────┐
│ PySide6  │──────────► │ interceptor │────────────►│   renderer.js    │
│ code     │  patched   │  core       │   JSON tree │   → live DOM     │
│          │ ◄───────── │  widgets    │◄────────────│                  │
└──────────┘  signals   │  layouts    │  ws events  └──────────────────┘
                        │  state      │
                        │  server ────┼── aiohttp WebSocket (daemon thread)
                        └─────────────┘
```

## Modules

### `__init__.py`
Calls `interceptor.install()` at import time. This is why `import pysideweb` must be the
**first** import — before any `from PySide6 import ...`.

### `interceptor.py`
Builds fake module objects for `PySide6`, `PySide6.QtWidgets`, `PySide6.QtCore`,
`PySide6.QtGui` (plus empty stubs for optional submodules like `QtNetwork`) and injects
them into `sys.modules`. Any later `from PySide6.QtWidgets import QPushButton` therefore
resolves to `pysideweb.widgets.QPushButton` instead of native Qt.

Every one of those fake modules also carries a [PEP 562](https://peps.python.org/pep-0562/)
module-level `__getattr__`, and a `sys.meta_path` finder covers the one case that mechanism
doesn't (`import PySide6.<Something>` for a submodule not stubbed at all, e.g. `QtCharts`).
So importing a class/submodule PySideWeb doesn't implement never raises — it generates and
caches a permissive placeholder instead (`core._AutoAttr`, or a real `QWidget` subclass for
anything from `QtWidgets`). This is what lets third-party PySide6 libraries, not just apps
written directly against PySideWeb, at least run without crashing. See the README's
"Working with third-party PySide6 libraries" section.

### `core.py`
The QtCore surface, reimplemented in pure Python:
- **`QObject`** — the real root of the hierarchy: object name, parent/child ownership,
  `blockSignals`, `sender()`, `setProperty`, `findChild`. `QWidget`, `QTimer` and
  `QAction` inherit it, so `isinstance(w, QObject)` and `class Thing(QObject)` work.
- **`Signal` / `BoundSignal`** — a descriptor-based signal/slot system. `emit()` inspects
  each slot's signature and truncates arguments so zero-arg slots can connect to
  value-carrying signals; it honours `signalsBlocked()` and, under
  `PYSIDEWEB_STRICT=1`, re-raises slot exceptions instead of printing them.
- **`Qt`** — the enum/flag tables (full `Key`, `ItemDataRole`, `KeyboardModifier`, …),
  with a metaclass that returns a stable placeholder for any member not shipped, so
  `event.key() == Qt.Key_Whatever` never raises.
- **Value types** — `QSize`/`QSizeF`, `QPoint`/`QPointF`, `QRect`/`QRectF`, `QLine`/`QLineF`
  (operator- and method-complete), `QColor` (hex + CSS-name parsing with channel
  readback), `QFont`, `QUrl`, `QModelIndex`, `QSettings` (JSON-file backed).
- **`QTimer`** — one process-wide daemon scheduler with a monotonic deadline heap.
  Callbacks are serialized on that scheduler thread, matching a single event-loop
  owner more closely and avoiding linear thread growth. Long callbacks delay
  other timers, so applications should keep timer slots short.
- **`QApplication`** — `exec()` starts the web server, opens a browser, and blocks on a
  quit `Event`; `quit()` unblocks it and `aboutToQuit` fires.

### `qss.py`
Translates a Qt Style Sheet (`setStyleSheet(...)` with rule blocks) into CSS scoped to
the widget's subtree (`[data-wid="wN"] …`): pseudo-states (`:pressed` → `:active`),
sub-controls (`::item`, `::chunk`), Qt-only properties dropped. The renderer just injects
the result as a `<style>` element. A bare declaration list is applied inline instead.

### `widgets/` / `layouts.py`
Virtual widget and layout classes. `widgets/` is a package — `base` (QWidget),
`controls` (buttons, inputs, sliders), `views` (list/table/tree), `containers`
(windows, tabs, dialogs), `chrome` (menus, toolbar, status bar), `misc` — all
re-exported from `widgets/__init__.py`. Each widget has:
- `_widget_type` — the string the renderer switches on.
- `_get_props()` — returns a JSON-serializable dict of visual state.
- `_handle_event(type, value)` — applies a browser event and emits the matching signal.

The interceptor discovers widget classes by reflecting over the package (any
`Q*` class defined in `pysideweb.widgets.*`), so adding one to a submodule is
enough to expose it through the fake `PySide6.QtWidgets`.

### `painting.py`
The virtual `QPainter` pipeline. A `QWidget` subclass that overrides `paintEvent`
doesn't get a native surface — instead `QPainter` **records** every `drawLine` /
`drawRect` / `drawText` / … call as a small JSON command. During serialization
`QWidget._get_props()` runs `paintEvent`, collects the command list from the
`QPainter(self)` the user constructed, and attaches it as `props.paint =
{commands, w, h}`. `renderer.js` replays those commands onto an HTML5 `<canvas>`
of the same size. `update()` / `repaint()` re-run `paintEvent` and repaint.
Also home to the supporting value types (`QPen`, `QBrush`, `QPainterPath`,
`QPolygon`, `QLinearGradient`, `QImage`/`QPixmap`). Pixel *readback* is still
impossible — nothing is rasterized on the Python side.

### `state.py`
The central registry and protocol layer:
- Assigns every widget a stable id (`w1`, `w2`, …) and tracks root windows.
- `serialize_widget()` walks a widget + its layout/children into a JSON tree.
- A **change queue** records property updates; `notify_change()` enqueues and pokes
  listeners.
- `dispatch_event()` routes an inbound browser event to the right widget.

### `server.py`
An `aiohttp` app in a **daemon thread** with its own event loop:
- Serves the SPA (`static/index.html`) and static assets.
- `/ws` WebSocket: on connect, sends the full tree; then streams updates.
- Broadcasts are **debounced** (~50 ms → max ~20 updates/sec) so bursty property changes
  coalesce into a single frame.
- Inbound messages are decoded and handed to `state.dispatch_event()`.
- Each client owns one writer task: broadcasts serialize once and enqueue without
  waiting for sockets. Pending payload is capped at eight messages / 8 MiB, plus
  one in-flight send. Overflow substitutes a lazily built full snapshot for stale
  deltas. A full refresh also replaces queued deltas; subsequent changes follow it.
- Sends have a five-second timeout; an oversized snapshot closes with code 1009.
  Shutdown cancels writers and closes sockets, falling back to transport closure
  if the two-second close deadline expires. These are per-client queue limits,
  not aggregate memory or connection limits.

### `static/`
The browser client: `renderer.js` reconstructs the DOM from the JSON tree, applies
incremental updates, and sends user interactions back over the socket. `style.css`
provides the visual theme.

`renderer.js` also translates Qt Style Sheets: a widget's `styleSheet` prop, when it
contains rule blocks, is parsed into rules, its selectors/pseudo-states/sub-controls
mapped to CSS, scoped to `[data-wid="wN"] …`, and injected as a `<style>` element. A
bare declaration list is still applied inline. Custom `paintEvent` output arrives as
`props.paint` and is replayed onto a `<canvas>` (see `painting.py`).

## Data flow

**Python → Browser**
1. App code mutates a widget (e.g. `label.setText(...)`).
2. The setter calls `state.notify_change(id, prop, value)`.
3. The server's debounce timer fires and broadcasts a `updates` (or `full_tree`) message.
4. `renderer.js` patches the DOM.

**Browser → Python**
1. User clicks/types; `renderer.js` sends `{id, event, value}` over the socket.
2. `server.websocket_handler` calls `state.dispatch_event(...)`.
3. The target widget's `_handle_event` updates internal state and emits a `Signal`.
4. Connected Python slots run — which may trigger more Python → Browser updates.

## Threading model

- The **main thread** runs your application code and `QApplication.exec()`'s idle loop.
- The **server thread** owns the asyncio event loop and all WebSocket I/O.
- `state` is guarded by a lock; cross-thread wakeups use `loop.call_soon_threadsafe`.

## Known limitations

- Not every Qt method/property is implemented — the common app surface is prioritized. The
  universal fallback (see `interceptor.py` above) means missing API degrades to an inert
  placeholder instead of crashing, but "doesn't crash" isn't "works" — an unrendered
  third-party widget (a plot, a graphics view, ...) is still just an empty, dashed-outline
  box until PySideWeb implements a real renderer for it. A widget that draws itself in
  `paintEvent`, though, renders for real on a `<canvas>` (see `painting.py`).
- Custom painting is fire-and-forget: `paintEvent` runs on the server thread during
  serialization, drawing commands are replayed but never rasterized in Python, so
  `QImage`/`QPixmap` pixel readback and any logic that depends on it can't work.
- One shared widget tree is broadcast to all connected browsers (no per-session isolation
  yet).
- QSS translation is best-effort: property selectors (`[echoMode="2"]`) and sub-controls
  we don't map to a real element are dropped, and Qt's cascade/specificity rules aren't
  reproduced exactly.
- `QFontMetrics` is approximate — there is no font engine server-side, so text widths
  come from a per-character factor table, not real shaping.


## Runtime consolidation

`core.py` and `state.py` are the canonical implementations. The former experimental
`core_refactored.py` and `state_refactored.py` modules now re-export live APIs;
`integration.init_refactored_modules()` returns the real runtime modules without
creating a second registry. The experimental `WidgetRegistry` and `SlotBinding`
classes have been removed; they were incomplete and not public Qt APIs. The
experimental Property signature has been replaced with the Qt-style descriptor.

Signal sender identity uses a ContextVar, isolating concurrent threads and nested
emissions. Slot argument arity is computed on connection. State changes coalesce
on enqueue by widget/property, and listeners execute outside the registry lock.
Broadcast debounce decisions run on the server loop.

The full-tree envelope carries `appStyleSheetCss`, which the renderer applies via
style.textContent. Full and incremental messages use SafeJSONEncoder, preserving
JSON values while escaping HTML delimiters. Rich-text sanitization remains a
separate browser responsibility. The conservative QSS policy is enforced when
setting widget/application styles and when translating QSS directly.

The WebSocket route checks Origin, limits message size/rate, and validates event
envelopes before dispatch. This is boundary hardening, not authentication or
per-session isolation. See README for the supported network model.
