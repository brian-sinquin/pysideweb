"""JSON encoding that preserves values and remains safe to embed in HTML.

DOM consumers must still use textContent or a rich-text sanitizer. Encoding
alone cannot make an arbitrary HTML string safe for innerHTML.
"""

import json


class SafeJSONEncoder(json.JSONEncoder):
    """Escape HTML delimiters as JSON Unicode escapes, never HTML entities."""

    def iterencode(self, o, _one_shot=False):
        for chunk in super().iterencode(o, _one_shot):
            for char, replacement in (("&", "\\u0026"), ("<", "\\u003c"),
                                      (">", "\\u003e"), ("\u2028", "\\u2028"),
                                      ("\u2029", "\\u2029")):
                chunk = chunk.replace(char, replacement)
            yield chunk

    def encode(self, o):
        # JSONEncoder.encode special-cases strings, bypassing iterencode.
        return "".join(self.iterencode(o, _one_shot=True))
