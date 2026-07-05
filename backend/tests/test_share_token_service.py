import pytest

from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import DrillRepository, ShareTokenRepository
from app.schemas import DrillRun, DrillRunStatus
from app.services.share_token_service import ShareTokenReservationError, ShareTokenService


def test_reserve_share_token_retries_collision_and_creates_drill_run_in_transaction() -> None:
    client = InMemoryFirestoreClient()
    drill_repository = DrillRepository(client)
    token_repository = ShareTokenRepository(client)
    service = ShareTokenService(
        drill_repository=drill_repository,
        share_token_repository=token_repository,
        token_generator=iter(["taken-token", "unique-token"]).__next__,
    )
    token_repository.reserve("taken-token", drill_run_id="other-drill")

    token = service.create_drill_run_with_reserved_token(
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.GENERATING)
    )

    drill_run = drill_repository.get("drill-1")
    assert token == "unique-token"
    assert token_repository.get_drill_run_id("unique-token") == "drill-1"
    assert drill_run is not None
    assert drill_run.share_token == "unique-token"
    assert client.transaction_count == 2


def test_reserve_share_token_marks_drill_failed_after_three_collisions() -> None:
    client = InMemoryFirestoreClient()
    drill_repository = DrillRepository(client)
    token_repository = ShareTokenRepository(client)
    for index in range(3):
        token_repository.reserve(f"taken-{index}", drill_run_id=f"other-{index}")
    service = ShareTokenService(
        drill_repository=drill_repository,
        share_token_repository=token_repository,
        token_generator=iter(["taken-0", "taken-1", "taken-2"]).__next__,
    )

    with pytest.raises(ShareTokenReservationError):
        service.create_drill_run_with_reserved_token(
            DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.GENERATING)
        )

    drill_run = drill_repository.get("drill-1")
    assert drill_run is not None
    assert drill_run.status == "failed"
    assert drill_run.error_message == "share token reservation failed"
