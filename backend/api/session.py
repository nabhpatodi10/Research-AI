import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from api.models import SessionUser


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_session_token(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    encoded_signature = _b64url_encode(signature)
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def decode_session_token(token: str, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed session token.")

    encoded_header, encoded_payload, encoded_signature = parts
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = _b64url_decode(encoded_signature)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid token signature.")

    payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise ValueError("Missing token expiration.")
    if exp <= int(time.time()):
        raise ValueError("Token expired.")
    return payload


def set_auth_cookie(response: JSONResponse | RedirectResponse, request: Request, user: SessionUser) -> None:
    ttl = int(request.app.state.session_ttl_seconds)
    payload = {
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "provider": user.provider,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
    }
    token = create_session_token(payload, request.app.state.session_secret)
    response.set_cookie(
        key=request.app.state.cookie_name,
        value=token,
        max_age=ttl,
        httponly=True,
        secure=request.app.state.cookie_secure,
        samesite=request.app.state.cookie_samesite,
        domain=request.app.state.cookie_domain,
        path="/",
    )


def clear_auth_cookie(response: JSONResponse, request: Request) -> None:
    response.delete_cookie(
        key=request.app.state.cookie_name,
        domain=request.app.state.cookie_domain,
        path="/",
    )


def _auth_cookie_unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Authentication required.")


async def get_current_user(request: Request) -> SessionUser:
    token = request.cookies.get(request.app.state.cookie_name)
    if not token:
        raise _auth_cookie_unauthorized()
    try:
        payload = decode_session_token(token, request.app.state.session_secret)
        user_id = str(payload.get("sub") or "").strip()
        email = str(payload.get("email") or "").strip()
        name = str(payload.get("name") or "").strip()
        provider = str(payload.get("provider") or "").strip()
        if not user_id or not email:
            raise ValueError("Invalid token payload.")
        return SessionUser(
            id=user_id,
            email=email,
            name=name or email.split("@")[0],
            provider=provider or "emailPassword",
        )
    except Exception:
        raise _auth_cookie_unauthorized()

