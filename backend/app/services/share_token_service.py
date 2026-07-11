import secrets
from collections.abc import Callable
from datetime import UTC, datetime

from app.repositories.firestore_client import DocumentAlreadyExists
from app.repositories.repositories import DrillRepository, ShareTokenRepository
from app.schemas import DrillRun, DrillRunStatus

DEFAULT_TOKEN_BYTES = 32
MAX_TOKEN_RESERVATION_ATTEMPTS = 3


class ShareTokenReservationError(Exception):
    pass


def generate_share_token() -> str:
    return secrets.token_urlsafe(DEFAULT_TOKEN_BYTES)


class ShareTokenService:
    def __init__(
        self,
        *,
        drill_repository: DrillRepository,
        share_token_repository: ShareTokenRepository,
        token_generator: Callable[[], str] = generate_share_token,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._drill_repository = drill_repository
        self._share_token_repository = share_token_repository
        self._token_generator = token_generator
        self._now = now or _utc_now

    def create_drill_run_with_reserved_token(
        self,
        drill_run: DrillRun,
        *,
        existing_token: str | None = None,
    ) -> str:
        if existing_token is not None:
            self._drill_repository.create(
                drill_run.model_copy(update={"share_token": existing_token})
            )
            return existing_token

        for _attempt in range(MAX_TOKEN_RESERVATION_ATTEMPTS):
            token = self._token_generator()
            try:
                return self._reserve_once(drill_run, token)
            except DocumentAlreadyExists:
                continue

        failed_drill_run = drill_run.model_copy(
            update={
                "status": DrillRunStatus.FAILED,
                "error_message": "share token reservation failed",
            }
        )
        self._drill_repository.create(failed_drill_run)
        raise ShareTokenReservationError("share token reservation failed")

    def _reserve_once(self, drill_run: DrillRun, token: str) -> str:
        def reserve_and_create() -> None:
            self._share_token_repository.reserve(
                token,
                drill_run_id=drill_run.id,
                course_id=drill_run.course_id,
                created_at=self._now(),
            )
            self._drill_repository.create(drill_run.model_copy(update={"share_token": token}))

        self._share_token_repository.run_transaction(reserve_and_create)
        return token

    def publish(self, drill_run: DrillRun) -> None:
        if drill_run.share_token is None:
            raise ValueError("published drill run requires a share token")
        share_token = drill_run.share_token

        def point_to_ready_drill() -> None:
            self._share_token_repository.point_to_drill(
                share_token,
                drill_run.id,
                drill_run.course_id,
            )
            self._drill_repository.update(drill_run)

        self._share_token_repository.run_transaction(point_to_ready_drill)

    def close(self, token: str) -> None:
        self._share_token_repository.close(token, self._now())

    def reopen(self, token: str) -> None:
        self._share_token_repository.reopen(token)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
