"""
pysideweb.security — XSS prevention via safe JSON encoding.
"""

import json
from html import escape


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that escapes HTML in string values to prevent XSS."""

    def encode(self, o):
        result = super().encode(o)
        # Escape HTML in final JSON string
        return escape(result)

    def iterencode(self, o, _one_shot=False):
        for chunk in super().iterencode(o, _one_shot):
            # Escape HTML in each chunk
            yield escape(chunk)

    def default(self, obj):
        # Handle custom types
        if hasattr(obj, '__dict__'):
            return self.default(obj.__dict__)
        return super().default(obj)
