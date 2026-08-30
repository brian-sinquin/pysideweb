"""Compatibility surface: QObject hierarchy, value types, enums, QSettings.

These pin down the behaviours real third-party PySide6 code relies on that the
universal fallback used to answer wrongly (isinstance checks, colour channel
readback, float geometry, enum access).
"""

from PySide6.QtCore import (
    QLine,
    QModelIndex,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAction, QPushButton, QWidget


class TestObjectHierarchy:
    def test_widget_is_qobject(self):
        assert issubclass(QWidget, QObject)
        assert isinstance(QPushButton("x"), QObject)
        assert isinstance(QTimer(), QObject)
        assert isinstance(QAction("a"), QObject)

    def test_custom_qobject_subclass_with_signal(self):
        class Worker(QObject):
            done = Signal(int)

        w = Worker()
        got = []
        w.done.connect(got.append)
        w.done.emit(42)
        assert got == [42]

    def test_block_signals(self):
        b = QPushButton("x")
        hits = []
        b.clicked.connect(lambda *a: hits.append(1))
        prev = b.blockSignals(True)
        assert prev is False
        b.clicked.emit()
        assert hits == []
        b.blockSignals(False)
        b.clicked.emit()
        assert hits == [1]

    def test_sender(self):
        class S(QObject):
            sig = Signal()

        s = S()
        seen = []
        s.sig.connect(lambda: seen.append(s.sender()))
        s.sig.emit()
        assert seen == [s]

    def test_dynamic_properties_on_plain_qobject(self):
        o = QObject()
        assert o.property("missing") is None
        o.setProperty("k", 5)
        assert o.property("k") == 5
        assert "k" in o.dynamicPropertyNames()

    def test_inherits(self):
        assert QPushButton("x").inherits("QWidget")
        assert QPushButton("x").inherits("QObject")
        assert not QPushButton("x").inherits("QLineEdit")


class TestQColor:
    def test_hex_channels(self):
        c = QColor("#ff8800")
        assert (c.red(), c.green(), c.blue()) == (255, 136, 0)
        assert QColor("#f80").getRgb() == (255, 136, 0, 255)

    def test_named_color_channels(self):
        assert QColor("steelblue").getRgb() == (70, 130, 180, 255)
        assert QColor("rebeccapurple").red() == 102

    def test_argb_hex(self):
        c = QColor("#80ff0000")  # Qt's #AARRGGBB
        assert c.alpha() == 128 and c.red() == 255

    def test_equality_is_channel_based(self):
        assert QColor("#ff0000") == QColor(255, 0, 0)
        assert QColor("red") == QColor(255, 0, 0, 255)
        assert QColor(1, 2, 3) != QColor(1, 2, 4)

    def test_qrgb_int_ctor(self):
        c = QColor(0xFF8800)
        assert (c.red(), c.green(), c.blue()) == (255, 136, 0)

    def test_global_color_enum(self):
        assert QColor(Qt.red).getRgb() == (255, 0, 0, 255)

    def test_lighter_darker_roundtrip_direction(self):
        base = QColor(80, 80, 80)
        assert base.lighter(150).value() > base.value()
        assert base.darker(200).value() < base.value()

    def test_name_formats(self):
        assert QColor(255, 0, 0).name() == "#ff0000"
        assert QColor(255, 0, 0, 128).name(QColor.HexArgb) == "#80ff0000"

    def test_invalid(self):
        assert not QColor().isValid()
        assert not QColor("definitely-not-a-color").isValid()


class TestGeometryTypes:
    def test_pointf_is_real(self):
        p = QPointF(1.5, 2.5)
        assert p.x() == 1.5
        assert (p + QPointF(0.5, 0.5)).x() == 2.0
        assert (p * 2).y() == 5.0

    def test_point_ops(self):
        assert QPoint(3, -4).manhattanLength() == 7
        assert QPoint(1, 1) + QPoint(2, 3) == QPoint(3, 4)
        assert -QPoint(1, 2) == QPoint(-1, -2)

    def test_rect_geometry(self):
        r = QRect(0, 0, 10, 20)
        assert r.center() == QPoint(4, 9)  # Qt: inclusive right/bottom
        assert r.adjusted(1, 1, -1, -1).getRect() == (1, 1, 8, 18)
        assert r.contains(QPoint(5, 5)) and not r.contains(QPoint(50, 50))
        assert r.translated(5, 5).topLeft() == QPoint(5, 5)

    def test_rect_set_operations(self):
        a = QRect(0, 0, 10, 10)
        b = QRect(5, 5, 10, 10)
        assert a.intersected(b).getRect() == (5, 5, 5, 5)
        assert a.united(b).getRect() == (0, 0, 15, 15)
        assert a.intersects(b)

    def test_rectf_float(self):
        r = QRectF(0.0, 0.0, 3.0, 4.0)
        assert r.center() == QPointF(1.5, 2.0)

    def test_size_ops(self):
        assert QSize(4, 9).boundedTo(QSize(6, 3)).toTuple() == (4, 3)
        assert QSize(4, 9).expandedTo(QSize(6, 3)).toTuple() == (6, 9)
        assert QSize(0, 5).isEmpty()

    def test_qline(self):
        assert QLine(0, 0, 3, 4).length() == 5.0
        assert QLine(0, 0, 4, 4).center() == QPoint(2, 2)


class TestEnums:
    def test_key_enum_complete(self):
        assert Qt.Key_F5 == 0x01000034
        assert Qt.Key_Left == 0x01000012
        assert Qt.Key_Space == 0x20

    def test_scoped_access(self):
        assert Qt.AlignmentFlag.AlignHCenter == Qt.AlignHCenter
        assert Qt.Key.Key_A == Qt.Key_A

    def test_item_data_roles(self):
        assert Qt.DisplayRole == 0
        assert Qt.UserRole == 256
        assert Qt.EditRole == 2

    def test_modifiers_bitwise(self):
        combo = Qt.ControlModifier | Qt.ShiftModifier
        assert combo & Qt.ControlModifier
        assert combo & Qt.ShiftModifier
        assert not (combo & Qt.AltModifier)

    def test_unknown_member_is_stable_not_crash(self):
        assert Qt.WA_DeleteOnClose == Qt.WA_DeleteOnClose
        assert Qt.WA_DeleteOnClose != Qt.WA_StaticContents


class TestQSettings:
    def test_default_is_kept(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        s = QSettings("acme", "widget-test")
        assert s.value("never-set", 42) == 42
        assert s.value("never-set", "fallback") == "fallback"

    def test_roundtrip_persists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        QSettings("acme", "rt").setValue("k", "v")
        assert QSettings("acme", "rt").value("k") == "v"

    def test_groups(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        s = QSettings("acme", "grp")
        s.beginGroup("window")
        s.setValue("w", 800)
        s.endGroup()
        assert s.value("window/w") == 800

    def test_type_coercion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        s = QSettings("acme", "ty")
        s.setValue("n", "5")
        assert s.value("n", 0, type=int) == 5


class TestValueTypesMisc:
    def test_qurl(self):
        u = QUrl.fromLocalFile("/tmp/x.txt")
        assert u.scheme() == "file"
        assert u.toLocalFile() == "/tmp/x.txt"
        assert QUrl("https://example.com").isValid()

    def test_qmodelindex(self):
        assert not QModelIndex().isValid()
        assert QModelIndex(2, 3).isValid()
        assert QModelIndex(2, 3) == QModelIndex(2, 3)
