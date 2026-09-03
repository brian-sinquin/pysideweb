"""Conservative policy for the supported QSS subset, not a general CSS parser.

Reject an entire sheet with at-rules, resource URLs, escapes, HTML delimiters,
or legacy executable CSS. This deliberately disallows external CSS resources.
Application Python code remains trusted; this is not a sandbox for that code.
"""

import re


class QSSSanitizer:
    _comments = re.compile(r"/\*.*?\*/", re.DOTALL)
    _unsafe = re.compile(
        r"[@\\<>]|url\s*\(|expression\s*\(|javascript\s*:|"
        r"(?:-moz-)?binding\s*:|behavior\s*:", re.IGNORECASE,
    )

    @classmethod
    def sanitize(cls, qss: str) -> str:
        normalized = cls._comments.sub("", qss or "")
        if cls._unsafe.search(normalized) or "/*" in normalized:
            return ""
        return qss or ""

    @classmethod
    def is_safe(cls, qss: str) -> bool:
        return qss == cls.sanitize(qss)
