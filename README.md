# Dasan

LLM으로 로컬 파일을 제어하는 개인 에이전트 하네스 (MVP).
"질문 → `read_file` 도구로 파일 읽기 → 답변" ReAct 루프를 끝까지 돌리고, 대화를 SQLite에 저장한다.

**인증**: OpenAI(ChatGPT 구독) OAuth — Codex CLI의 "Sign in with ChatGPT" 플로우를 재사용 (개인용).

## 빠른 시작

```bash
pip install -r requirements.txt
python3 -m agent.main --login                    # 브라우저 로그인 (최초 1회)
python3 -m agent.main "이 파일 요약해줘: ./notes.txt"
```

## 사용

```bash
python3 -m agent.main                    # 채팅 TUI (CC 스타일, 스트리밍) — 종료: /exit
python3 -m agent.main "질문..."          # 단발 질문 (스크립트용)
python3 -m agent.main --list             # 세션 목록
python3 -m agent.main --session <id>     # 세션 이어가기
AGENT_DEBUG=1 python3 -m agent.main ...  # 디버그 (원본 스트림 /tmp/dasan_raw.txt)
```

TUI 안 명령: `/new` `/sessions` `/clear` `/help` `/exit`

## 구조

```
agent/
├─ auth/          # OAuth PKCE 플로우 + 토큰 저장/자동 갱신
├─ providers/     # 모델 호출 어댑터 (openai_oauth / anthropic)
├─ core/loop.py   # ReAct 루프 (추론 → 도구 → 관찰)
├─ tools/         # 도구 등록 + read_file
├─ session/       # SQLite 세션 저장
├─ service.py     # AgentService — 프론트엔드 무관 코어 (respond)
├─ tui.py         # CC 스타일 채팅 TUI (스트리밍)
├─ config.py      # 설정 (env로 override)
└─ main.py        # CLI 진입점
```

**설계**: 루프/도구/세션은 프로바이더를 모른다. 어댑터의 정규화 타입만 사용 → 어댑터 교체로 모델/프로바이더 전환. 표면(CLI/TUI/Discord/웹)은 `AgentService.respond(session_id, text)` 하나만 호출. 도구는 등록과 노출을 분리하고, 입력은 Pydantic으로 검증.

## 설정 (env, 선택)

| 변수 | 기본값 |
|---|---|
| `AGENT_MODEL` | `gpt-5.5` |
| `AGENT_DB_PATH` | `agent_sessions.db` |
| `AGENT_AUTH_PATH` | `~/.dasan/auth.json` |
| `AGENT_BASE_URL` | `https://chatgpt.com/backend-api/codex` |

## 주의

Codex 공개 client_id와 ChatGPT 백엔드를 재사용하는 방식이라 OpenAI ToS 회색지대다. 개인 실험 용도이며 리스크는 사용자 책임. 토큰은 `~/.dasan/auth.json`(권한 600)에 저장되며 리포에 커밋되지 않는다.
