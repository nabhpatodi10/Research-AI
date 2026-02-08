from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse


def normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required.")
    return email


def derive_session_title(user_input: str) -> str:
    normalized = " ".join((user_input or "").split()).strip()
    if not normalized:
        return "Untitled Session"
    max_len = 72
    return normalized if len(normalized) <= max_len else f"{normalized[:max_len - 3]}..."


def oauth_error_redirect(request: Request, message: str) -> RedirectResponse:
    frontend_base = request.app.state.frontend_base_url
    return RedirectResponse(url=f"{frontend_base}/login?error={message}", status_code=302)

