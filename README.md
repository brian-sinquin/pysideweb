# PySideWeb

Write standard PySide6 code and render it in a web browser — no Qt installation required.

[![CI](https://github.com/brian-sinquin/pysideweb/actions/workflows/ci.yml/badge.svg)](https://github.com/brian-sinquin/pysideweb/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

PySideWeb is a drop-in shim for [PySide6](https://doc.qt.io/qtforpython/). Add a single
`import pysideweb` line above your Qt imports and your existing widget code renders as a
live web app at `http://localhost:8765` — with no Qt binaries, no C++ toolchain, and no
native display server.

```python
import pysideweb  # the only new line

from PySide6.QtWidgets import QApplication, QPushButton

app = QApplication([])
button = QPushButton("Hello, browser")
button.clicked.connect(lambda: print("clicked!"))
button.show()
app.exec()
```

Open the browser and the button is there; clicks fire your Python callback in real time.

## Why

- **No native dependency.** No PySide6 wheel (~100 MB), no system Qt libraries — only `aiohttp`.
- **The real PySide6 API.** The same `QWidget`, `QVBoxLayout`, `Signal`/`Slot`, and `QTimer`.
  Existing code often runs unchanged.
- **Live and bidirectional.** The widget tree streams to the browser over WebSocket; user
  interactions fire Qt signals back in Python.
- **Runs anywhere Python does.** Headless servers, containers, CI, remote machines.

## Installation

Using [uv](https://github.com/astral-sh/uv) (recommended):

```bash
git clone https://github.com/brian-sinquin/pysideweb.git
cd pysideweb
uv run python examples/preferences.py
```

Using pip:

```bash
pip install -e .
python examples/preferences.py
```

Then open http://localhost:8765 (PySideWeb opens it for you automatically).

## How it works

1. `import pysideweb` patches `sys.modules` so that every `from PySide6.QtWidgets import ...`
   resolves to lightweight pure-Python widget classes instead of native Qt.
2. Your code runs normally, building a virtual widget tree held in `pysideweb.state`.
3. An `aiohttp` WebSocket server (daemon thread) serializes that tree to JSON and streams
   debounced diffs to the browser.
4. The browser renderer reconstructs the DOM; user interactions travel back over the socket
   and are re-emitted as Qt signals.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Supported widgets

| Category   | Widgets |
|------------|---------|
| Containers | `QWidget`, `QMainWindow`, `QFrame`, `QGroupBox`, `QScrollArea`, `QStackedWidget`, `QTabWidget`, `QSplitter` |
| Buttons    | `QPushButton`, `QCheckBox`, `QRadioButton`, `QButtonGroup` |
| Input      | `QLineEdit`, `QTextEdit`, `QComboBox`, `QSpinBox`, `QDoubleSpinBox`, `QSlider` |
| Display    | `QLabel`, `QProgressBar`, `QListWidget` / `QListWidgetItem` |
| Chrome     | `QMenuBar`, `QMenu`, `QAction`, `QToolBar`, `QStatusBar` |
| Layouts    | `QVBoxLayout`, `QHBoxLayout`, `QGridLayout`, `QFormLayout`, `QStackedLayout` |
| Core       | `Signal`, `Slot`, `QTimer`, `Qt`, `QSize`, `QPoint`, `QRect`, `QColor`, `QFont` |

Not every Qt method is implemented; PySideWeb targets the common application surface.
Missing something? [Open an issue](https://github.com/brian-sinquin/pysideweb/issues) or see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Configuration

| Environment variable | Default     | Description |
|----------------------|-------------|-------------|
| `PYSIDEWEB_PORT`     | `8765`       | Port for the HTTP and WebSocket server |
| `PYSIDEWEB_HOST`     | `127.0.0.1`  | Interface to bind to. The `/ws` endpoint has no authentication, so anything that can reach it can inspect and drive your app's UI — only set this to `0.0.0.0` (or a specific LAN address) if you intend to open the app to other devices on your network, and understand that anyone on that network can then control it. |

## Examples

Run any with `uv run python examples/<name>.py`, then open http://localhost:8765.
See [examples/README.md](examples/README.md) for details.

- [preferences.py](examples/preferences.py) — an application settings screen: grouped
  sections of controls with a Save / Reset action bar.
- [contacts.py](examples/contacts.py) — a master–detail record manager: a contact list
  alongside an editable detail form.

## Roadmap

- Additional widgets (`QTableWidget`, `QTreeWidget`, `QDial`)
- QSS stylesheet translation
- PyPI release
- Per-session isolation for multiple simultaneous clients

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md) before opening a pull request.

## License

[MIT](LICENSE) © PySideWeb Contributors

PySideWeb is an independent project and is not affiliated with or endorsed by the Qt Company
or the PySide project.
