from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_google_genai import ChatGoogleGenerativeAI
from playwright.async_api import async_playwright

from api.routes.auth import router as auth_router
from api.routes.chat import router as chat_router
from api.routes.feedback import router as feedback_router
from api.routes.system import router as system_router
from api.session import parse_bool
from auth_service import FirebaseAuthService
from custom_search import CustomSearch
from database import Database

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.playwright = await async_playwright().start()
    app.state.browser = await app.state.playwright.chromium.launch(headless=True)
    app.state.custom_search = CustomSearch()
    app.state.database = Database()
    app.state.chat_model = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        thinking_level="minimal",
    )
    app.state.chat_model_mini = ChatGoogleGenerativeAI(
        model="models/gemini-flash-latest"
    )
    app.state.firebase_auth = FirebaseAuthService()

    app.state.frontend_base_url = (
        os.getenv("FRONTEND_BASE_URL") or app.state.firebase_auth.frontend_base_url
    ).rstrip("/")
    app.state.session_secret = os.getenv("APP_SESSION_SECRET")
    app.state.session_ttl_seconds = int(os.getenv("APP_SESSION_TTL_SECONDS"))
    app.state.cookie_name = os.getenv("COOKIE_NAME", "ra_session")
    app.state.cookie_secure = parse_bool(os.getenv("COOKIE_SECURE"), default=True)
    app.state.cookie_domain = os.getenv("COOKIE_DOMAIN") or None
    cookie_samesite = (os.getenv("COOKIE_SAMESITE") or "lax").strip().lower()
    if cookie_samesite not in {"lax", "strict", "none"}:
        cookie_samesite = "lax"
    app.state.cookie_samesite = cookie_samesite
    yield
    await app.state.browser.close()
    await app.state.playwright.stop()
    await CustomSearch.aclose()
    app.state.database.close_connection()


app = FastAPI(title="Research-AI Backend", lifespan=lifespan)

default_origins = [
    "http://localhost:3000",
]
env_origins = [origin.strip() for origin in (os.getenv("CORS_ORIGINS") or "").split(",") if origin.strip()]
frontend_origin = os.getenv("FRONTEND_BASE_URL")
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

app.include_router(system_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(feedback_router)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
