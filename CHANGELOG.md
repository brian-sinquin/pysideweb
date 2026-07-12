# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
