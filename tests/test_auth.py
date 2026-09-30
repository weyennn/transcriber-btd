"""Authentication contract tests without real Google credentials or network."""

import importlib

import pytest
from fastapi.testclient import TestClient


def load_auth(monkeypatch, **values):
    defaults = {
        "AUTH_ENABLED": "true",
        "SESSION_SECRET": "test-session-secret-please-change",
        "GOOGLE_CLIENT_ID": "client-id",
        "GOOGLE_CLIENT_SECRET": "client-secret",
        "GOOGLE_REDIRECT_URI": "https://dts-lab.web.id/transcribe/api/auth/callback",
        "AUTH_ALLOWED_DOMAIN": "ugm.ac.id",
        "AUTH_ALLOWED_EMAILS": "",
        "APP_BASE_PATH": "/transcribe",
        "AUTH_COOKIE_SECURE": "true",
    }
    defaults.update(values)
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)
    import src.web.auth as auth
    return importlib.reload(auth)


def test_anonymous_protected_route_is_rejected(monkeypatch):
    auth = load_auth(monkeypatch)
    request = type("Request", (), {"cookies": {}})()
    with pytest.raises(Exception) as exc:
        auth.get_current_user(request)
    assert exc.value.status_code == 401


def test_login_state_is_signed_and_next_is_local(monkeypatch):
    auth = load_auth(monkeypatch)
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/transcribe/api/auth/login",
        "query_string": b"next=https%3A%2F%2Fevil.example%2Fsteal",
        "headers": [],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "scheme": "https",
    }
    response = auth.login(Request(scope))
    assert response.status_code == 307
    assert "evil.example" not in response.headers["location"]
    assert "transcribe" in response.headers["location"]
    assert "transcribe_oauth_state" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]


def test_callback_rejects_state_mismatch(monkeypatch):
    auth = load_auth(monkeypatch)
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/transcribe/api/auth/callback",
        "query_string": b"code=abc&state=wrong",
        "headers": [],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "scheme": "https",
    }
    with pytest.raises(Exception) as exc:
        auth.callback(Request(scope))
    assert exc.value.status_code == 400


def test_callback_creates_signed_session(monkeypatch):
    auth = load_auth(monkeypatch)
    from starlette.requests import Request
    from urllib.parse import quote

    login_scope = {
        "type": "http", "method": "GET", "path": "/transcribe/api/auth/login",
        "query_string": b"next=%2Ftranscribe%2F", "headers": [],
        "client": ("testclient", 123), "server": ("testserver", 80), "scheme": "https",
    }
    login_response = auth.login(Request(login_scope))
    state = login_response.headers["set-cookie"].split("transcribe_oauth_state=", 1)[1].split(";", 1)[0]

    class FakeResponse:
        status_code = 200
        is_success = True

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class FakeGoogleClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, data):
            assert url == "https://oauth2.googleapis.com/token"
            assert data["code"] == "auth-code"
            return FakeResponse({"access_token": "server-only-token"})

        def get(self, url, headers):
            assert url == "https://openidconnect.googleapis.com/v1/userinfo"
            assert headers["Authorization"] == "Bearer server-only-token"
            return FakeResponse({
                "sub": "google-sub", "email": "person@ugm.ac.id",
                "email_verified": True, "name": "Person UGM",
            })

    monkeypatch.setattr(auth.httpx, "Client", FakeGoogleClient)
    callback_scope = {
        "type": "http", "method": "GET", "path": "/transcribe/api/auth/callback",
        "query_string": f"code=auth-code&state={quote(state)}".encode(),
        "headers": [(b"cookie", f"transcribe_oauth_state={state}".encode())],
        "client": ("testclient", 123), "server": ("testserver", 80), "scheme": "https",
    }
    response = auth.callback(Request(callback_scope))
    assert response.status_code == 303
    assert response.headers["location"] == "/transcribe/?auth=success"
    cookie = response.headers["set-cookie"]
    assert "transcribe_session=" in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie

    session = cookie.split("transcribe_session=", 1)[1].split(";", 1)[0]
    session_scope = {
        "type": "http", "method": "GET", "path": "/transcribe/api/auth/me",
        "query_string": b"", "headers": [(b"cookie", f"transcribe_session={session}".encode())],
        "client": ("testclient", 123), "server": ("testserver", 80), "scheme": "https",
    }
    assert auth.auth_me(Request(session_scope))["user"]["email"] == "person@ugm.ac.id"


def test_allowlist_requires_verified_ugm_account(monkeypatch):
    auth = load_auth(monkeypatch)
    assert auth._allowed_user({"email": "person@ugm.ac.id", "email_verified": True})
    assert auth._allowed_user({"email": "person@mail.ugm.ac.id", "email_verified": True})
    assert not auth._allowed_user({"email": "person@ugm.ac.id", "email_verified": False})
    assert not auth._allowed_user({"email": "person@example.com", "email_verified": True})
    assert not auth._allowed_user({"email": "person@evilugm.ac.id", "email_verified": True})


def test_auth_routes_and_protection_with_fastapi(monkeypatch):
    load_auth(monkeypatch)
    monkeypatch.setattr("src.core.engine.TranscribeEngine.apply_wdac_patch", classmethod(lambda cls: None))
    import src.web.server as server
    server = importlib.reload(server)
    client = TestClient(server.app)
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/env").status_code == 401
    assert client.get("/").status_code == 200
