import logging

from app.config import Settings
from app.logging_config import _APP_HANDLER_MARKER, configure_app_logging


def test_configure_app_logging_adds_idempotent_app_handler() -> None:
    logger = logging.getLogger("app")
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate

    try:
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
        logger.propagate = False

        configure_app_logging(Settings(log_level="DEBUG"))
        configure_app_logging(Settings(log_level="INFO"))

        marked_handlers = [
            handler
            for handler in logger.handlers
            if getattr(handler, _APP_HANDLER_MARKER, False)
        ]
        assert len(marked_handlers) == 1
        assert marked_handlers[0].formatter is not None
        assert logger.level == logging.INFO
        assert logger.propagate is True
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def test_configure_app_logging_falls_back_to_info_for_unknown_level() -> None:
    logger = logging.getLogger("app")
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate

    try:
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)

        configure_app_logging(Settings(log_level="unknown"))

        assert logger.level == logging.INFO
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)
        logger.setLevel(original_level)
        logger.propagate = original_propagate
