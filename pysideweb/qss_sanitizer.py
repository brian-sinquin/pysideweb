"""QSS/CSS sanitization to prevent injection attacks."""

import re


class QSSSanitizer:
    """Sanitize Qt Style Sheets to prevent injection."""
    
    DANGEROUS_DIRECTIVES = {
        r'@import', r'@font-face', r'@keyframes',
        r'@media', r'expression\(', r'javascript:',
        r'behavior:', r'binding:'
    }
    
    @classmethod
    def sanitize(cls, qss: str) -> str:
        """Remove dangerous directives from QSS."""
        lines = qss.split('\n')
        safe_lines = []
        
        for line in lines:
            # Check for dangerous patterns
            is_dangerous = any(
                re.search(pattern, line, re.IGNORECASE)
                for pattern in cls.DANGEROUS_DIRECTIVES
            )
            
            if not is_dangerous:
                safe_lines.append(line)
        
        return '\n'.join(safe_lines)
    
    @classmethod
    def is_safe(cls, qss: str) -> bool:
        """Check if QSS is safe without modification."""
        return qss == cls.sanitize(qss)
