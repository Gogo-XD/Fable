"""
Logging configuration for the Fable API.
"""

import logging
import sys


def setup_logging() -> logging.Logger:
    """
    Configure application logging.

    :return: Root logger for the worldbuilding application
    :rtype: logging.Logger
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    return logging.getLogger('worldbuilding')


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    :param name: The module name for the logger
    :type name: str
    :return: Logger instance for the specified module
    :rtype: logging.Logger
    """
    return logging.getLogger(f'worldbuilding.{name}')
