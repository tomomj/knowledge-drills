from __future__ import annotations

from collections.abc import Callable

from app.analysis_policy import is_scored_answer
from app.errors import AppError
from app.repositories.firestore_client import DocumentNotFound, FirestoreClient
from app.schemas import (
    AnalysisClaim,
    AnalysisOrigin,
    AnalysisStepStatus,
    AnalysisTimelineItem,
    AnswerStatus,
    AnswerSubmission,
    Course,
    CourseRevision,
    CourseScoreTrendPoint,
    DocumentPatch,
    DrillRun,
    DrillRunStatus,
    PatchStatus,
    ShareToken,
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
        score_trend: list[CourseScoreTrendPoint] | None = None,
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
        if score_trend is not None:
            data["scoreTrend"] = [
                point.model_dump(mode="json", by_alias=True) for point in score_trend
            ]
        if data:
            self._client.update_document(self.collection, course_id, data)

    def update_score_trend_point(
        self,
        course_id: str,
        point: CourseScoreTrendPoint,
    ) -> None:
        course = self.get(course_id)
        if course is None:
            return
        by_version = {existing.course_version: existing for existing in (course.score_trend or [])}
        by_version[point.course_version] = point
        score_trend = [by_version[version] for version in sorted(by_version)]
        self.update_summary(course_id, score_trend=score_trend)

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

    def delete_revision(self, course_id: str, version: int) -> None:
        self._client.delete_document(self.revision_collection, f"{course_id}:{version}")

    def delete(self, course_id: str) -> None:
        self._client.delete_document(self.collection, course_id)

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
        def update_document() -> None:
            incoming = drill_run.model_dump(mode="json", by_alias=True)
            current = self._client.get_document(self.collection, drill_run.id)
            if current is not None:
                current_count = current.get("analyzedAnswerCount")
                incoming_count = incoming.get("analyzedAnswerCount")
                if (
                    isinstance(current_count, int)
                    and not isinstance(current_count, bool)
                    and (
                        not isinstance(incoming_count, int)
                        or isinstance(incoming_count, bool)
                        or incoming_count < current_count
                    )
                ):
                    incoming["analyzedAnswerCount"] = current_count
            self._client.set_document(self.collection, drill_run.id, incoming)

        self._client.run_transaction(update_document)

    def initialize_analyzed_answer_count(self, drill_run_id: str, baseline: int) -> None:
        if baseline < 0:
            raise ValueError("baseline must be greater than or equal to zero")

        def initialize() -> None:
            document = self._client.get_document(self.collection, drill_run_id)
            if document is None:
                raise DocumentNotFound(f"{self.collection}/{drill_run_id} was not found")
            analyzed_answer_count = document.get("analyzedAnswerCount")
            has_recorded_count = isinstance(analyzed_answer_count, int) and not isinstance(
                analyzed_answer_count,
                bool,
            )
            if has_recorded_count or document.get("status") != DrillRunStatus.ANALYZED.value:
                return
            self._client.update_document(
                self.collection,
                drill_run_id,
                {"analyzedAnswerCount": baseline},
            )

        self._client.run_transaction(initialize)

    def list_by_course(self, course_id: str) -> list[DrillRun]:
        return [
            DrillRun.model_validate(document)
            for document in self._client.list_documents_by_field(
                self.collection,
                "courseId",
                course_id,
            )
        ]

    def delete(self, drill_run_id: str) -> None:
        self._client.delete_document(self.collection, drill_run_id)


_ANALYSIS_FAILED_MESSAGE = "analysis failed"
_ANALYSIS_STEPS: tuple[tuple[str, str], ...] = (
    ("collect_answers", "回答データを収集"),
    ("detect_failure_patterns", "つまずき箇所を特定"),
    ("match_course_evidence", "教材の根拠を照合"),
    ("decide_patch_strategy", "改善方針を判断"),
    ("create_patch", "修正案を作成"),
)


class AnalysisExecutionRepository:
    def __init__(self, client: FirestoreClient) -> None:
        self._client = client

    def claim_manual_analysis(
        self,
        drill_run_id: str,
        owner_user_id: str,
    ) -> AnalysisClaim:
        def claim() -> AnalysisClaim:
            drill_document = self._client.get_document(DrillRepository.collection, drill_run_id)
            if drill_document is None:
                raise AppError(
                    "drill_run_not_found",
                    "Drill run was not found.",
                    status_code=404,
                )
            drill_run = DrillRun.model_validate(drill_document)

            course_document = self._client.get_document(
                CourseRepository.collection,
                drill_run.course_id,
            )
            if course_document is None:
                raise AppError(
                    "drill_run_not_found",
                    "Drill run was not found.",
                    status_code=404,
                )
            course = Course.model_validate(course_document)
            if course.owner_user_id != owner_user_id:
                raise AppError(
                    "drill_run_not_found",
                    "Drill run was not found.",
                    status_code=404,
                )

            if (
                drill_run.status is DrillRunStatus.FAILED
                and drill_run.error_message != _ANALYSIS_FAILED_MESSAGE
            ) or drill_run.status not in {
                DrillRunStatus.READY,
                DrillRunStatus.ANALYZED,
                DrillRunStatus.FAILED,
            }:
                raise AppError(
                    "drill_not_analyzable",
                    "Drill run is not analyzable.",
                    status_code=409,
                )

            answers = [
                AnswerSubmission.model_validate(document)
                for document in self._client.list_documents_by_field(
                    AnswerRepository.collection,
                    "drillRunId",
                    drill_run.id,
                )
            ]
            graded_answers = [
                answer for answer in answers if answer.status is AnswerStatus.GRADED
            ]
            if not graded_answers:
                raise AppError(
                    "no_graded_answers",
                    "At least one graded answer is required.",
                )

            timeline = _initial_analysis_timeline()
            self._client.update_document(
                DrillRepository.collection,
                drill_run.id,
                {
                    "status": DrillRunStatus.ANALYZING.value,
                    "errorMessage": None,
                    "analysisTimeline": [
                        item.model_dump(mode="json", by_alias=True) for item in timeline
                    ],
                    "analysisOrigin": AnalysisOrigin.MANUAL.value,
                    "latestPatchId": None,
                },
            )
            self._client.update_document(
                CourseRepository.collection,
                course.id,
                {
                    "latestDrillRunId": drill_run.id,
                    "latestDrillStatus": DrillRunStatus.ANALYZING.value,
                    "answerCount": len(answers),
                },
            )
            return AnalysisClaim(
                course_id=course.id,
                drill_run_id=drill_run.id,
                owner_user_id=owner_user_id,
                course_version=course.version,
                answer_ids=tuple(answer.id for answer in graded_answers),
                snapshot_agent_answer_count=len(graded_answers),
                snapshot_scored_answer_count=sum(
                    is_scored_answer(answer) for answer in graded_answers
                ),
                origin=AnalysisOrigin.MANUAL,
            )

        return self._client.run_transaction(claim)


def _initial_analysis_timeline() -> list[AnalysisTimelineItem]:
    return [
        AnalysisTimelineItem(
            id=step_id,
            title=title,
            status=(
                AnalysisStepStatus.RUNNING
                if step_id == "collect_answers"
                else AnalysisStepStatus.PENDING
            ),
        )
        for step_id, title in _ANALYSIS_STEPS
    ]


class ShareTokenRepository:
    collection = "share_tokens"

    def __init__(self, client: FirestoreClient) -> None:
        self._client = client

    def reserve(
        self,
        token: str,
        drill_run_id: str,
        *,
        course_id: str | None = None,
        created_at: str | None = None,
    ) -> None:
        share_token = ShareToken(
            token=token,
            drill_run_id=drill_run_id,
            course_id=course_id,
            created_at=created_at,
        )
        self._client.create_document(
            self.collection,
            token,
            share_token.model_dump(mode="json", by_alias=True),
        )

    def get(self, token: str) -> ShareToken | None:
        document = self._client.get_document(self.collection, token)
        if document is None:
            return None
        return ShareToken.model_validate(document)

    def get_drill_run_id(self, token: str) -> str | None:
        share_token = self.get(token)
        return share_token.drill_run_id if share_token is not None else None

    def point_to_drill(self, token: str, drill_run_id: str, course_id: str) -> None:
        self._client.update_document(
            self.collection,
            token,
            {"drillRunId": drill_run_id, "courseId": course_id},
        )

    def close(self, token: str, closed_at: str) -> None:
        self._client.update_document(self.collection, token, {"closedAt": closed_at})

    def reopen(self, token: str) -> None:
        self._client.update_document(self.collection, token, {"closedAt": None})

    def run_transaction(self, callback: Callable[[], object]) -> object:
        return self._client.run_transaction(callback)

    def delete(self, token: str) -> None:
        self._client.delete_document(self.collection, token)


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

    def delete(self, answer_id: str) -> None:
        self._client.delete_document(self.collection, answer_id)


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

    def list_by_course(self, course_id: str) -> list[DocumentPatch]:
        return [
            DocumentPatch.model_validate(document)
            for document in self._client.list_documents_by_field(
                self.collection,
                "courseId",
                course_id,
            )
        ]

    def delete(self, patch_id: str) -> None:
        self._client.delete_document(self.collection, patch_id)
