import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.clients.agent_runtime_client import AgentInvocationError
from app.schemas import ErrorResponse

logger = logging.getLogger("app.error")


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        current_status: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.current_status = current_status


def register_exception_handlers(app: FastAPI) -> None:
    def error_content(
        code: str,
        message: str,
        request: Request,
        current_status: str | None = None,
    ) -> dict[str, str]:
        request_id = getattr(request.state, "request_id", "unknown")
        return ErrorResponse(
            code=code,
            message=message,
            requestId=request_id,
            current_status=current_status,
        ).model_dump(by_alias=True, exclude_none=True)

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_content(exc.code, exc.message, _request, exc.current_status),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.info(
            "request validation failed request_id=%s path=%s error_count=%s",
            getattr(request.state, "request_id", "unknown"),
            request.url.path,
            len(exc.errors()),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_content(
                "validation_error",
                "Request validation failed.",
                request,
            ),
        )

    @app.exception_handler(AgentInvocationError)
    async def agent_invocation_error_handler(
        request: Request,
        _exc: AgentInvocationError,
    ) -> JSONResponse:
        logger.info(
            "agent invocation failed request_id=%s path=%s error_type=%s",
            getattr(request.state, "request_id", "unknown"),
            request.url.path,
            AgentInvocationError.__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=error_content(
                "agent_invocation_failed",
                "Agent invocation failed.",
                request,
            ),
        )

    @app.exception_handler(Exception)
    async def system_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled system error request_id=%s path=%s",
            getattr(request.state, "request_id", "unknown"),
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_content(
                "internal_server_error",
                "An unexpected error occurred.",
                request,
            ),
        )
