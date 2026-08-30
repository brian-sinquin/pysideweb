"""pysideweb.widgets.misc - QSizePolicy, spacers."""

from __future__ import annotations


class QSizePolicy:
    Fixed = 0
    Minimum = 1
    Maximum = 4
    Preferred = 5
    Expanding = 7
    MinimumExpanding = 3
    Ignored = 13

    def __init__(self, h_policy=Preferred, v_policy=Preferred):
        self._h = h_policy
        self._v = v_policy

    def setHorizontalStretch(self, stretch: int):
        pass

    def setVerticalStretch(self, stretch: int):
        pass


class QSpacerItem:
    def __init__(self, w=0, h=0, h_policy=QSizePolicy.Minimum, v_policy=QSizePolicy.Minimum):
        self._w = w
        self._h = h

class QWidgetItem:
    def __init__(self, widget):
        self._widget = widget
