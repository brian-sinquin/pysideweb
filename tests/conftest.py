"""Shared pytest fixtures.

Importing ``pysideweb`` patches ``sys.modules`` so that ``PySide6`` resolves to
the virtual implementation. This happens once for the whole test session.
"""

import pytest

import pysideweb  # noqa: F401  (side effect: install the import interceptor)
from pysideweb import state


@pytest.fixture(autouse=True)
def clean_state():
    """Reset the global widget registry between tests."""
    state.drain_changes()
    roots = state.get_roots()
    for root in roots:
        state.remove_root(root)
    yield
    state.drain_changes()
    for root in state.get_roots():
        state.remove_root(root)
