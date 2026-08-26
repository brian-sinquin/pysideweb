# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
  unaffected -- only public, non-underscore-prefixed names are absorbed.

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
