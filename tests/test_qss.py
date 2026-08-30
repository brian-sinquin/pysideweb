"""Tests for the QSS -> scoped CSS translator (pysideweb/qss.py)."""

from pysideweb import qss

SCOPE = '[data-wid="w7"]'


def t(css: str) -> str:
    return qss.translate(css, SCOPE)


class TestRulesetDetection:
    def test_bare_declarations_not_a_ruleset(self):
        assert not qss.looks_like_ruleset("color: red; font-weight: bold")

    def test_block_is_a_ruleset(self):
        assert qss.looks_like_ruleset("QPushButton { color: red }")


class TestSelectors:
    def test_type_matches_host_and_descendants(self):
        out = t("QPushButton { color: red }")
        assert '[data-wid="w7"].qpushbutton' in out
        assert '[data-wid="w7"] .qpushbutton' in out
        assert "color: red" in out

    def test_pseudo_states(self):
        assert ".qpushbutton:active" in t("QPushButton:pressed { color: red }")
        assert ".qpushbutton:hover" in t("QPushButton:hover { color: red }")
        assert ".qcheckbox:checked" in t("QCheckBox:checked { color: red }")

    def test_object_name_selector(self):
        assert '[data-wid="w7"]#saveBtn' in t("#saveBtn { font-weight: bold }")

    def test_class_selector_lowercased(self):
        assert '[data-wid="w7"] .qframe' in t(".QFrame { border: 1px solid gray }")

    def test_comma_group_expands(self):
        out = t("QLabel, QPushButton { color: red }")
        assert ".qlabel" in out and ".qpushbutton" in out

    def test_descendant_combinator(self):
        out = t("QWidget QLabel { margin: 4px }")
        assert '[data-wid="w7"] .qwidget .qlabel' in out
        # descendant selector should NOT also get the host-matching variant
        assert '[data-wid="w7"].qwidget .qlabel' not in out

    def test_subcontrol_item_selected(self):
        out = t("QListWidget::item:selected { background: blue }")
        assert '[data-wid="w7"] .qlistwidget .list-item.selected' in out

    def test_subcontrol_chunk(self):
        assert ".qprogressbar .progress-fill" in t(
            "QProgressBar::chunk { background: green }"
        )

    def test_unmodelled_subcontrol_skips_rule(self):
        # ::drop-down isn't mapped to a single element -> rule dropped, not
        # mis-targeted at the whole combobox.
        assert t("QComboBox::drop-down { width: 20px }") == ""


class TestBody:
    def test_qt_only_props_dropped(self):
        out = t("QCheckBox { qproperty-iconSize: 20px; color: #eee }")
        assert "qproperty" not in out
        assert "color: #eee" in out

    def test_style_breakout_guarded(self):
        out = t("QLabel { content: '</style><script>' }")
        assert "<script>" not in out

    def test_empty_body_produces_nothing(self):
        assert t("QLabel { }") == ""

    def test_comments_stripped(self):
        out = t("/* theme */ QLabel { color: red } /* end */")
        assert "theme" not in out and "color: red" in out


class TestIntegration:
    def test_widget_get_props_carries_translated_css(self):
        from PySide6.QtWidgets import QWidget

        from pysideweb import state

        w = QWidget()
        w.setStyleSheet("QLabel { color: #123456 }")
        w.show()
        props = state.serialize_widget(w)["props"]
        assert "color: #123456" in props["styleSheetCss"]
        assert props["styleSheetCss"].startswith(f'[data-wid="{w._wid}"]')

    def test_bare_declarations_pass_through_untranslated(self):
        from PySide6.QtWidgets import QWidget

        from pysideweb import state

        w = QWidget()
        w.setStyleSheet("background: #222; color: white")
        w.show()
        props = state.serialize_widget(w)["props"]
        assert "styleSheetCss" not in props
        assert props["styleSheet"] == "background: #222; color: white"
