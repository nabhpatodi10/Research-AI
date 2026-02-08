import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, urlencode

import httpx


class FirebaseAuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class AuthUser:
    id: str
    email: str
    name: str
    provider: str


class FirebaseAuthService:
    def __init__(self):
        self._firebase_api_key = (
            os.getenv("FIREBASE_WEB_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        self._google_client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        self._google_client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
        self._google_redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
        self._frontend_base_url = (os.getenv("FRONTEND_BASE_URL") or "http://localhost:3000").rstrip(
            "/"
        )

        if not self._firebase_api_key:
            raise RuntimeError(
                "Missing Firebase Web API key. Set FIREBASE_WEB_API_KEY (or GEMINI_API_KEY/GOOGLE_API_KEY fallback)."
            )

    @staticmethod
    def _friendly_error(message: str) -> str:
        errors = {
            "EMAIL_EXISTS": "An account with this email already exists.",
            "INVALID_PASSWORD": "Invalid email or password.",
            "EMAIL_NOT_FOUND": "Invalid email or password.",
            "USER_DISABLED": "This account is disabled.",
            "INVALID_IDP_RESPONSE": "Google sign-in failed. Please try again.",
            "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
            "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Please try again later.",
        }
        return errors.get(message, message.replace("_", " ").capitalize())

    async def _identity_post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"https://identitytoolkit.googleapis.com/v1/{method}?key={self._firebase_api_key}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.post(url, json=payload)

        if response.is_success:
            return response.json()

        detail = "Authentication request failed."
        status_code = 400
        try:
            body = response.json()
            error = body.get("error", {}) if isinstance(body, dict) else {}
            message = str(error.get("message", "") or "").strip()
            if message:
                detail = self._friendly_error(message)
            status_code = int(error.get("code") or response.status_code)
        except Exception:
            detail = response.text or detail
            status_code = response.status_code

        raise FirebaseAuthError(detail, status_code=status_code)

    @staticmethod
    def _display_name_from_email(email: str) -> str:
        local = email.split("@")[0].strip()
        return local or email

    def _user_from_identity(
        self, payload: dict[str, Any], provider: str, preferred_name: str | None = None
    ) -> AuthUser:
        user_id = str(payload.get("localId") or "").strip()
        email = str(payload.get("email") or "").strip()
        if not user_id or not email:
            raise FirebaseAuthError("Authentication response missing user identity.", status_code=500)
        display_name = (
            str(preferred_name or "").strip()
            or str(payload.get("displayName") or "").strip()
            or self._display_name_from_email(email)
        )
        return AuthUser(id=user_id, email=email, name=display_name, provider=provider)

    async def signup_email_password(self, name: str, email: str, password: str) -> AuthUser:
        payload = {"email": email, "password": password, "returnSecureToken": True}
        response = await self._identity_post("accounts:signUp", payload)
        return self._user_from_identity(response, provider="emailPassword", preferred_name=name)

    async def login_email_password(self, email: str, password: str) -> AuthUser:
        payload = {"email": email, "password": password, "returnSecureToken": True}
        response = await self._identity_post("accounts:signInWithPassword", payload)
        return self._user_from_identity(response, provider="emailPassword")

    def build_google_oauth_url(self, state: str) -> str:
        if not self._google_client_id or not self._google_redirect_uri:
            raise FirebaseAuthError(
                "Google OAuth is not configured. Missing GOOGLE_OAUTH_CLIENT_ID or GOOGLE_OAUTH_REDIRECT_URI.",
                status_code=500,
            )

        query = urlencode(
            {
                "client_id": self._google_client_id,
                "redirect_uri": self._google_redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "online",
                "prompt": "consent",
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    async def login_with_google_code(self, code: str) -> AuthUser:
        if not self._google_client_id or not self._google_client_secret or not self._google_redirect_uri:
            raise FirebaseAuthError(
                "Google OAuth is not fully configured. Missing client id/secret/redirect URI.",
                status_code=500,
            )

        token_payload = {
            "code": code,
            "client_id": self._google_client_id,
            "client_secret": self._google_client_secret,
            "redirect_uri": self._google_redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            token_response = await client.post("https://oauth2.googleapis.com/token", data=token_payload)

        if not token_response.is_success:
            raise FirebaseAuthError("Failed to exchange Google OAuth code.", status_code=400)

        token_data = token_response.json()
        id_token = str(token_data.get("id_token") or "").strip()
        if not id_token:
            raise FirebaseAuthError("Google OAuth response missing id_token.", status_code=400)

        firebase_payload = {
            "postBody": f"id_token={quote_plus(id_token)}&providerId=google.com",
            "requestUri": f"{self._frontend_base_url}/chat",
            "returnSecureToken": True,
            "returnIdpCredential": True,
        }
        response = await self._identity_post("accounts:signInWithIdp", firebase_payload)
        return self._user_from_identity(response, provider="google")

    @property
    def frontend_base_url(self) -> str:
        return self._frontend_base_url
