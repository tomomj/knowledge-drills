from collections.abc import Callable
from datetime import UTC, datetime

from app.auth import AuthenticatedUser
from app.repositories.user_repository import UserRepository
from app.schemas import UserProfile


class UserService:
    def __init__(
        self,
        user_repository: UserRepository,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._user_repository = user_repository
        self._clock = clock or _utc_now

    def upsert_current_user(self, user: AuthenticatedUser) -> UserProfile:
        now = self._clock()
        existing = self._user_repository.get(user.uid)
        profile = UserProfile(
            uid=user.uid,
            email=user.email,
            display_name=user.display_name,
            photo_url=user.photo_url,
            created_at=existing.created_at if existing is not None else now,
            last_login_at=now,
        )
        self._user_repository.upsert(profile)
        return profile


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
