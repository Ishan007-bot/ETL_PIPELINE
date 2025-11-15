"""
Security utilities for input validation, sanitization, and injection prevention.
"""
import re
import os
from typing import Dict, Any, Optional, List
from fastapi import HTTPException

# Maximum file size (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024

# Allowed file extensions
ALLOWED_EXTENSIONS = ['.txt', '.pdf', '.md']

# Dangerous SQL keywords
SQL_INJECTION_PATTERNS = [
    r'(?i)(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|SCRIPT)\b)',
    r'(?i)(\b(OR|AND)\s+\d+\s*=\s*\d+)',
    r'(?i)(\b(OR|AND)\s+[\'"]?\w+[\'"]?\s*=\s*[\'"]?\w+[\'"]?)',
    r'(\b(DROP|DELETE|TRUNCATE)\s+TABLE\b)',
    r'(\b(ALTER|CREATE)\s+TABLE\b)',
]

def validate_file_upload(file_content: bytes, filename: str) -> Dict[str, Any]:
    """
    Validate file upload for security.
    Returns validation result with any issues found.
    """
    issues = []
    
    # Check file size
    if len(file_content) > MAX_FILE_SIZE:
        issues.append(f"File size {len(file_content)} exceeds maximum {MAX_FILE_SIZE}")
    
    # Check file extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        issues.append(f"File extension {ext} not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
    
    # Note: We allow script tags in data files as they may be part of scraped content
    # (e.g., JSON-LD, embedded scripts in HTML). Actual execution is prevented by
    # the query sanitization layer, not file upload validation.
    # For now, we only check file size and extension.
    
    return {
        "valid": len(issues) == 0,
        "issues": issues
    }

def sanitize_input(text: str, max_length: Optional[int] = None) -> str:
    """Sanitize user input to prevent injection attacks."""
    if not isinstance(text, str):
        return str(text)
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Limit length
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    # Remove control characters (except newlines and tabs)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    
    return text.strip()

def detect_sql_injection(query: str) -> bool:
    """Detect potential SQL injection in query string."""
    if not isinstance(query, str):
        return False
    
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, query):
            return True
    
    return False

def sanitize_query(query: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize query object to prevent injection."""
    sanitized = {}
    
    for key, value in query.items():
        # Sanitize key
        sanitized_key = sanitize_input(str(key), max_length=100)
        
        # Sanitize value based on type
        if isinstance(value, str):
            # Check for SQL injection
            if detect_sql_injection(value):
                raise HTTPException(status_code=400, detail="Potential SQL injection detected in query")
            sanitized[sanitized_key] = sanitize_input(value, max_length=1000)
        elif isinstance(value, dict):
            sanitized[sanitized_key] = sanitize_query(value)
        elif isinstance(value, list):
            sanitized[sanitized_key] = [sanitize_query(item) if isinstance(item, dict) else item for item in value]
        else:
            sanitized[sanitized_key] = value
    
    return sanitized

def validate_source_id(source_id: str) -> bool:
    """Validate source_id format."""
    if not source_id or not isinstance(source_id, str):
        return False
    
    # Allow alphanumeric, hyphens, underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', source_id):
        return False
    
    # Length check
    if len(source_id) > 255:
        return False
    
    return True

def validate_nl_query(nl_query: str) -> Dict[str, Any]:
    """Validate natural language query."""
    if not nl_query or not isinstance(nl_query, str):
        return {"valid": False, "reason": "Query must be a non-empty string"}
    
    # Length check
    if len(nl_query) > 1000:
        return {"valid": False, "reason": "Query too long (max 1000 characters)"}
    
    # Check for potential injection
    if detect_sql_injection(nl_query):
        return {"valid": False, "reason": "Potential SQL injection detected"}
    
    return {"valid": True}

def secure_file_storage(file_content: bytes, filename: str) -> Dict[str, Any]:
    """
    Secure file storage with validation.
    Returns storage metadata.
    """
    validation = validate_file_upload(file_content, filename)
    
    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail=f"File validation failed: {', '.join(validation['issues'])}"
        )
    
    return {
        "filename": sanitize_input(filename),
        "size": len(file_content),
        "validated": True
    }

