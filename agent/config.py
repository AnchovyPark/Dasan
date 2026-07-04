"""설정 로딩: 인증 저장 위치, 모델명, 백엔드 URL 등.

메인 프로바이더는 OpenAI(ChatGPT 구독) OAuth. 정적 API 키 대신 토큰
스토어 경로를 넘긴다. base_url/model은 문서화되지 않은 백엔드 계약이라
환경변수로 조정 가능하게 열어둔다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # .env가 있으면 로드 (없어도 무방)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class Config:
    auth_path: str  # OAuth 토큰 저장 위치
    base_url: str  # Responses API 백엔드 (Codex 버전마다 다를 수 있음)
    model: str
    db_path: str
    alignment_path: str  # 사용자 지속 선호(ALIGNMENT) 저장 파일
    reasoning_effort: str  # gpt-5.x 추론 강도: minimal/low/medium/high, 또는 off


def load_config() -> Config:
    return Config(
        auth_path=os.environ.get("AGENT_AUTH_PATH", "~/.dasan/auth.json"),
        base_url=os.environ.get("AGENT_BASE_URL", "https://chatgpt.com/backend-api/codex"),
        model=os.environ.get("AGENT_MODEL", "gpt-5.5"),
        db_path=os.environ.get("AGENT_DB_PATH", "~/.dasan/sessions.db"),
        alignment_path=os.environ.get("AGENT_ALIGNMENT_PATH", "~/.dasan/alignment.md"),
        reasoning_effort=os.environ.get("AGENT_REASONING", "high"),
    )
