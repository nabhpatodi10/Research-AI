import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from api.models import (
    AuthResponse,
    LoginRequest,
    LogoutResponse,
    MeResponse,
    SessionUser,
    SignupRequest,
)
from api.session import (
    clear_auth_cookie,
    create_session_token,
    decode_session_token,
    get_current_user,
    set_auth_cookie,
)
from api.utils import normalize_email, oauth_error_redirect
from auth_service import FirebaseAuthError


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse)
async def auth_signup(request_body: SignupRequest, request: Request):
    name = request_body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    if len(request_body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    email = normalize_email(request_body.email)

    try:
        firebase_user = await request.app.state.firebase_auth.signup_email_password(
            name=name,
            email=email,
            password=request_body.password,
        )
        user_record = await request.app.state.database.upsert_user(
            user_id=firebase_user.id,
            email=firebase_user.email,
            name=firebase_user.name,
            provider=firebase_user.provider,
        )
        user = SessionUser(**user_record)
        response = JSONResponse(AuthResponse(user=user).model_dump())
        set_auth_cookie(response, request, user)
        return response
    except FirebaseAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)


@router.post("/login", response_model=AuthResponse)
async def auth_login(request_body: LoginRequest, request: Request):
    email = normalize_email(request_body.email)
    try:
        firebase_user = await request.app.state.firebase_auth.login_email_password(
            email=email,
            password=request_body.password,
        )
        user_record = await request.app.state.database.upsert_user(
            user_id=firebase_user.id,
            email=firebase_user.email,
            name=firebase_user.name,
            provider=firebase_user.provider,
        )
        user = SessionUser(**user_record)
        response = JSONResponse(AuthResponse(user=user).model_dump())
        set_auth_cookie(response, request, user)
        return response
    except FirebaseAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)


@router.post("/logout", response_model=LogoutResponse)
async def auth_logout(request: Request):
    response = JSONResponse(LogoutResponse(ok=True).model_dump())
    clear_auth_cookie(response, request)
    return response


@router.get("/me", response_model=MeResponse)
async def auth_me(request: Request, current_user: SessionUser = Depends(get_current_user)):
    db_user = await request.app.state.database.get_user(current_user.id)
    if db_user is not None:
        return MeResponse(user=SessionUser(**db_user))
    return MeResponse(user=current_user)


@router.get("/google/start")
async def auth_google_start(request: Request):
    state_payload = {
        "type": "oauth_state",
        "nonce": secrets.token_urlsafe(16),
        "exp": int(time.time()) + 600,
    }
    state_token = create_session_token(state_payload, request.app.state.session_secret)
    try:
        auth_url = request.app.state.firebase_auth.build_google_oauth_url(state_token)
    except FirebaseAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/google/callback")
async def auth_google_callback(request: Request, code: str | None = None, state: str | None = None):
    if not code or not state:
        return oauth_error_redirect(request, "missing_google_callback_params")

    try:
        payload = decode_session_token(state, request.app.state.session_secret)
        if payload.get("type") != "oauth_state":
            raise ValueError("Invalid OAuth state.")
    except Exception:
        return oauth_error_redirect(request, "invalid_oauth_state")

    try:
        firebase_user = await request.app.state.firebase_auth.login_with_google_code(code)
        user_record = await request.app.state.database.upsert_user(
            user_id=firebase_user.id,
            email=firebase_user.email,
            name=firebase_user.name,
            provider=firebase_user.provider,
        )
        user = SessionUser(**user_record)
        response = RedirectResponse(url=f"{request.app.state.frontend_base_url}/chat", status_code=302)
        set_auth_cookie(response, request, user)
        return response
    except FirebaseAuthError as error:
        return oauth_error_redirect(request, f"google_auth_failed:{error.message}")

