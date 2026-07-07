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


def test_course_detail_update_revisions_and_diff_are_owner_scoped() -> None:
    app = create_app()

    with TestClient(app) as client:
        _set_current_user(client, "owner-1")
        course_id = client.post(
            "/api/courses",
            json={"title": "Owner 1 Course", "markdown": "# v1"},
        ).json()["courseId"]
        update = client.put(
            f"/api/courses/{course_id}",
            json={"title": "Owner 1 Course", "markdown": "# v2"},
        )
        assert update.status_code == 200

        detail = client.get(f"/api/courses/{course_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == course_id
        assert "ownerUserId" not in detail.json()

        revisions = client.get(f"/api/courses/{course_id}/revisions")
        diff = client.get(f"/api/courses/{course_id}/revisions/diff?from=1&to=2")
        assert revisions.status_code == 200
        assert diff.status_code == 200

        _set_current_user(client, "owner-2")
        blocked_detail = client.get(f"/api/courses/{course_id}")
        blocked_update = client.put(
            f"/api/courses/{course_id}",
            json={"title": "Hacked", "markdown": "# hacked"},
        )
        blocked_revisions = client.get(f"/api/courses/{course_id}/revisions")
        blocked_diff = client.get(f"/api/courses/{course_id}/revisions/diff?from=1&to=2")

        saved = client.app.state.course_repository.get(course_id)  # type: ignore[attr-defined]

    assert blocked_detail.status_code == 404
    assert blocked_update.status_code == 404
    assert blocked_revisions.status_code == 404
    assert blocked_diff.status_code == 404
    assert blocked_detail.json()["code"] == "course_not_found"
    assert blocked_update.json()["code"] == "course_not_found"
    assert blocked_revisions.json()["code"] == "course_not_found"
    assert blocked_diff.json()["code"] == "course_not_found"
    assert saved is not None
    assert saved.title == "Owner 1 Course"
    assert saved.markdown == "# v2"


def test_ownerless_course_detail_is_not_visible_to_authenticated_owner() -> None:
    app = create_app()

    with TestClient(app) as client:
        client.app.state.course_repository.create(  # type: ignore[attr-defined]
            Course(id="ownerless-course", title="Ownerless", markdown="# Body")
        )
        _set_current_user(client, "owner-1")

        response = client.get("/api/courses/ownerless-course")

    assert response.status_code == 404
    assert response.json()["code"] == "course_not_found"
