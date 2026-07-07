from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clients.adk_agent_invoker import create_adk_invoker
from app.clients.agent_runtime_client import AgentInvoker, AgentRuntimeClient
from app.clients.local_agent_invoker import LocalAgentInvoker
from app.config import Settings, get_settings
from app.errors import register_exception_handlers
from app.observability import configure_adk_tracing
from app.repositories.firestore_client import (
    FirestoreClient,
    GoogleFirestoreClient,
    InMemoryFirestoreClient,
)
from app.repositories.repositories import (
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
    ShareTokenRepository,
)
from app.request_context import RequestContextMiddleware
from app.routes.courses import router as courses_router
from app.routes.drills import router as drills_router
from app.routes.health import router as health_router
from app.routes.learn import router as learn_router
from app.routes.patches import router as patches_router
from app.services.analysis_service import AnalysisService
from app.services.answer_service import AnswerService
from app.services.course_service import CourseService
from app.services.drill_service import DrillService
from app.services.patch_service import PatchService
from app.services.share_token_service import ShareTokenService


def _create_agent_invoker(settings: Settings) -> AgentInvoker:
    if settings.agent_mode == "adk":
        return create_adk_invoker(settings)
    return LocalAgentInvoker()


def _create_firestore_client(settings: Settings) -> FirestoreClient:
    if settings.storage_mode == "firestore":
        return GoogleFirestoreClient(database=settings.firestore_database)
    return InMemoryFirestoreClient()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_adk_tracing(settings)
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.auth_boundary = "mvp_no_auth"
    firestore_client = _create_firestore_client(settings)
    course_repository = CourseRepository(firestore_client)
    drill_repository = DrillRepository(firestore_client)
    share_token_repository = ShareTokenRepository(firestore_client)
    answer_repository = AnswerRepository(firestore_client)
    patch_repository = PatchRepository(firestore_client)
    app.state.firestore_client = firestore_client
    app.state.course_repository = course_repository
    app.state.drill_repository = drill_repository
    app.state.answer_repository = answer_repository
    app.state.share_token_repository = share_token_repository
    app.state.patch_repository = patch_repository
    app.state.course_service = CourseService(
        course_repository,
        drill_repository=drill_repository,
        answer_repository=answer_repository,
        patch_repository=patch_repository,
    )
    agent_client = AgentRuntimeClient(invoker=_create_agent_invoker(settings))
    app.state.answer_service = AnswerService(
        course_repository=course_repository,
        drill_repository=drill_repository,
        answer_repository=answer_repository,
        share_token_repository=share_token_repository,
        agent_client=agent_client,
    )
    app.state.drill_service = DrillService(
        course_repository=course_repository,
        drill_repository=drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=drill_repository,
            share_token_repository=share_token_repository,
        ),
        agent_client=agent_client,
        answer_repository=answer_repository,
        share_token_repository=share_token_repository,
    )
    app.state.analysis_service = AnalysisService(
        drill_repository,
        answer_repository,
        course_repository=course_repository,
        patch_repository=patch_repository,
        agent_client=agent_client,
    )
    app.state.patch_service = PatchService(course_repository, patch_repository, firestore_client)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(courses_router)
    app.include_router(drills_router)
    app.include_router(learn_router)
    app.include_router(patches_router)
    app.include_router(health_router)
    return app


app = create_app()
