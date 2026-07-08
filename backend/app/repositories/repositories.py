from __future__ import annotations

from collections.abc import Callable

from app.repositories.firestore_client import FirestoreClient
from app.schemas import (
    AnswerStatus,
    AnswerSubmission,
    Course,
    CourseRevision,
    DocumentPatch,
    DrillRun,
    DrillRunStatus,
    PatchStatus,
)


class CourseRepository:
    collection = "courses"
    revision_collection = "course_revisions"

    def __init__(self, client: FirestoreClient) -> None:
        self._client = client

    def create(self, course: Course) -> None:
        self._client.create_document(
            self.collection,
            course.id,
            course.model_dump(mode="json", by_alias=True),
        )
        self._record_revision(course)

    def get(self, course_id: str) -> Course | None:
        document = self._client.get_document(self.collection, course_id)
        if document is None:
            return None
        return Course.model_validate(document)

    def list_all(self) -> list[Course]:
        return [
            Course.model_validate(document)
            for document in self._client.list_documents(self.collection)
        ]

    def list_by_owner(self, owner_user_id: str) -> list[Course]:
        return [
            Course.model_validate(document)
            for document in self._client.list_documents_by_field(
                self.collection,
                "ownerUserId",
                owner_user_id,
            )
        ]

    def update(self, course: Course) -> None:
        self._client.set_document(
            self.collection,
            course.id,
            course.model_dump(mode="json", by_alias=True),
        )
        self._record_revision(course)

    def update_summary(
        self,
        course_id: str,
        *,
        latest_drill_run_id: str | None = None,
        latest_drill_status: DrillRunStatus | None = None,
        answer_count: int | None = None,
        latest_patch_id: str | None = None,
        latest_patch_status: PatchStatus | None = None,
    ) -> None:
        data: dict[str, object] = {}
        if latest_drill_run_id is not None:
            data["latestDrillRunId"] = latest_drill_run_id
        if latest_drill_status is not None:
            data["latestDrillStatus"] = latest_drill_status.value
        if answer_count is not None:
            data["answerCount"] = answer_count
        if latest_patch_id is not None:
            data["latestPatchId"] = latest_patch_id
        if latest_patch_status is not None:
            data["latestPatchStatus"] = latest_patch_status.value
        if data:
            self._client.update_document(self.collection, course_id, data)

    def increment_answer_count(self, course_id: str) -> None:
        course = self.get(course_id)
        if course is None:
            return
        self.update_summary(course_id, answer_count=course.answer_count + 1)

    def list_revisions(self, course_id: str) -> list[CourseRevision]:
        return [
            CourseRevision.model_validate(document)
            for document in self._client.list_documents_by_field(
                self.revision_collection,
                "courseId",
                course_id,
            )
        ]

    def get_revision(self, course_id: str, version: int) -> CourseRevision | None:
        document = self._client.get_document(
            self.revision_collection,
            f"{course_id}:{version}",
        )
        if document is None:
            return None
        return CourseRevision.model_validate(document)

    def _record_revision(self, course: Course) -> None:
        revision = CourseRevision(
            course_id=course.id,
            version=course.version,
            title=course.title,
            markdown=course.markdown,
            drill_focus=course.drill_focus,
            updated_at=course.updated_at,
        )
        self._client.set_document(
            self.revision_collection,
            f"{course.id}:{course.version}",
            revision.model_dump(mode="json", by_alias=True),
        )


class DrillRepository:
    collection = "drill_runs"

    def __init__(self, client: FirestoreClient) -> None:
        self._client = client

    def create(self, drill_run: DrillRun) -> None:
        self._client.create_document(
            self.collection,
            drill_run.id,
            drill_run.model_dump(mode="json", by_alias=True),
        )

    def get(self, drill_run_id: str) -> DrillRun | None:
        document = self._client.get_document(self.collection, drill_run_id)
        if document is None:
            return None
        return DrillRun.model_validate(document)

    def update_status(self, drill_run_id: str, status: DrillRunStatus) -> None:
        self._client.update_document(self.collection, drill_run_id, {"status": status.value})

    def update(self, drill_run: DrillRun) -> None:
        self._client.set_document(
            self.collection,
            drill_run.id,
            drill_run.model_dump(mode="json", by_alias=True),
        )

    def list_by_course(self, course_id: str) -> list[DrillRun]:
        return [
            DrillRun.model_validate(document)
            for document in self._client.list_documents_by_field(
                self.collection,
                "courseId",
                course_id,
            )
        ]


class ShareTokenRepository:
    collection = "share_tokens"

    def __init__(self, client: FirestoreClient) -> None:
        self._client = client

    def reserve(self, token: str, drill_run_id: str) -> None:
        self._client.create_document(
            self.collection,
            token,
            {"token": token, "drillRunId": drill_run_id},
        )

    def get_drill_run_id(self, token: str) -> str | None:
        document = self._client.get_document(self.collection, token)
        if document is None:
            return None
        value = document.get("drillRunId")
        if not isinstance(value, str):
            return None
        return value

    def run_transaction(self, callback: Callable[[], object]) -> object:
        return self._client.run_transaction(callback)


class AnswerRepository:
    collection = "answers"

    def __init__(self, client: FirestoreClient) -> None:
        self._client = client

    def create(
        self,
        *,
        id: str,
        drill_run_id: str,
        learner_name: str,
        status: AnswerStatus,
        answers: dict[str, str],
    ) -> None:
        answer = AnswerSubmission(
            id=id,
            drill_run_id=drill_run_id,
            learner_name=learner_name,
            status=status,
            answers=answers,
        )
        self._client.create_document(
            self.collection,
            id,
            answer.model_dump(mode="json", by_alias=True),
        )

    def create_submission(self, answer: AnswerSubmission) -> None:
        self._client.create_document(
            self.collection,
            answer.id,
            answer.model_dump(mode="json", by_alias=True),
        )

    def get(self, answer_id: str) -> AnswerSubmission | None:
        document = self._client.get_document(self.collection, answer_id)
        if document is None:
            return None
        return AnswerSubmission.model_validate(document)

    def list_by_drill_run(self, drill_run_id: str) -> list[AnswerSubmission]:
        return [
            AnswerSubmission.model_validate(document)
            for document in self._client.list_documents_by_field(
                self.collection,
                "drillRunId",
                drill_run_id,
            )
        ]

    def update_status(self, answer_id: str, status: AnswerStatus) -> None:
        self._client.update_document(self.collection, answer_id, {"status": status.value})

    def update(self, answer: AnswerSubmission) -> None:
        self._client.set_document(
            self.collection,
            answer.id,
            answer.model_dump(mode="json", by_alias=True),
        )


class PatchRepository:
    collection = "patches"

    def __init__(self, client: FirestoreClient) -> None:
        self._client = client

    def create(self, patch: DocumentPatch) -> None:
        self._client.create_document(
            self.collection,
            patch.id,
            patch.model_dump(mode="json", by_alias=True),
        )

    def get(self, patch_id: str) -> DocumentPatch | None:
        document = self._client.get_document(self.collection, patch_id)
        if document is None:
            return None
        return DocumentPatch.model_validate(document)

    def update_status(self, patch_id: str, status: PatchStatus) -> None:
        self._client.update_document(self.collection, patch_id, {"status": status.value})

    def update(self, patch: DocumentPatch) -> None:
        self._client.set_document(
            self.collection,
            patch.id,
            patch.model_dump(mode="json", by_alias=True),
        )
