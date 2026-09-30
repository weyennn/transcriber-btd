"""Backend-managed Google OAuth sessions for the web dashboard."""

from __future__ import annotations

import hmac
import hashlib
import os
import secrets
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").strip().lower() == "true"
BASE_PATH = os.environ.get("APP_BASE_PATH", "/transcribe").strip() or "/transcribe"
if not BASE_PATH.startswith("/"):
    BASE_PATH = f"/{BASE_PATH}"
BASE_PATH = BASE_PATH.rstrip("/") or "/"

SESSION_COOKIE = "transcribe_session"
STATE_COOKIE = "transcribe_oauth_state"
SESSION_DAYS = max(1, int(os.environ.get("SESSION_DAYS", "7")))
SESSION_MAX_AGE = SESSION_DAYS * 86400
STATE_MAX_AGE = 600
COOKIE_SECURE = os.environ.get(
    "AUTH_COOKIE_SECURE", "true" if AUTH_ENABLED else "false"
).strip().lower() == "true"

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "https://dts-lab.web.id/transcribe/api/auth/callback",
).strip()
ALLOWED_DOMAINS = {
    "ugm.ac.id",
    "mail.ugm.ac.id",
    *(
        domain.strip().lower().lstrip("@")
        for domain in os.environ.get("AUTH_ALLOWED_DOMAIN", "").split(",")
        if domain.strip()
    ),
}
ALLOWED_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("AUTH_ALLOWED_EMAILS", "").split(",")
    if email.strip()
}
SESSION_SECRET = os.environ.get("SESSION_SECRET", "").strip()
_serializer = URLSafeTimedSerializer(SESSION_SECRET) if SESSION_SECRET else None


def _configuration_error() -> str | None:
    if not AUTH_ENABLED:
        return None
    missing = [
        name
        for name, value in (
            ("SESSION_SECRET", SESSION_SECRET),
            ("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID),
            ("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET),
            ("GOOGLE_REDIRECT_URI", GOOGLE_REDIRECT_URI),
        )
        if not value
    ]
    return f"Konfigurasi auth belum lengkap: {', '.join(missing)}" if missing else None


def _require_configuration() -> None:
    error = _configuration_error()
    if error:
        raise HTTPException(503, error)


def _cookie_path() -> str:
    return BASE_PATH


def _safe_next(value: str | None) -> str:
    """Accept only same-origin paths under the application base path."""
    default = f"{BASE_PATH}/" if BASE_PATH != "/" else "/"
    if not value:
        return default
    parsed = urlsplit(value)
    path = parsed.path
    if parsed.scheme or parsed.netloc or path.startswith("//"):
        return default
    if BASE_PATH != "/" and not (path == BASE_PATH or path.startswith(f"{BASE_PATH}/")):
        return default
    return path + (f"?{parsed.query}" if parsed.query else "")


def _allowed_user(user: dict[str, Any]) -> bool:
    email = str(user.get("email", "")).strip().lower()
    verified = user.get("email_verified") is True or str(
        user.get("email_verified", "")
    ).lower() == "true"
    if not email or not verified:
        return False
    if email in ALLOWED_EMAILS:
        return True
    return any(email.endswith(f"@{domain}") for domain in ALLOWED_DOMAINS)


def _sign(payload: dict[str, Any]) -> str:
    _require_configuration()
    assert _serializer is not None
    return _serializer.dumps(payload)


def _unsign(value: str, max_age: int) -> dict[str, Any]:
    _require_configuration()
    assert _serializer is not None
    data = _serializer.loads(value, max_age=max_age)
    if not isinstance(data, dict):
        raise BadSignature("payload bukan object")
    return data


def current_user(request: Request) -> dict[str, Any] | None:
    if not AUTH_ENABLED:
        return {"email": "local@development", "name": "Local development", "dev": True}
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    try:
        data = _unsign(cookie, SESSION_MAX_AGE)
        user = data.get("user")
        return user if isinstance(user, dict) else None
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None


def get_current_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency for every protected data endpoint."""
    if not AUTH_ENABLED:
        return current_user(request) or {"email": "local@development", "dev": True}
    _require_configuration()
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Login diperlukan")
    return user


def user_id(user: dict[str, Any]) -> str:
    """Create an opaque, stable storage namespace from the Google subject."""
    subject = str(user.get("sub", "")).strip()
    identity = f"google:{subject}" if subject else f"email:{str(user.get('email', '')).strip().lower()}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def is_archive_admin(user: dict[str, Any]) -> bool:
    admins = {item.strip().lower() for item in os.environ.get("AUTH_ADMIN_EMAILS", "").split(",") if item.strip()}
    return str(user.get("email", "")).strip().lower() in admins


def auth_me(request: Request) -> dict[str, Any]:
    if not AUTH_ENABLED:
        return {"authenticated": True, "auth_enabled": False, "user": current_user(request)}
    _require_configuration()
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Login diperlukan")
    return {"authenticated": True, "auth_enabled": True, "user": user}


def login(request: Request) -> RedirectResponse:
    if not AUTH_ENABLED:
        raise HTTPException(404, "Login Google tidak diaktifkan")
    _require_configuration()
    state = _sign({
        "nonce": secrets.token_urlsafe(32),
        "next": _safe_next(request.query_params.get("next")),
    })
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    response = RedirectResponse(
        f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}",
        status_code=307,
    )
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path=_cookie_path(),
    )
    return response


def callback(request: Request) -> RedirectResponse:
    if not AUTH_ENABLED:
        raise HTTPException(404, "Login Google tidak diaktifkan")
    _require_configuration()
    if request.query_params.get("error"):
        raise HTTPException(400, "Login Google dibatalkan")

    code = request.query_params.get("code")
    supplied_state = request.query_params.get("state", "")
    cookie_state = request.cookies.get(STATE_COOKIE, "")
    if not code or not supplied_state or not cookie_state or not hmac.compare_digest(
        supplied_state, cookie_state
    ):
        raise HTTPException(400, "OAuth state tidak valid atau sudah kedaluwarsa")
    try:
        state_data = _unsign(supplied_state, STATE_MAX_AGE)
    except (BadSignature, SignatureExpired, TypeError, ValueError) as exc:
        raise HTTPException(400, "OAuth state tidak valid atau sudah kedaluwarsa") from exc

    try:
        with httpx.Client(timeout=20.0) as client:
            token_response = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            if not token_response.is_success:
                raise HTTPException(502, "Google token exchange gagal")
            token = token_response.json()
            access_token = token.get("access_token")
            if not access_token:
                raise HTTPException(502, "Google tidak mengembalikan access token")
            user_response = client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if not user_response.is_success:
                raise HTTPException(502, "Google userinfo gagal dibaca")
            google_user = user_response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"Koneksi ke Google gagal: {exc}") from exc

    user = {
        "sub": str(google_user.get("sub", "")),
        "email": str(google_user.get("email", "")).strip().lower(),
        "email_verified": google_user.get("email_verified", False),
        "name": str(google_user.get("name", "")).strip(),
        "picture": str(google_user.get("picture", "")).strip(),
    }
    if not _allowed_user(user):
        raise HTTPException(403, "Akun Google tidak termasuk pengguna yang diizinkan")

    next_path = _safe_next(state_data.get("next"))
    separator = "&" if "?" in next_path else "?"
    response = RedirectResponse(f"{next_path}{separator}auth=success", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        _sign({"user": user}),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path=_cookie_path(),
    )
    response.delete_cookie(STATE_COOKIE, path=_cookie_path())
    return response


def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path=_cookie_path())
    response.delete_cookie(STATE_COOKIE, path=_cookie_path())
    return response
