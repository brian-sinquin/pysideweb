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
- **`Signal` / `BoundSignal`** — a descriptor-based signal/slot system. `emit()` inspects
  each slot's signature and truncates arguments so zero-arg slots can connect to
  value-carrying signals (matching Qt's forgiving behavior).
- **`Qt`** — enums and flags (alignment, orientation, item flags, …).
- **Value types** — `QSize`, `QPoint`, `QRect`, `QColor`, `QFont` (with `to_css()`), etc.
- **`QTimer`** — backed by `threading.Timer`.
- **`QApplication`** — `exec()` starts the web server, opens a browser, and blocks.

### `widgets.py` / `layouts.py`
Virtual widget and layout classes. Each widget has:
- `_widget_type` — the string the renderer switches on.
- `_get_props()` — returns a JSON-serializable dict of visual state.
- `_handle_event(type, value)` — applies a browser event and emits the matching signal.

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

### `static/`
The browser client: `renderer.js` reconstructs the DOM from the JSON tree, applies
incremental updates, and sends user interactions back over the socket. `style.css`
provides the visual theme.

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
  box until PySideWeb implements a real renderer for it.
- One shared widget tree is broadcast to all connected browsers (no per-session isolation
  yet).
- QSS/stylesheets are not translated to CSS.
