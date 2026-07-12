<div align="center">

# 🌐 PySideWeb

**Write standard PySide6 code. Render it in the browser. No Qt required.**

[![CI](https://github.com/brian-sinquin/pysideweb/actions/workflows/ci.yml/badge.svg)](https://github.com/brian-sinquin/pysideweb/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

</div>

---

PySideWeb is a drop-in shim for [PySide6](https://doc.qt.io/qtforpython/). Add a single
`import pysideweb` line above your Qt imports, and your existing widget code renders as a
live web app at `http://localhost:8765` — **with no Qt binaries, no C++ toolchain, and no
native display server**.

```python
import pysideweb  # ← the only new line

from PySide6.QtWidgets import QApplication, QPushButton

app = QApplication([])
button = QPushButton("Hello, browser 👋")
button.clicked.connect(lambda: print("clicked!"))
button.show()
app.exec()
```

Open your browser — the button is there, and clicks fire your Python callback in real time.

## ✨ Why PySideWeb?

- **Zero-install UI** — no `PySide6` wheel (~100 MB), no system Qt libraries. Just `aiohttp`.
- **Real PySide6 API** — the same `QWidget`, `QVBoxLayout`, `Signal`/`Slot`, and `QTimer`
  you already know. Existing code often runs unchanged.
- **Live & bidirectional** — the widget tree streams to the browser over WebSocket; clicks,
  text input, and slider drags fire Qt signals back in Python.
- **Runs anywhere Python does** — headless servers, containers, CI, remote boxes, Jupyter.
- **Instant reload** — no compile step. Edit, rerun, refresh.

## 🚀 Quick Start

### With [uv](https://github.com/astral-sh/uv) (recommended)

```bash
git clone https://github.com/brian-sinquin/pysideweb.git
cd pysideweb
uv run python examples/demo_app.py
```

### With pip

```bash
pip install -e .
python examples/demo_app.py
```

Then open **http://localhost:8765** (PySideWeb opens it for you automatically).

## 🧩 How It Works

```
┌─────────────────┐   import pysideweb    ┌──────────────────────┐
│  Your PySide6    │ ───────────────────►  │  sys.modules patched │
│  application     │                       │  PySide6.* → virtual │
└─────────────────┘                        └──────────┬───────────┘
         │ builds widgets                              │
         ▼                                              ▼
┌─────────────────┐    serialize + diff    ┌──────────────────────┐
│  Virtual widget │ ───────────────────►   │  aiohttp WebSocket    │
│  tree (state)   │  ◄─────────────────    │  hub (daemon thread)  │
└─────────────────┘     browser events     └──────────┬───────────┘
                                                        │ JSON tree
                                                        ▼
                                            ┌──────────────────────┐
                                            │  Browser renderer.js  │
                                            │  → live DOM           │
                                            └──────────────────────┘
```

1. `import pysideweb` patches `sys.modules` so every `from PySide6.QtWidgets import ...`
   resolves to lightweight pure-Python widget classes instead of native Qt.
2. Your code runs normally, building a **virtual widget tree** held in `pysideweb.state`.
3. An `aiohttp` WebSocket server (daemon thread) serializes that tree to JSON and streams
   debounced diffs to the browser.
4. The browser renderer reconstructs the DOM; user interactions travel back over the
   socket and are re-emitted as Qt `Signal`s.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## 📦 Supported Widgets

| Category  | Widgets |
|-----------|---------|
| Containers | `QWidget`, `QMainWindow`, `QFrame`, `QGroupBox`, `QScrollArea`, `QStackedWidget`, `QTabWidget`, `QSplitter` |
| Buttons    | `QPushButton`, `QCheckBox`, `QRadioButton`, `QButtonGroup` |
| Input      | `QLineEdit`, `QTextEdit`, `QComboBox`, `QSpinBox`, `QDoubleSpinBox`, `QSlider` |
| Display    | `QLabel`, `QProgressBar`, `QListWidget` / `QListWidgetItem` |
| Chrome     | `QMenuBar`, `QMenu`, `QAction`, `QToolBar`, `QStatusBar` |
| Layouts    | `QVBoxLayout`, `QHBoxLayout`, `QGridLayout`, `QFormLayout`, `QStackedLayout` |
| Core       | `Signal`, `Slot`, `QTimer`, `Qt`, `QSize`, `QPoint`, `QRect`, `QColor`, `QFont` |

Not every Qt method is implemented — PySideWeb targets the common application surface.
Missing something? [Open an issue](https://github.com/brian-sinquin/pysideweb/issues) or
see [CONTRIBUTING.md](CONTRIBUTING.md).

## ⚙️ Configuration

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `PYSIDEWEB_PORT`     | `8765`  | Port for the HTTP + WebSocket server |

## 🧪 Examples

Run any with `uv run python examples/<name>.py`, then open http://localhost:8765.
See [`examples/README.md`](examples/README.md) for the full list.

- [`hello.py`](examples/hello.py) — the smallest possible app (button + click counter)
- [`smart_home.py`](examples/smart_home.py) — a Smart Home control panel: device toggles,
  dimmers, thermostat, scenes, and a live energy meter
- [`kanban.py`](examples/kanban.py) — a Kanban task board: add tasks and move them across
  To Do → In Progress → Done with a live completion bar
- [`demo_app.py`](examples/demo_app.py) — a multi-tab "phone" UI showcasing many widgets
- [`demo_simulation.py`](examples/demo_simulation.py) — a live CPU/memory monitor + sim

## 🗺️ Roadmap

- [ ] More widgets (`QTableWidget`, `QTreeWidget`, `QDial`)
- [ ] CSS/QSS stylesheet translation
- [ ] Publish to PyPI
- [ ] Multi-client session isolation
- [ ] Optional authentication for the web server

## 🤝 Contributing

Contributions are very welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) and our
[Code of Conduct](CODE_OF_CONDUCT.md) before opening a PR.

## 📄 License

[MIT](LICENSE) © PySideWeb Contributors

> **Note:** PySideWeb is an independent project and is not affiliated with or endorsed by
> the Qt Company or the PySide project.
