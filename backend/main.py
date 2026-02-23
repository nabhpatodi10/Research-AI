import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_google_genai import ChatGoogleGenerativeAI

from api.routes.auth import router as auth_router
from api.routes.chat import router as chat_router
from api.routes.feedback import router as feedback_router
from api.routes.system import router as system_router
from auth_service import FirebaseAuthService
from browser_lifecycle import BrowserLifecycleManager, ManagedBrowser
from custom_search import CustomSearch
from database import Database
from graph_modules.visual_tier2 import PlaywrightVisualTier2Validator
from pdf_processing import PdfBackgroundWorker, PdfProcessingService
from research_worker import ResearchBackgroundWorker
from settings import get_settings, validate_security_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def _configure_noisy_library_loggers() -> None:
    settings = get_settings()
    noisy_log_level = settings.noisy_lib_log_level
    noisy_loggers = settings.noisy_library_loggers
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(noisy_log_level)


_configure_noisy_library_loggers()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    validate_security_settings(settings)
    app.state.browser_manager = BrowserLifecycleManager(headless=True)
    await app.state.browser_manager.start()
    app.state.browser = ManagedBrowser(app.state.browser_manager)
    app.state.custom_search = CustomSearch()
    app.state.database = Database()
    app.state.pdf_background_worker = PdfBackgroundWorker(app.state.database)
    app.state.pdf_worker_task = asyncio.create_task(
        app.state.pdf_background_worker.run_forever()
    )
    app.state.research_background_worker = ResearchBackgroundWorker(
        database=app.state.database,
        browser=app.state.browser,
    )
    app.state.research_worker_task = asyncio.create_task(
        app.state.research_background_worker.run_forever()
    )
    app.state.chat_model = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        thinking_level="minimal",
    )
    app.state.chat_model_mini = ChatGoogleGenerativeAI(
        model="models/gemini-flash-latest"
    )
    app.state.firebase_auth = FirebaseAuthService()

    app.state.frontend_base_url = settings.frontend_base_url or app.state.firebase_auth.frontend_base_url
    app.state.session_secret = settings.session_secret
    app.state.session_ttl_seconds = settings.session_ttl_seconds
    app.state.cookie_name = settings.cookie_name
    app.state.cookie_secure = settings.cookie_secure
    app.state.cookie_domain = settings.cookie_domain
    app.state.cookie_samesite = settings.cookie_samesite
    yield
    pdf_worker_task = getattr(app.state, "pdf_worker_task", None)
    if pdf_worker_task is not None:
        pdf_worker_task.cancel()
        await asyncio.gather(pdf_worker_task, return_exceptions=True)
    research_worker_task = getattr(app.state, "research_worker_task", None)
    if research_worker_task is not None:
        research_worker_task.cancel()
        await asyncio.gather(research_worker_task, return_exceptions=True)

    browser_manager = getattr(app.state, "browser_manager", None)
    if browser_manager is not None:
        await browser_manager.stop()
    await PlaywrightVisualTier2Validator.clear_session_limiters()
    await PdfProcessingService.aclose_shared_client()
    await CustomSearch.aclose()
    app.state.database.close_connection()


app = FastAPI(title="Research-AI Backend", lifespan=lifespan)

default_origins = [
    "http://localhost:3000",
]
settings = get_settings()
env_origins = list(settings.cors_origins)
frontend_origin = settings.frontend_base_url
all_origins = list(
    dict.fromkeys([*default_origins, *env_origins, *([frontend_origin] if frontend_origin else [])])
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=all_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(request.headers.get("x-request-id") or uuid4().hex)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


def _error_payload(message: str, code: str, request_id: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = str(getattr(request.state, "request_id", "") or uuid4().hex)
    detail = exc.detail
    if isinstance(detail, str):
        message = detail
    elif isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or "Request failed.")
    else:
        message = "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(message=message, code=f"http_{exc.status_code}", request_id=request_id),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = str(getattr(request.state, "request_id", "") or uuid4().hex)
    message = "Invalid request payload."
    if exc.errors():
        first_error = exc.errors()[0]
        message = str(first_error.get("msg") or message)
    return JSONResponse(
        status_code=422,
        content=_error_payload(message=message, code="validation_error", request_id=request_id),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = str(getattr(request.state, "request_id", "") or uuid4().hex)
    logger.exception("Unhandled backend error [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            message="Internal server error.",
            code="internal_error",
            request_id=request_id,
        ),
    )


app.include_router(system_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(feedback_router)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
