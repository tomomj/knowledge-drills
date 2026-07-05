import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger("app.request")

RESOURCE_PARAM_NAMES = {
    "courseId",
    "course_id",
    "drillRunId",
    "drill_run_id",
    "answerId",
    "answer_id",
    "patchId",
    "patch_id",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id
        start = perf_counter()

        response = await call_next(request)

        elapsed_ms = round((perf_counter() - start) * 1000, 2)
        resource_ids = {
            key: value
            for key, value in request.path_params.items()
            if key in RESOURCE_PARAM_NAMES
        }
        response.headers["x-request-id"] = request_id
        logger.info(
            "request completed method=%s path=%s status_code=%s request_id=%s "
            "duration_ms=%s resources=%s",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            elapsed_ms,
            resource_ids,
        )
        return response
