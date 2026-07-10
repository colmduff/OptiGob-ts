"""
logger
======

This module provides a simple logging interface for optigob_ts.

All logging in optigob_ts uses Python's standard logging module, which allows users
to control what messages they see and where they go (console, file, etc.).

Functions:
    get_logger: Get a logger instance for a specific optigob_ts module.
    configure_logging: Quick setup function for common logging configurations.

Example:
    >>> from optigob_ts.common.logger import get_logger
    >>> logger = get_logger("my_module")
    >>> logger.info("This is an informational message")
    >>> logger.warning("This is a warning")
"""

import logging
import sys


def get_logger(name=None):
    """
    Get a logger instance for optigob_ts.

    This function returns a logger that is part of the 'optigob_ts' logging hierarchy.
    All optigob_ts loggers can be controlled together by configuring the root 'optigob_ts' logger.

    Args:
        name (str, optional): Name of the module/component requesting the logger.
                             If provided, logger will be named "optigob_ts.{name}".
                             If None, returns the root "optigob_ts" logger.

    Returns:
        logging.Logger: A logger instance that can be used to log messages.

    Example:
        >>> logger = get_logger("data_manager")
        >>> logger.info("Loading data...")
        >>> logger.warning("Parameter validation issue detected")

    Note:
        By default, if no configuration has been done, Python's logging will only
        show WARNING level and above. Call configure_logging() to see INFO and DEBUG.
    """
    logger_name = f"optigob_ts.{name}" if name else "optigob_ts"
    return logging.getLogger(logger_name)


def configure_logging(level=logging.INFO,
                     log_to_file=None,
                     format_style="detailed"):
    """
    Configure logging for optigob_ts with sensible defaults.

    This is a convenience function for common logging setups. Users can call this
    at the start of their script to control what optigob_ts logs.

    Args:
        level (int): Minimum logging level to display. Options:
                    - logging.DEBUG (most verbose - shows everything)
                    - logging.INFO (normal - shows general info)
                    - logging.WARNING (quiet - only warnings and errors)
                    - logging.ERROR (very quiet - only errors)
                    Default: logging.INFO

        log_to_file (str, optional): If provided, logs will be written to this file
                                     in addition to the console. If None, logs only
                                     go to console. Default: None

        format_style (str): How detailed the log messages should be. Options:
                          - "simple": Just the message
                          - "detailed": Time, module name, level, and message
                          Default: "detailed"

    Returns:
        None

    Example:
        >>> # Show all INFO and above messages
        >>> configure_logging(level=logging.INFO)

        >>> # Only show warnings and errors
        >>> configure_logging(level=logging.WARNING)

        >>> # Log everything to a file
        >>> configure_logging(level=logging.DEBUG, log_to_file="optigob_ts.log")

    Note:
        This function configures the root 'optigob_ts' logger. If you need more
        advanced control, use Python's logging module directly.
    """
    # Choose format based on user preference
    if format_style == "simple":
        log_format = '%(message)s'
    else:  # detailed
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Get the root optigob_ts logger
    logger = logging.getLogger("optigob_ts")
    logger.setLevel(level)

    # Remove any existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create console handler (writes to terminal/notebook)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # If user wants file logging, add a file handler
    if log_to_file:
        file_handler = logging.FileHandler(log_to_file, mode='a')
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            log_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # Prevent propagation to root logger (avoids duplicate messages)
    logger.propagate = False

    logger.debug(f"Logging configured: level={logging.getLevelName(level)}, file={log_to_file}")
