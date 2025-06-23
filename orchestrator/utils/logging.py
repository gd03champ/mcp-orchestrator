"""Logging utilities for MCP Docker Orchestrator."""

import json
import logging
import sys
from datetime import datetime

class JsonFormatter(logging.Formatter):
    """Format logs as JSON objects."""

    def format(self, record):
        """Format log record as JSON."""
        log_object = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }

        # Add any extra attributes
        for key, value in record.__dict__.items():
            if key not in ["args", "asctime", "created", "exc_info", "exc_text", 
                          "filename", "funcName", "id", "levelname", "levelno", 
                          "lineno", "module", "msecs", "message", "msg", 
                          "name", "pathname", "process", "processName", 
                          "relativeCreated", "stack_info", "thread", "threadName"]:
                log_object[key] = value

        # Add exception info if available
        if record.exc_info:
            log_object["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_object)


def setup_logging(name="mcp-orchestrator", level=logging.INFO):
    """Set up structured logging for the application."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(JsonFormatter())

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger
