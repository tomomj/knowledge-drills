import logging

from app.config import Settings

_APP_LOGGER_NAME = "app"
_APP_HANDLER_MARKER = "_knowledge_drills_app_handler"
_LOG_FORMAT = "%(levelname)s:%(name)s:%(message)s"


def configure_app_logging(settings: Settings) -> None:
    app_logger = logging.getLogger(_APP_LOGGER_NAME)
    app_logger.setLevel(_resolve_log_level(settings.log_level))
    app_logger.propagate = True

    if any(getattr(handler, _APP_HANDLER_MARKER, False) for handler in app_logger.handlers):
        return

    handler = logging.StreamHandler()
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    setattr(handler, _APP_HANDLER_MARKER, True)
    app_logger.addHandler(handler)


def _resolve_log_level(level_name: str) -> int:
    level = logging.getLevelName(level_name.upper())
    if isinstance(level, int):
        return level
    return logging.INFO
