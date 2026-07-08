from app.clients.agent_runtime_client import AgentRuntimeClient
from app.clients.local_agent_invoker import LocalAgentInvoker
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import CourseRepository, DrillRepository, ShareTokenRepository
from app.schemas import Course, DrillGenerationRequest
from app.services.drill_service import DrillService
from app.services.share_token_service import ShareTokenService


def test_local_generate_drill_uses_course_markdown_for_source_evidence() -> None:
    course_markdown = "# 申請手順\n申請前に上長の承認を得る。"
    client = AgentRuntimeClient(invoker=LocalAgentInvoker())

    response = client.generate_drill(
        DrillGenerationRequest(
            course_title="申請講座",
            course_markdown=course_markdown,
            drill_focus="承認条件",
        )
    )

    assert all(
        evidence.excerpt in course_markdown
        for question in response.questions
        for evidence in question.source_evidence
    )
    assert all(
        evidence.excerpt != "## 判断基準"
        for question in response.questions
        for evidence in question.source_evidence
    )
    assert any(
        "承認条件" in question.question or "承認条件" in question.intent
        for question in response.questions
    )


def test_local_generate_drill_passes_backend_evidence_validation() -> None:
    course_markdown = "申請前に上長の承認を得る。"
    firestore_client = InMemoryFirestoreClient()
    course_repository = CourseRepository(firestore_client)
    drill_repository = DrillRepository(firestore_client)
    share_token_repository = ShareTokenRepository(firestore_client)
    course_repository.create(
        Course(
            id="course-1",
            owner_user_id="owner-1",
            title="申請講座",
            markdown=course_markdown,
            drill_focus="承認条件",
        )
    )
    service = DrillService(
        course_repository=course_repository,
        drill_repository=drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=drill_repository,
            share_token_repository=share_token_repository,
            token_generator=lambda: "share-token",
        ),
        agent_client=AgentRuntimeClient(invoker=LocalAgentInvoker()),
    )

    drill_run = service.generate_drill("course-1", "owner-1")

    assert drill_run.status == "ready"
    assert all(
        evidence.excerpt in course_markdown
        for question in drill_run.questions
        for evidence in question.source_evidence
    )
