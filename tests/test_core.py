"""Tests for the pure-Python QtCore reimplementation."""

import threading
import time

from pysideweb import core


class TestSignal:
    def test_connect_and_emit(self):
        received = []

        class Obj:
            changed = core.Signal(int)

        obj = Obj()
        obj.changed.connect(received.append)
        obj.changed.emit(42)

        assert received == [42]

    def test_multiple_slots(self):
        calls = []

        class Obj:
            fired = core.Signal()

        obj = Obj()
        obj.fired.connect(lambda: calls.append("a"))
        obj.fired.connect(lambda: calls.append("b"))
        obj.fired.emit()

        assert calls == ["a", "b"]

    def test_disconnect(self):
        received = []

        class Obj:
            changed = core.Signal(int)

        def slot(value):
            received.append(value)

        obj = Obj()
        obj.changed.connect(slot)
        obj.changed.disconnect(slot)
        obj.changed.emit(1)

        assert received == []

    def test_slot_receives_fewer_args_than_emitted(self):
        # A zero-arg slot connected to a signal that emits a value must not raise.
        called = []

        class Obj:
            changed = core.Signal(int)

        obj = Obj()
        obj.changed.connect(lambda: called.append(True))
        obj.changed.emit(99)

        assert called == [True]


class TestValueTypes:
    def test_qsize(self):
        s = core.QSize(10, 20)
        assert s.width() == 10
        assert s.height() == 20
        assert s.toTuple() == (10, 20)

    def test_qpoint(self):
        p = core.QPoint(3, 4)
        assert (p.x(), p.y()) == (3, 4)

    def test_qcolor_named(self):
        assert core.QColor("#ff0000").name() == "#ff0000"

    def test_qcolor_rgb(self):
        c = core.QColor(255, 0, 0)
        assert c.red() == 255 and c.green() == 0 and c.blue() == 0

    def test_qfont_to_css(self):
        f = core.QFont("Inter", 14)
        f.setBold(True)
        css = f.to_css()
        assert css["fontFamily"] == "Inter"
        assert css["fontSize"] == "14pt"
        assert css["fontWeight"] == "bold"


class TestQApplication:
    def test_instance_is_singleton(self):
        app = core.QApplication([])
        assert core.QApplication.instance() is app


class TestQTimer:
    def test_many_timers_share_one_scheduler_thread(self):
        before = threading.active_count()
        timers = [core.QTimer() for _ in range(50)]
        for timer in timers:
            timer.start(60_000)
        try:
            assert threading.active_count() <= before + 1
        finally:
            for timer in timers:
                timer.stop()

    def test_periodic_stop_and_restart(self):
        timer = core.QTimer()
        fired = threading.Event()
        calls = []
        timer.timeout.connect(lambda: (calls.append(time.monotonic()), fired.set()))
        timer.start(10)
        assert fired.wait(1)
        timer.stop()
        stopped_at = len(calls)
        time.sleep(0.04)
        assert len(calls) == stopped_at

        fired.clear()
        timer.start(5)
        assert fired.wait(1)
        timer.stop()
        assert len(calls) == stopped_at + 1

    def test_single_shot_survives_without_caller_reference(self):
        fired = threading.Event()
        core.QTimer.singleShot(5, fired.set)
        assert fired.wait(1)
