"""컨텍스트 압축 — raw는 DB에 불변으로 두고, 모델에 보낼 것만 다듬는 3층 기억.

보내는 컨텍스트 = [시스템(CORE+ALIGNMENT+digest)] + [최근 턴 원문].
- digest: 오래된 턴들을 LLM이 접어 넣는 굴러가는 요약(장기 기억).
  세션 DB의 meta에 커서(compacted_until)와 함께 저장된다.
- 최근 창: 커서 뒤의 아이템은 원문 그대로 보낸다.
- 창 안에서도 오래된 턴의 큰 도구 출력은 규칙으로 스텁 치환한다(무료 다이어트).
  function_call(호출 기록)은 남기므로 모델은 무엇을 했는지 알고, 필요하면 재호출한다.
"""
from __future__ import annotations

import os

# 창 안에서 이 수의 유저 턴보다 오래된 도구 출력은 스텁 치환
STUB_TURNS = int(os.environ.get("AGENT_CTX_STUB_TURNS", "3"))
# 이보다 작은 도구 출력은 치환해도 이득이 없어 그대로 둔다
STUB_MIN_CHARS = int(os.environ.get("AGENT_CTX_STUB_MIN", "500"))
# 컴팩션 후 원문으로 남길 최근 유저 턴 수
KEEP_TURNS = int(os.environ.get("AGENT_CTX_KEEP_TURNS", "8"))
# 커서 밖 유저 턴이 이만큼 쌓이면 컴팩션 발동 (KEEP과의 차이가 1회 접는 양)
TRIGGER_TURNS = int(os.environ.get("AGENT_CTX_TRIGGER_TURNS", "12"))

DIGEST_SYSTEM = """너는 개인 에이전트의 장기 기억을 관리하는 사서다.
[기존 기억]과 [새로 접을 대화]를 받아, 하나의 갱신된 장기 기억으로 통합하라.

남길 것: 내려진 결정과 그 이유, 수정·생성한 파일과 목적, 아직 미해결인 작업,
사용자에 대해 알게 된 사실(선호·프로젝트·목표), 다음에 참조할 핵심 정보.
버릴 것: 일회성 질문과 답, 잡담, 이미 해결된 시행착오의 세부 과정, 도구 출력 원문.

규칙:
- 마크다운 불릿(- )으로 최대 40줄. 오래돼 가치가 떨어진 항목은 통합하거나 지워라.
- 대화에 실제로 있던 사실만 적어라. 지어내지 마라.
- 서론·설명·코드펜스 없이 기억 내용만 출력하라."""


def _is_user_msg(item: dict) -> bool:
    return item.get("type") == "message" and item.get("role") == "user"


def _turn_starts(items: list[dict]) -> list[int]:
    """각 유저 턴이 시작되는 아이템 인덱스."""
    return [i for i, it in enumerate(items) if _is_user_msg(it)]


def count_turns(items: list[dict]) -> int:
    return len(_turn_starts(items))


def prepare_for_send(items: list[dict]) -> list[dict]:
    """전송용 복사본을 만든다. 원본 리스트/아이템은 건드리지 않는다.

    최근 STUB_TURNS 유저 턴보다 오래된 턴의 function_call_output 중
    STUB_MIN_CHARS 이상인 것만 내용을 스텁으로 치환한다.
    """
    total = count_turns(items)
    out: list[dict] = []
    turn = 0  # 현재 아이템이 속한 유저 턴 번호(1-base)
    for it in items:
        if _is_user_msg(it):
            turn += 1
        output = it.get("output") if it.get("type") == "function_call_output" else None
        if (
            output is not None
            and turn <= total - STUB_TURNS
            and len(output) >= STUB_MIN_CHARS
        ):
            stub = (
                f"[오래된 도구 출력 생략 — 원래 {len(output):,}자. "
                "내용이 필요하면 도구를 다시 호출하세요]"
            )
            out.append({**it, "output": stub})
        else:
            out.append(it)
    return out


def should_compact(items: list[dict]) -> bool:
    """커서 밖(원문 창)에 쌓인 유저 턴이 임계치를 넘었는가."""
    return count_turns(items) >= TRIGGER_TURNS


def fold_split(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(접을 부분, 남길 부분)으로 나눈다. 최근 KEEP_TURNS 유저 턴은 남긴다.

    경계는 항상 유저 메시지 시작점이므로 function_call/출력 짝이 갈라지지 않는다.
    """
    starts = _turn_starts(items)
    if len(starts) <= KEEP_TURNS:
        return [], items
    boundary = starts[len(starts) - KEEP_TURNS]
    return items[:boundary], items[boundary:]


def _render(items: list[dict]) -> str:
    """접힐 아이템들을 요약용 대화 전사 텍스트로 바꾼다(도구 출력은 미리보기만)."""
    lines: list[str] = []
    for it in items:
        t = it.get("type")
        if t == "message":
            text = "".join(
                c.get("text", "") for c in it.get("content", []) if isinstance(c, dict)
            ).strip()
            if text:
                who = "사용자" if it.get("role") == "user" else "에이전트"
                lines.append(f"{who}: {text}")
        elif t == "function_call":
            lines.append(f"  · 도구 {it.get('name')}({(it.get('arguments') or '')[:150]})")
        elif t == "function_call_output":
            preview = (it.get("output") or "").replace("\n", " ")[:200]
            lines.append(f"  ↳ {preview}")
    return "\n".join(lines)


def update_digest(complete, old_digest: str, folded: list[dict]) -> str:
    """접힐 턴들을 기존 digest에 통합한 새 digest를 반환한다.

    complete: (system, user) -> str 형태의 1회성 모델 호출(AgentService.complete).
    """
    user = (
        f"[기존 기억]\n{old_digest.strip() or '(없음)'}\n\n"
        f"[새로 접을 대화]\n{_render(folded)}"
    )
    new = (complete(DIGEST_SYSTEM, user) or "").strip()
    if new.startswith("```"):  # 코드펜스 방어
        new = "\n".join(
            ln for ln in new.splitlines() if not ln.strip().startswith("```")
        ).strip()
    return new or old_digest
