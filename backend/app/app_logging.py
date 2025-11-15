"""
Structured logging for the application.
"""
import logging
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional
import os

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)
        
        return json.dumps(log_data)

def setup_logging(log_level: str = "INFO"):
    """Setup structured logging for the application."""
    logger = logging.getLogger("chrysalis")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Remove existing handlers
    logger.handlers = []
    
    # Console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)
    
    # File handler (optional)
    log_file = os.getenv("LOG_FILE")
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
    
    return logger

def get_logger(name: str = "chrysalis") -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)

def log_ingest(logger: logging.Logger, source_id: str, file_id: str, file_type: str, fragments: Dict[str, Any]):
    """Log file ingestion."""
    logger.info(
        "File ingested",
        extra={
            "extra_fields": {
                "event_type": "ingest",
                "source_id": source_id,
                "file_id": file_id,
                "file_type": file_type,
                "fragments": fragments
            }
        }
    )

def log_schema_generation(logger: logging.Logger, source_id: str, schema_id: str, version: int, field_count: int):
    """Log schema generation."""
    logger.info(
        "Schema generated",
        extra={
            "extra_fields": {
                "event_type": "schema_generation",
                "source_id": source_id,
                "schema_id": schema_id,
                "version": version,
                "field_count": field_count
            }
        }
    )

def log_schema_evolution(logger: logging.Logger, source_id: str, from_version: int, to_version: int, diff: Dict[str, Any]):
    """Log schema evolution."""
    logger.info(
        "Schema evolved",
        extra={
            "extra_fields": {
                "event_type": "schema_evolution",
                "source_id": source_id,
                "from_version": from_version,
                "to_version": to_version,
                "diff_summary": {
                    "added": len(diff.get("added", {})),
                    "removed": len(diff.get("removed", {})),
                    "changed": len(diff.get("changed", {}))
                }
            }
        }
    )

def log_query_execution(logger: logging.Logger, source_id: str, query_type: str, db_type: str, result_count: int, execution_time_ms: float):
    """Log query execution."""
    logger.info(
        "Query executed",
        extra={
            "extra_fields": {
                "event_type": "query_execution",
                "source_id": source_id,
                "query_type": query_type,
                "db_type": db_type,
                "result_count": result_count,
                "execution_time_ms": execution_time_ms
            }
        }
    )

def log_error(logger: logging.Logger, error_type: str, message: str, context: Optional[Dict[str, Any]] = None):
    """Log error with context."""
    logger.error(
        message,
        extra={
            "extra_fields": {
                "event_type": "error",
                "error_type": error_type,
                "context": context or {}
            }
        }
    )

def log_security_event(logger: logging.Logger, event_type: str, details: Dict[str, Any]):
    """Log security-related events."""
    logger.warning(
        "Security event",
        extra={
            "extra_fields": {
                "event_type": "security",
                "security_event_type": event_type,
                "details": details
            }
        }
    )

