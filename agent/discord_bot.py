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
import traceback

from .citations import format_web_citations, strip_citation_tokens
from .config import load_config
from .service import AgentService

MAX_DISCORD = 2000  # Discord 메시지 최대 길이


def _allowed_user_ids() -> set[int]:
    """DISCORD_ALLOWED_USER_IDS(쉼표 구분)를 int 집합으로."""
    raw = os.environ.get("DISCORD_ALLOWED_USER_IDS", "")
    return {int(p) for p in raw.replace(" ", "").split(",") if p.isdigit()}


def _split(text: str, limit: int = MAX_DISCORD) -> list[str]:
    """긴 답변을 Discord 한도(2000자) 이하 조각으로 자른다(줄 경계 우선)."""
    # 어댑터에서 놓친 ChatGPT 전용 citation 토큰도 Discord 전송 직전에 제거한다.
    # URL annotation이 정상 수집된 경우에는 이미 일반 Markdown 출처 링크로 바뀌어 있다.
    text = format_web_citations(text) or "(빈 응답)"
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
    # ~/.dasan/discord.env 가 있으면 자동 로드(이미 설정된 환경변수가 우선).
    # 덕분에 `dasan discord` 만으로 실행된다.
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.expanduser("~/.dasan/discord.env"))
    except ImportError:
        pass

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

        # 허용된 사용자의 메시지면 DM·서버 채널 어디서든 멘션 없이 반응한다.
        # (허용 목록이 곧 잡음 방지 — 봇이 초대된 서버 = 내 서버)
        text = message.content
        if client.user in message.mentions:  # 멘션이 섞여 있으면 토큰만 제거
            text = text.replace(f"<@{client.user.id}>", "").replace(
                f"<@!{client.user.id}>", ""
            ).strip()
        # 봇 답변을 복사·붙여넣기하면 ChatGPT 전용 citation 토큰이 입력에 섞여
        # 백엔드가 턴 중간에 실패할 수 있다 — 모델에 넣기 전에 제거한다.
        text = strip_citation_tokens(text).strip()
        if not text:
            return

        sid = f"discord-{message.channel.id}"
        async with lock:
            async with message.channel.typing():
                try:
                    reply = await asyncio.to_thread(_respond_blocking, sid, text)
                except Exception as e:  # 봇이 죽지 않게 오류를 답장으로
                    traceback.print_exc()
                    reply = f"[오류] {e}"

        # 전송 실패가 조용히 사라지면 사용자는 '응답이 안 온' 것만 본다 —
        # 실패를 로그로 남기고 짧은 오류 답장이라도 반드시 시도한다.
        try:
            for chunk in _split(reply):
                await message.channel.send(chunk)
        except Exception:
            traceback.print_exc()
            try:
                await message.channel.send("[오류] 답변 전송에 실패했어요. 호스트 터미널 로그를 확인해주세요.")
            except Exception:
                pass

    client.run(token)
