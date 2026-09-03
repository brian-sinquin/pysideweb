"""Validation helpers used at the WebSocket boundary."""

import hashlib
import hmac
import time


class WebSocketValidator:
    """Fixed-window limits; use one instance per connection and release on close.

    HMAC is available to callers with a shared secret, but the browser protocol
    does not use it. An absent signature never bypasses a configured secret.
    """

    def __init__(self, secret_key: str | None = None):
        self.secret_key = secret_key
        self.client_limits = {}
        self.rate_limit_per_minute = 1000

    def validate_signature(self, message: str, signature: str | None) -> bool:
        if not self.secret_key:
            return True
        if not isinstance(signature, str):
            return False
        expected = hmac.new(self.secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected.encode("ascii"), signature.encode("utf-8"))

    def check_rate_limit(self, client_id: str) -> bool:
        now = time.monotonic()
        count, reset_at = self.client_limits.get(client_id, (0, now + 60))
        if now >= reset_at:
            count, reset_at = 0, now + 60
        if count >= self.rate_limit_per_minute:
            return False
        self.client_limits[client_id] = (count + 1, reset_at)
        return True

    def validate_message(self, client_id: str, message: str,
                         signature: str | None = None) -> tuple[bool, str]:
        if not self.check_rate_limit(client_id):
            return False, "Rate limited"
        if not self.validate_signature(message, signature):
            return False, "Invalid signature"
        return True, "OK"

    @staticmethod
    def validate_event(event) -> bool:
        return (
            isinstance(event, dict)
            and isinstance(event.get("id"), str)
            and 0 < len(event["id"]) <= 128
            and isinstance(event.get("event"), str)
            and 0 < len(event["event"]) <= 128
            and not (event.keys() - {"id", "event", "value"})
        )
