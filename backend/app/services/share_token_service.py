import secrets
from collections.abc import Callable

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
    ) -> None:
        self._drill_repository = drill_repository
        self._share_token_repository = share_token_repository
        self._token_generator = token_generator

    def create_drill_run_with_reserved_token(self, drill_run: DrillRun) -> str:
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
            self._share_token_repository.reserve(token, drill_run_id=drill_run.id)
            self._drill_repository.create(drill_run.model_copy(update={"share_token": token}))

        self._share_token_repository.run_transaction(reserve_and_create)
        return token
