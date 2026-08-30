# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Compatibility
- **Real `QObject`** at the root of the hierarchy — `objectName`, parent/child ownership,
  `blockSignals`/`signalsBlocked` (honoured by `Signal.emit`), `sender()`,
  `setProperty`/`property`, `findChild`/`findChildren`, `installEventFilter`, `inherits()`,
  `tr()`. `QWidget`, `QTimer` and `QAction` inherit it and the interceptor exports the same
  class as `QtCore.QObject`, so `isinstance(w, QObject)` and `class Thing(QObject)` work.
  `QEvent`/`QUrl`/`QModelIndex` are real classes now too.
- **`QColor`** parses `#rgb` / `#rrggbb` / `#rrggbbaa` and 148 CSS/SVG colour names into
  real channels (`QColor("#ff8800").red() == 255`), with `getRgb`/`setRgb`/`lighter`/
  `darker`/`toHsv`/`name(HexArgb)`/`fromRgb*`/`setNamedColor` and channel-based `__eq__`.
- **Geometry**: `QPoint`/`QRect`/`QSize` gained the operator overloads and methods
  (`center`, `adjusted`, `contains`, `intersected`, `translated`, `boundedTo`,
  `manhattanLength`, …); added real `QPointF`/`QRectF`/`QSizeF`/`QLine`/`QLineF` instead of
  `_AutoAttr` sentinels.
- **Enums**: complete `Qt.Key`; added `Qt.MouseButton`, `KeyboardModifier`, `ItemDataRole`,
  `FocusPolicy`, `TextFormat`, `ContextMenuPolicy`, `ConnectionType`, `AspectRatioMode`,
  `TransformationMode`, `TextElideMode`, `LayoutDirection`. Qt6 scoped access
  (`Qt.AlignmentFlag.AlignLeft`) works alongside the flat form. Any `Qt.<member>` not
  shipped returns a stable placeholder instead of raising `AttributeError`.
- **`QSettings`** — a working shim backed by a JSON file under the user config dir; honours
  the default passed to `value()`, and persists.
- **`QApplication`**: `quit()`/`exit()` actually unblock `exec()` (which now emits
  `aboutToQuit`); added `clipboard()`, app-wide `setStyleSheet()`, `applicationName` /
  `organizationName`, `setQuitOnLastWindowClosed`, `topLevelWidgets` / `activeWindow`,
  `primaryScreen` / `screens`. `QCoreApplication` / `QGuiApplication` are aliases.
- **`QTimer`** uses one daemon thread per active timer instead of spawning a fresh
  `threading.Timer` (a whole thread) on every tick.
- `PYSIDEWEB_STRICT=1` makes every unknown-API access raise instead of no-opping.
  Independently, `isFoo()`/`hasFoo()` predicate names raise from the fallback so
  `hasattr(w, "hasHeightForWidth")` is `False` and feature-detecting libraries take the
  right branch.
- `QAction(*args)` parses all Qt overloads (previously `QAction("Save", win)` stored the
  parent as the action's text).

### Changed
- QSS → CSS translation moved from `renderer.js` to `pysideweb/qss.py` (server-side,
  pytest-covered); behaviour unchanged. Browser-inbound events now ride the same 50 ms
  broadcast debounce as server-side changes (a browser slider drag no longer round-trips a
  full tree per pixel). Static assets served with `Cache-Control: no-cache`.

### Added
- Widgets: `QDial` (rotary slider, drawn as a draggable SVG dial), `QTableWidget` /
  `QTableWidgetItem` (headers, per-cell items, `cellClicked` selection, editable cells
  via `ItemIsEditable` → `cellChanged`), and `QTreeWidget` / `QTreeWidgetItem` (nested
  items, per-column text, `expandAll`, expand/collapse toggles, `itemClicked` /
  `itemExpanded`). All three ride the reflective `Prop`/serialization machinery, so
  they're exposed through the fake `PySide6.QtWidgets` automatically.
- QSS → CSS translation: `setStyleSheet()` now accepts real Qt Style Sheets, not only
  a flat declaration list. Rule blocks, `:pressed` / `:hover` / `:checked` / `:disabled`
  pseudo-states, and common sub-controls (`::item`, `::chunk`, `::tab`, …) are
  translated to CSS scoped to the widget's subtree (`[data-wid="wN"] …`) and injected
  as a `<style>` element, so a stylesheet neither leaks to sibling widgets nor needs
  per-property handling in Python. Qt-only bits (`qproperty-*`, sub-controls we don't
  model) are dropped rather than misapplied. A bare declaration list still works as
  before. Also: `renderTree` now has a `setTimeout` fallback beside
  `requestAnimationFrame`, so the first paint still happens in a backgrounded /
  non-compositing tab where rAF is throttled to never.
- `QPainter` coverage widened: `QImage` / `QPixmap` read a local file and carry it to
  the browser as a `data:` URL (so `drawImage` / `drawPixmap` actually show it; http/
  data URLs pass through, a missing path is kept verbatim); `setCompositionMode()` maps
  the full `CompositionMode_*` set to canvas `globalCompositeOperation`; `QFontMetrics`
  / `QFontMetricsF` are real now, backed by a per-character width table (approximate —
  no font engine server-side — but far closer than a flat multiplier), with
  `horizontalAdvance` / `boundingRect` / `elidedText` / the vertical metrics.
- Example: `examples/data_browser.py`, a `QTreeWidget` / `QTableWidget` / `QDial`
  layout themed with a single `setStyleSheet` call.
- Virtual `QPainter` pipeline (`pysideweb/painting.py`): a `QWidget` subclass that
  overrides `paintEvent` now renders for real in the browser instead of as a dashed
  "unsupported" box. `QPainter` records each drawing call (`drawLine`, `drawRect`,
  `drawRoundedRect`, `drawEllipse`, `drawArc`/`drawPie`/`drawChord`, `drawPolygon`,
  `drawPath`, `drawText`, `fillRect`, gradients, the affine transform stack, opacity
  and clipping) as a JSON command; `renderer.js` replays the list onto an HTML5
  `<canvas>` sized to the widget. `update()` / `repaint()` re-run `paintEvent`.
  Supporting value types are real now too — `QPen`, `QBrush`, `QPainterPath`,
  `QPolygon`/`QPolygonF`, `QLinearGradient`/`QRadialGradient`, `QImage`/`QPixmap` —
  as are `Qt.PenStyle` / `Qt.BrushStyle` / `Qt.GlobalColor` and `QColor(Qt.red)`-style
  construction. Pixel readback stays impossible (nothing is rasterized in Python); a
  broken `paintEvent` is caught and skipped rather than breaking serialization; an
  unimplemented painter method is absorbed like the rest of pysideweb's unknown API.
- Example: `examples/custom_paint.py`, a resource monitor with a `QPainter`-drawn
  circular gauge and a scrolling sparkline, fed by a `QTimer`.
- Universal fallback for PySide6 API PySideWeb doesn't implement, so third-party PySide6
  libraries (not just apps written directly against PySideWeb) degrade gracefully instead
  of crashing: an unimplemented `QtWidgets` class becomes a real, addable/showable
  `QWidget` placeholder; an unimplemented method on any widget is silently absorbed; an
  unimplemented value type (`QTransform`, ...) or submodule (`PySide6.QtCharts`, ...) is
  constructible, chainable, and inert. The renderer marks a placeholder widget visually
  (dashed outline + class name) so it reads as "unsupported", not as a bug. `core._AutoAttr`
  is the underlying permissive object; `interceptor.py`'s per-module `__getattr__` (plus a
  `sys.meta_path` finder for bare `import PySide6.<Something>`) is the entry point.
  pysideweb's own internal duck typing (`hasattr(widget, "_children")` and similar) is
  unaffected -- only public, non-underscore-prefixed names are absorbed. Placeholder
  classes are built with `core._AutoAttrMeta`, so class-level constants referenced without
  an instance (`QGraphicsView.ScrollHandDrag`, `QAbstractItemView.SelectRows`, ...) are
  absorbed too, not just instance attribute access.
- Example: `examples/third_party_widget.py`, a stand-in for a third-party PySide6 library
  (subclasses `QGraphicsView`, imports from the unstubbed `PySide6.QtCharts`) that
  demonstrates the universal fallback end to end.

### Security
- Renderer: `QLabel`/`QPushButton` text containing `<...>` was rendered via `innerHTML`
  with no sanitization -- text reaching a label often originates from data the app
  didn't author (a network response, user input echoed back), making this a direct DOM
  XSS sink even though real Qt's rich-text renderer never executes script. An
  allowlist-based sanitizer (`sanitizeRichText` in `renderer.js`) now strips
  non-formatting tags and event-handler/`javascript:` attributes before the HTML is
  ever assigned.
- Server: `TCPSite` bound to `0.0.0.0` unconditionally, exposing the unauthenticated
  `/ws` endpoint (full read/write access to the app's widget tree) to the whole LAN by
  default. Now defaults to `127.0.0.1`; set `PYSIDEWEB_HOST` to opt into wider exposure.

### Added
- Examples: `preferences.py` (an application settings screen) and `contacts.py` (a
  master–detail record manager), with a restrained, professional visual style, plus an
  `examples/README.md` index. Replaces the earlier demo set.
- Test suite (`tests/`) covering the interceptor, core signal/value types, widgets, and
  state serialization.

### Fixed
- `QSlider.setValue` and `QSpinBox.setValue` now emit `valueChanged` when the value
  changes, matching Qt behavior for programmatic updates.
- Serialization crashed on a layout nested inside another sub-layout (doubly-nested
  `addLayout`); `_serialize_layout_as_container` now recurses into nested layouts and
  guards against `None` item ids.
- Continuous integration (GitHub Actions) running ruff + pytest on Python 3.10–3.13.
- `examples/hello.py` minimal example; demos moved under `examples/`.
- Project documentation: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `docs/ARCHITECTURE.md`,
  issue/PR templates, and an expanded `README.md`.
- Packaging metadata (classifiers, keywords, URLs, dev extras) and ruff configuration.

## [0.1.0] - 2026-07-11

### Added
- Initial release: intercept PySide6 imports and render the widget tree in a browser via
  an aiohttp WebSocket server.
- Virtual implementations of common QtWidgets, layouts, and QtCore/QtGui types.
