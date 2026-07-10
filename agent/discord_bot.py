"""Discord 봇 표면 — 채팅 메시지를 AgentService.respond()로 넘긴다.

Mac mini에서 `dasan discord`로 상시 실행한다. 봇 프로세스가 Discord에
outbound로 붙으므로 들어오는 포트를 하나도 열지 않는다(집 밖 폰에서도 안전하게 호출).

권한: DISCORD_ALLOWED_USER_IDS(쉼표 구분)에 있는 사용자만 처리한다. 비어 있으면
안전상 기본 거부(아무 메시지도 실행하지 않음). agent가 파일 수정·명령 실행을 하므로
반드시 본인 ID만 넣는다.

세션: Discord 채널 하나당 세션 하나(discord-<channel_id>). 채널을 나누면 프로젝트별
대화가 분리된다.
"""
from __future__ import annotations

import asyncio
import os

from .config import load_config
from .service import AgentService

MAX_DISCORD = 2000  # Discord 메시지 최대 길이


def _allowed_user_ids() -> set[int]:
    """DISCORD_ALLOWED_USER_IDS(쉼표 구분)를 int 집합으로."""
    raw = os.environ.get("DISCORD_ALLOWED_USER_IDS", "")
    return {int(p) for p in raw.replace(" ", "").split(",") if p.isdigit()}


def _split(text: str, limit: int = MAX_DISCORD) -> list[str]:
    """긴 답변을 Discord 한도(2000자) 이하 조각으로 자른다(줄 경계 우선)."""
    text = text or "(빈 응답)"
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def _respond_blocking(sid: str, text: str) -> str:
    """워커 스레드에서 실행: 서비스 생성→respond→close 를 한 스레드 안에서 끝낸다.

    SQLite 연결은 만든 스레드에서만 쓸 수 있어서, 서비스의 생성·사용·종료를
    모두 이 함수(=하나의 to_thread 호출) 안에 둔다.
    """
    service = AgentService(load_config())
    try:
        if not service.logged_in():
            return "⚠️ 아직 로그인되지 않았어요. 호스트(Mac mini)에서 `dasan login` 을 먼저 해주세요."
        if not service.session_exists(sid):
            sid = service.new_session(sid)
        return service.respond(sid, text)
    finally:
        service.close()


def run_bot() -> None:
    try:
        import discord
    except ImportError as e:
        raise SystemExit(
            "discord.py 가 필요합니다.\n"
            "  일반 설치: pip install 'discord.py>=2.3'\n"
            "  pipx 설치: pipx inject dasan 'discord.py>=2.3'"
        ) from e

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN 환경변수를 설정하세요(개발자 포털의 봇 토큰).")

    allowed = _allowed_user_ids()
    if not allowed:
        print(
            "⚠️  DISCORD_ALLOWED_USER_IDS 가 비어 있어 안전상 아무 메시지도 처리하지 않습니다.\n"
            "    본인 Discord 사용자 ID를 넣어 실행하세요: DISCORD_ALLOWED_USER_IDS=123456789012345678"
        )

    intents = discord.Intents.default()
    intents.message_content = True  # 메시지 본문 읽기(개발자 포털에서 Message Content Intent 활성화 필요)
    client = discord.Client(intents=intents)
    lock = asyncio.Lock()  # 한 번에 한 턴만 처리(같은 세션 동시 쓰기 방지)

    @client.event
    async def on_ready() -> None:
        print(f"[dasan] Discord 봇 로그인: {client.user}  (허용 사용자 {len(allowed)}명)")

    @client.event
    async def on_message(message) -> None:
        if message.author.bot:  # 자기 자신·다른 봇 무시
            return
        if message.author.id not in allowed:  # 허용된 사용자만
            return

        is_dm = message.guild is None
        # 서버 채널에선 봇을 멘션했을 때만 반응(잡음 방지). DM은 전부 반응.
        if not is_dm and client.user not in message.mentions:
            return

        text = message.content
        if not is_dm:  # 멘션 토큰 제거
            text = text.replace(f"<@{client.user.id}>", "").replace(
                f"<@!{client.user.id}>", ""
            ).strip()
        if not text:
            return

        sid = f"discord-{message.channel.id}"
        async with lock:
            async with message.channel.typing():
                try:
                    reply = await asyncio.to_thread(_respond_blocking, sid, text)
                except Exception as e:  # 봇이 죽지 않게 오류를 답장으로
                    reply = f"[오류] {e}"

        for chunk in _split(reply):
            await message.channel.send(chunk)

    client.run(token)
