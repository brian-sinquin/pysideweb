"""
pysideweb.qss — Qt Style Sheet -> scoped CSS translation.

Qt Style Sheets look like CSS but aren't: `QPushButton:pressed`, sub-controls
(`::item`, `::chunk`), and Qt-only properties (`qproperty-*`). This turns a
stylesheet into real CSS rules scoped to one widget's subtree
(`[data-wid="wN"] ...`) so a stylesheet neither leaks to sibling widgets nor
needs per-property handling in the renderer. It's Python (not renderer.js) so
it's covered by the normal pytest run; the browser only injects a `<style>`.

A bare declaration list (no `{`) is not our job -- the caller applies it inline.
"""

from __future__ import annotations

import re

from .qss_sanitizer import QSSSanitizer

# Qt pseudo-state -> CSS. A value that's a real pseudo (":hover") attaches to
# the target selector; a bare-class value (".selected") is a class our
# renderers set. "" drops the state (matches nothing special).
_PSEUDO = {
    "pressed": ":active", "hover": ":hover", "checked": ":checked",
    "unchecked": ":not(:checked)", "disabled": ":disabled", "enabled": ":enabled",
    "focus": ":focus", "on": ":checked", "off": ":not(:checked)",
    "selected": ".selected", "first": ":first-child", "last": ":last-child",
    "read-only": ":read-only", "no-frame": "",
}

# Sub-control -> a single descendant selector matching what the renderers emit.
# None means "we don't model this as one element" -> skip the whole rule
# rather than mis-target it.
_SUBCONTROL: dict[str, str | None] = {
    "item": " .list-item", "indicator": " input", "handle": " input[type=range]",
    "chunk": " .progress-fill", "tab": " .tab-item", "tab-bar": " .tab-bar",
    "pane": " .tab-content", "title": " .group-title", "section": " th",
    "add-line": None, "sub-line": None, "up-button": None, "down-button": None,
    "drop-down": None, "up-arrow": None, "down-arrow": None, "groove": None,
    "add-page": None, "sub-page": None,
}

_DROP_PROP = re.compile(
    r"^(qproperty-|subcontrol-|alternate-background-color|gridline-color"
    r"|show-decoration-selected|selection-color|selection-background-color"
    r"|titlebar-|button-layout|messagebox-|icon-size$|spacing$)"
)

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_SUB_RE = re.compile(r"::([a-z-]+)")
_PSEUDO_RE = re.compile(r":([a-z-]+)")
_COMPOUND_ID = re.compile(r"#([A-Za-z0-9_-]+)")
_COMPOUND_ATTR = re.compile(r"\[[^\]]+\]")
_COMPOUND_NAME = re.compile(r"\.?([A-Za-z_][A-Za-z0-9_]*)")


def looks_like_ruleset(css: str) -> bool:
    """True if `css` is a QSS ruleset (has selector blocks), vs a bare
    `prop: value; ...` declaration list the caller should apply inline."""
    return "{" in css


def translate(qss: str, scope: str) -> str:
    """Translate a QSS ruleset into CSS with every selector prefixed by
    `scope` (e.g. `[data-wid="w7"]` or `#app`). Returns "" if nothing usable
    survived."""
    qss = _COMMENT.sub("", QSSSanitizer.sanitize(qss or ""))
    out: list[str] = []
    for sel_group, body_src in _RULE.findall(qss):
        body = _translate_body(body_src)
        if not body:
            continue
        selectors = [
            t for s in sel_group.split(",")
            if (t := _translate_selector(s.strip(), scope))
        ]
        if selectors:
            joined = ",\n".join(selectors)
            out.append(f"{joined} {{ {body} }}")
    return "\n".join(out)


def _translate_body(body: str) -> str:
    keep = []
    for decl in body.split(";"):
        prop, sep, val = decl.partition(":")
        prop = prop.strip().lower()
        val = val.strip()
        if not sep or not prop or not val or _DROP_PROP.match(prop):
            continue
        # Guard against a value breaking out of the injected <style>.
        if "<" in val or "}" in val:
            continue
        keep.append(f"{prop}: {val}")
    return "; ".join(keep)


def _translate_selector(sel: str, scope: str) -> str:
    if not sel:
        return ""

    # Pull off one sub-control (`::item`) ...
    sub_control = ""
    unmapped_sub = False

    def _take_sub(m: re.Match) -> str:
        nonlocal sub_control, unmapped_sub
        name = m.group(1)
        if name in _SUBCONTROL:
            mapped = _SUBCONTROL[name]
            if mapped is None:
                unmapped_sub = True
            else:
                sub_control = mapped
        else:
            unmapped_sub = True
        return ""

    sel = _SUB_RE.sub(_take_sub, sel)
    if unmapped_sub:
        return ""  # a control we don't model -> skip rather than mis-target

    # ... and any pseudo-states.
    pseudo_parts: list[str] = []

    def _take_pseudo(m: re.Match) -> str:
        mapped = _PSEUDO.get(m.group(1))
        if mapped:
            pseudo_parts.append(mapped)
        return ""

    sel = _PSEUDO_RE.sub(_take_pseudo, sel).strip()
    pseudo = "".join(pseudo_parts)

    parts = sel.split()
    compiled = [_compile_compound(p) for p in parts]
    if any(c is None for c in compiled):
        return ""
    core = " ".join(compiled) or "*"

    if sub_control:
        return f"{scope} {core}{sub_control}{pseudo}"
    if len(parts) <= 1:
        # Single element: match the host itself and its descendants.
        return f"{scope}{core}{pseudo}, {scope} {core}{pseudo}"
    return f"{scope} {core}{pseudo}"


def _compile_compound(tok: str) -> str | None:
    if tok in (">", "*"):
        return tok
    out = ""
    m = _COMPOUND_ID.search(tok)
    if m:
        out += f"#{m.group(1)}"
        tok = tok.replace(m.group(0), "")
    m = _COMPOUND_ATTR.search(tok)
    if m:
        out += m.group(0)
        tok = tok.replace(m.group(0), "")
    m = _COMPOUND_NAME.search(tok)
    if m:
        out = f".{m.group(1).lower()}" + out
    return out or None
