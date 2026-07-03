"""토큰 저장/조회/갱신.

~/.dasan/auth.json 에 access/refresh/id_token + account_id 를 평문 저장한다
(Codex의 auth.json 방식과 동일). access_token 만료가 임박하면 refresh_token
그랜트로 자동 갱신하고, 어댑터는 401 시 force_refresh 후 재시도한다.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import flow


def _decode_jwt_payload(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # base64url 패딩 복원
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _account_id(id_token: str) -> str | None:
    claims = _decode_jwt_payload(id_token)
    auth = claims.get("https://api.openai.com/auth", {})
    return auth.get("chatgpt_account_id") or claims.get("chatgpt_account_id")


class TokenStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path).expanduser()
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            return json.loads(self._path.read_text())
        return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))
        try:
            os.chmod(self._path, 0o600)  # 토큰 파일 권한 축소
        except OSError:
            pass

    def logged_in(self) -> bool:
        return bool(self._data.get("tokens", {}).get("access_token"))

    def save_login(self, token_resp: dict) -> None:
        self._store_tokens(token_resp)

    def _store_tokens(self, resp: dict) -> None:
        tokens = self._data.setdefault("tokens", {})
        tokens["access_token"] = resp["access_token"]
        if resp.get("refresh_token"):
            tokens["refresh_token"] = resp["refresh_token"]
        if resp.get("id_token"):
            tokens["id_token"] = resp["id_token"]
            acct = _account_id(resp["id_token"])
            if acct:
                tokens["account_id"] = acct
        expires_in = int(resp.get("expires_in", 3600))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
        self._data["expires_at"] = expires_at.isoformat()
        self._data["last_refresh"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def account_id(self) -> str | None:
        return self._data.get("tokens", {}).get("account_id")

    def _expired(self) -> bool:
        exp = self._data.get("expires_at")
        if not exp:
            return True
        return datetime.now(timezone.utc) >= datetime.fromisoformat(exp)

    def access_token(self) -> str:
        if not self.logged_in():
            raise RuntimeError("로그인이 필요합니다: python -m agent.main --login")
        if self._expired():
            self.force_refresh()
        return self._data["tokens"]["access_token"]

    def force_refresh(self) -> None:
        rt = self._data.get("tokens", {}).get("refresh_token")
        if not rt:
            raise RuntimeError("refresh_token이 없습니다. 다시 로그인: python -m agent.main --login")
        self._store_tokens(flow.refresh(rt))
