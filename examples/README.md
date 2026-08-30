# Examples

Each example is a standalone PySide6 program. The only thing that makes it render in the
browser is the `import pysideweb` line at the top — it must come **before** any `PySide6`
import.

Run any of them with:

```bash
uv run python examples/<name>.py
# then open http://localhost:8765
```

| File | Description |
|------|-------------|
| [preferences.py](preferences.py) | An application settings screen. Grouped sections of labelled controls (line edits, dropdowns, checkboxes, a slider) with a Save / Reset action bar. |
| [contacts.py](contacts.py) | A master–detail record manager. A contact list on the left, an editable detail form on the right; select, edit, add, and delete records. |
| [custom_paint.py](custom_paint.py) | A resource monitor whose widgets draw themselves in `paintEvent` with `QPainter` — a circular gauge (arcs, text) and a scrolling sparkline (polyline, gradient fill), animated by a `QTimer`. Demonstrates the virtual painting pipeline: painter calls are recorded and replayed on a `<canvas>`. |
| [third_party_widget.py](third_party_widget.py) | A stand-in for a third-party PySide6 library (think pyqtgraph): subclasses `QGraphicsView` and imports from `PySide6.QtCharts`, neither implemented by pysideweb. Demonstrates the universal fallback — nothing crashes, the widget just renders as a labeled placeholder. |

## Writing your own

Copy `preferences.py` and adapt it. The rule to remember:

```python
import pysideweb                     # 1. FIRST — installs the import interceptor
from PySide6.QtWidgets import ...     # 2. then your normal PySide6 imports
```
