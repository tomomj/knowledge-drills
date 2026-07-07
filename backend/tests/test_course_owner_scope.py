from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, set_auth_client
from app.config import get_settings
from app.main import create_app
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import CourseRepository
from app.schemas import Course


class StaticAuthClient:
    def __init__(self, uid: str) -> None:
        self._uid = uid

    def verify_authorization_header(self, authorization: str | None) -> AuthenticatedUser:
        return AuthenticatedUser(uid=self._uid, email=f"{self._uid}@example.test")


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _set_current_user(client: TestClient, uid: str) -> None:
    set_auth_client(client.app, StaticAuthClient(uid))  # type: ignore[arg-type]


def test_course_repository_lists_courses_by_owner_and_reads_ownerless_courses() -> None:
    repository = CourseRepository(InMemoryFirestoreClient())
    repository.create(
        Course(id="owner-1-course", owner_user_id="owner-1", title="Owner 1", markdown="# A")
    )
    repository.create(
        Course(id="owner-2-course", owner_user_id="owner-2", title="Owner 2", markdown="# B")
    )
    repository.create(Course(id="ownerless-course", title="Ownerless", markdown="# C"))

    owner_courses = repository.list_by_owner("owner-1")
    ownerless = repository.get("ownerless-course")

    assert [course.id for course in owner_courses] == ["owner-1-course"]
    assert ownerless is not None
    assert ownerless.owner_user_id is None


def test_course_create_uses_current_user_uid_and_ignores_request_owner_user_id() -> None:
    app = create_app()

    with TestClient(app) as client:
        _set_current_user(client, "owner-1")
        response = client.post(
            "/api/courses",
            json={
                "title": "講座",
                "markdown": "# Body",
                "ownerUserId": "attacker-owner",
            },
        )

        course_id = response.json()["courseId"]
        saved = client.app.state.course_repository.get(course_id)  # type: ignore[attr-defined]

    assert response.status_code == 201
    assert saved is not None
    assert saved.owner_user_id == "owner-1"


def test_course_list_returns_only_current_owner_courses() -> None:
    app = create_app()

    with TestClient(app) as client:
        _set_current_user(client, "owner-1")
        owner_1_course_id = client.post(
            "/api/courses",
            json={"title": "Owner 1 Course", "markdown": "# A"},
        ).json()["courseId"]

        _set_current_user(client, "owner-2")
        client.post(
            "/api/courses",
            json={"title": "Owner 2 Course", "markdown": "# B"},
        )

        client.app.state.course_repository.create(  # type: ignore[attr-defined]
            Course(id="ownerless-course", title="Ownerless", markdown="# C")
        )

        _set_current_user(client, "owner-1")
        response = client.get("/api/courses")

    assert response.status_code == 200
    courses = response.json()["courses"]
    assert len(courses) == 1
    assert courses[0]["id"] == owner_1_course_id
    assert courses[0]["title"] == "Owner 1 Course"
    assert courses[0]["version"] == 1
    assert courses[0]["updatedAt"] is not None
    assert courses[0]["answerCount"] == 0
    assert "ownerUserId" not in courses[0]
