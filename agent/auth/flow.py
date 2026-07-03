"""OpenAI(ChatGPT) "Sign in with ChatGPT" OAuth 2.0 PKCE 플로우.

Codex CLI가 쓰는 공개 클라이언트를 재사용한다(개인용). 실제 확인값:
  authorize : https://auth.openai.com/oauth/authorize
  token     : https://auth.openai.com/oauth/token
  client_id : app_EMoamEEZ73f0CkXaXp7hrann
  redirect  : http://localhost:1455/auth/callback
  PKCE      : S256
  scopes    : openid profile email offline_access

주의: 이 client_id/백엔드는 OpenAI 자사 Codex 전용이다. 커스텀 에이전트가
재사용하는 건 ToS 회색지대이며 리스크는 사용자 책임(2번 옵션 선택).
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import urllib.parse
import webbrowser

import httpx

AUTH_BASE = "https://auth.openai.com"
AUTHORIZE_URL = f"{AUTH_BASE}/oauth/authorize"
TOKEN_URL = f"{AUTH_BASE}/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REDIRECT_PORT = 1455
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/auth/callback"
SCOPES = "openid profile email offline_access"


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_response(404)
            self.end_headers()
            return
        q = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.result = {
            "code": q.get("code", [None])[0],
            "state": q.get("state", [None])[0],
            "error": q.get("error", [None])[0],
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<html><body><h3>로그인 완료. 이 창을 닫아도 됩니다.</h3></body></html>".encode()
        )

    def log_message(self, *args) -> None:  # 콘솔 로그 억제
        pass


def login() -> dict:
    """브라우저 OAuth 플로우를 돌려 토큰 응답(dict)을 반환한다."""
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        # Codex가 함께 보내는 힌트 파라미터
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)

    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    _CallbackHandler.result = {}
    print("브라우저에서 로그인하세요. 자동으로 안 열리면 이 URL을 여세요:\n" + url)
    webbrowser.open(url)

    # /favicon.ico 등 다른 요청이 먼저 올 수 있으니 code/error 받을 때까지 반복
    while not _CallbackHandler.result.get("code") and not _CallbackHandler.result.get("error"):
        server.handle_request()
    server.server_close()

    res = _CallbackHandler.result
    if res.get("error"):
        raise RuntimeError(f"OAuth 오류: {res['error']}")
    if res.get("state") != state:
        raise RuntimeError("state 불일치 (CSRF 의심) — 다시 시도하세요")
    return exchange_code(res["code"], verifier)


def exchange_code(code: str, verifier: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": verifier,
    }
    r = httpx.post(TOKEN_URL, data=data, timeout=30)
    r.raise_for_status()
    return r.json()


def refresh(refresh_token: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "scope": SCOPES,
    }
    r = httpx.post(TOKEN_URL, data=data, timeout=30)
    r.raise_for_status()
    return r.json()
