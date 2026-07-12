# Examples

Each example is a standalone PySide6 program. The only thing that makes it render in the
browser is the `import pysideweb` line at the very top — it must come **before** any
`PySide6` import.

Run any of them with:

```bash
uv run python examples/<name>.py
# then open http://localhost:8765
```

| File | What it shows |
|------|---------------|
| [`hello.py`](hello.py) | The smallest possible app — a button and a click counter. Start here. |
| [`smart_home.py`](smart_home.py) | **Smart Home control panel.** Per-room device toggles, dimmer sliders, a thermostat, one-tap scenes, and a live energy meter driven by `QTimer`. Good tour of checkboxes, sliders, buttons, and live updates. |
| [`kanban.py`](kanban.py) | **Kanban task board.** Add tasks with a priority, then move them across To Do → In Progress → Done and watch a completion progress bar. Good tour of `QLineEdit`, `QComboBox`, `QListWidget`, and multi-column layouts. |
| [`demo_app.py`](demo_app.py) | A multi-tab "phone" UI that exercises most supported widgets at once. |
| [`demo_simulation.py`](demo_simulation.py) | A live CPU/memory monitor and particle simulation. |

## Writing your own

Copy `hello.py` and go. The rule to remember:

```python
import pysideweb          # 1. FIRST — installs the import interceptor
from PySide6.QtWidgets import ...   # 2. then your normal PySide6 imports
```
