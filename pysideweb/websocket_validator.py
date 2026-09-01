"""WebSocket message validation and rate limiting."""

import hashlib
import hmac
import time
from collections import defaultdict


class WebSocketValidator:
    """Validates WebSocket messages for integrity and rate limits."""
    
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key
        self.client_limits = defaultdict(lambda: {"count": 0, "reset_at": time.time() + 60})
        self.rate_limit_per_minute = 1000
    
    def validate_signature(self, message: str, signature: str) -> bool:
        """Verify HMAC-SHA256 signature of message."""
        if not self.secret_key:
            return True
        
        expected = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    
    def check_rate_limit(self, client_id: str) -> bool:
        """Check if client has exceeded rate limit."""
        now = time.time()
        limit_data = self.client_limits[client_id]
        
        if now > limit_data["reset_at"]:
            limit_data["count"] = 0
            limit_data["reset_at"] = now + 60
        
        if limit_data["count"] >= self.rate_limit_per_minute:
            return False
        
        limit_data["count"] += 1
        return True
    
    def validate_message(self, client_id: str, message: str, signature: str = None) -> tuple[bool, str]:
        """Validate message: signature + rate limit."""
        if signature and not self.validate_signature(message, signature):
            return False, "Invalid signature"
        
        if not self.check_rate_limit(client_id):
            return False, "Rate limited"
        
        return True, "OK"
