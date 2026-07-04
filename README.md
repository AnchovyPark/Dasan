# Dasan

LLM으로 로컬 파일을 제어하는 개인 에이전트 하네스.
"질문 → 도구(list_dir·search·read_file·write_file)로 프로젝트 탐색·수정 → 답변" ReAct 루프를 끝까지 돌리고,
대화는 단일 세션으로 SQLite(`~/.dasan/sessions.db`)에 계속 이어진다. 시스템 프롬프트는 불변 역할(CORE)과 학습되는 사용자 정렬(ALIGNMENT) 2겹.

**인증**: OpenAI(ChatGPT 구독) OAuth — Codex CLI의 "Sign in with ChatGPT" 플로우를 재사용 (개인용).

## 설치 (다른 컴퓨터 — 한 줄 전역 설치)

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/AnchovyPark/Dasan/main/install.sh | bash
```
```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/AnchovyPark/Dasan/main/install.ps1 | iex
```

GitHub에서 최신 코드를 받아 **pipx**로 전역 설치하고 `dasan` 명령을 PATH에 놓는다.
설치 후 새 터미널에서 `dasan login` → `dasan start`. (pipx가 없으면 스크립트가 알아서 깔아준다.)

## 개발 (이 리포에서 직접 수정)

```bash
pip install -e .        # editable 설치 — 소스 수정이 즉시 반영됨
dasan login             # 브라우저 로그인 (최초 1회)
```

`python -m agent.main <인자>` 로도 동일하게 동작한다.

## 사용

```bash
dasan                          # 채팅 TUI (CC 스타일, 스트리밍) — 종료: /exit
dasan start --session <id>     # 세션 이어가기
dasan ask "이 파일 요약해줘: ./notes.txt"   # 단발 질문 (스크립트용)
dasan list                     # 세션 목록
AGENT_DEBUG=1 dasan ask "..."  # 디버그 (원본 스트림 /tmp/dasan_raw.txt)
```

TUI 안 명령: `/new` `/sessions` `/clear` `/help` `/exit`

## 구조

```
agent/
├─ auth/          # OAuth PKCE 플로우 + 토큰 저장/자동 갱신
├─ providers/     # 모델 호출 어댑터 (openai_oauth / anthropic)
├─ core/loop.py   # ReAct 루프 (추론 → 도구 → 관찰)
├─ prompt.py      # 시스템 프롬프트 CORE(불변)+ALIGNMENT(가변) 조립
├─ alignment.py   # 사용자 지속 선호 저장(~/.dasan/alignment.md)
├─ tools/         # read_file · list_dir · search · write_file · remember_preference
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
| `AGENT_REASONING` | `high` (minimal/low/medium/high, 또는 `off`) |
| `AGENT_DB_PATH` | `~/.dasan/sessions.db` |
| `AGENT_AUTH_PATH` | `~/.dasan/auth.json` |
| `AGENT_ALIGNMENT_PATH` | `~/.dasan/alignment.md` |
| `AGENT_BASE_URL` | `https://chatgpt.com/backend-api/codex` |

## 주의

Codex 공개 client_id와 ChatGPT 백엔드를 재사용하는 방식이라 OpenAI ToS 회색지대다. 개인 실험 용도이며 리스크는 사용자 책임. 토큰은 `~/.dasan/auth.json`(권한 600)에 저장되며 리포에 커밋되지 않는다.
