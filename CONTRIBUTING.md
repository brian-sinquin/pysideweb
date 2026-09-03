# Contributing to PySideWeb

Thanks for your interest in improving PySideWeb! This document explains how to get set up
and what we expect from contributions.

## Development setup

We use [uv](https://github.com/astral-sh/uv) for environment and dependency management.

```bash
git clone https://github.com/brian-sinquin/pysideweb.git
cd pysideweb
uv venv
uv pip install -e ".[dev]"
```

Run an example to confirm everything works:

```bash
uv run python examples/preferences.py
# then open http://localhost:8765
```

## Running checks

Before opening a pull request, make sure both of these pass:

```bash
ruff check .      # lint
pytest -q         # Python tests
node --test tests_js/*.test.cjs  # renderer protocol tests (Node.js 22+)
python benchmarks/benchmark.py   # JSON performance baseline
```

Chromium end-to-end tests run in CI. Locally, install `@playwright/test@1.55.1`
and its Chromium binary, then run:

```bash
npx playwright test --config tests_browser/playwright.config.cjs
```

Auto-fix lint issues where safe:

```bash
ruff check --fix .
```

> ⚠️ **Important:** In example scripts, `import pysideweb` **must** stay above the
> `PySide6` imports — it is imported for its import-time side effect (patching
> `sys.modules`). Import sorters will try to move or delete it; the `examples/` folder is
> deliberately exempted from those rules in `pyproject.toml`. Don't "fix" that line.

## Project layout

```
pysideweb/
├── __init__.py       # installs the import interceptor on import
├── interceptor.py    # patches sys.modules → PySide6.* become virtual
├── core.py           # QtCore: Signal/Slot, Qt enums, value types, QTimer, QApplication
├── widgets/          # virtual QWidget subclasses, grouped by responsibility
├── layouts.py        # virtual layouts
├── state.py          # widget registry, JSON serializer, diff + event dispatch
├── server.py         # aiohttp HTTP + WebSocket server (daemon thread)
└── static/           # browser renderer (HTML/CSS/JS)
examples/             # runnable demos
tests/                # pytest suite
docs/                 # design docs
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a deeper tour.

## Adding a new widget

1. Add the class to the appropriate module in `pysideweb/widgets/`, subclassing
   `QWidget`, and re-export it from `pysideweb/widgets/__init__.py`. Give it a
   `_widget_type` string and implement `_get_props()` (and `_handle_event()` if it is
   interactive).
2. The interceptor discovers exported `Q*` classes automatically; no registry edit is needed.
3. Teach the browser renderer (`pysideweb/static/renderer.js`) how to render it.
4. Add a test in `tests/` covering props and any events.

## Pull request guidelines

- Keep PRs focused and reasonably small.
- Match the surrounding code style (naming, comment density, idioms).
- Add or update tests for behavior changes.
- Update `README.md` / `CHANGELOG.md` when you add user-facing features.
- Make sure `ruff check .`, `pytest -q`, and `node --test tests_js/*.test.cjs` are green.

## Reporting bugs / requesting features

Use the [issue tracker](https://github.com/brian-sinquin/pysideweb/issues). For bugs,
include a minimal reproducible example and your Python version.

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
