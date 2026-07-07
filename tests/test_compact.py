"""compact.py 순수 함수 테스트. 실행: python tests/test_compact.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.session import compact


def user(text: str) -> dict:
    return {"type": "message", "role": "user",
            "content": [{"type": "input_text", "text": text}]}


def assistant(text: str) -> dict:
    return {"type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": text}]}


def call(cid: str, name: str = "read_file") -> dict:
    return {"type": "function_call", "call_id": cid, "name": name,
            "arguments": '{"path": "x.py"}'}


def output(cid: str, size: int) -> dict:
    return {"type": "function_call_output", "call_id": cid, "output": "x" * size}


def turn(n: int, with_tool: bool = True, out_size: int = 1000) -> list[dict]:
    items = [user(f"질문 {n}"),
             {"type": "reasoning", "id": f"rs{n}", "encrypted_content": "blob"}]
    if with_tool:
        items += [call(f"c{n}"), output(f"c{n}", out_size)]
    items.append(assistant(f"답변 {n}"))
    return items


def make_history(turns: int, **kw) -> list[dict]:
    items: list[dict] = []
    for n in range(1, turns + 1):
        items += turn(n, **kw)
    return items


def test_prepare_for_send():
    compact.STUB_TURNS, compact.STUB_MIN_CHARS = 3, 500
    items = make_history(5, out_size=1000)
    sent = compact.prepare_for_send(items)
    # 오래된 턴(1·2)의 reasoning은 제외, 최근 3턴 것만 남는다
    assert [it["id"] for it in sent if it["type"] == "reasoning"] == ["rs3", "rs4", "rs5"]
    assert len(sent) == len(items) - 2
    outs = [it for it in sent if it["type"] == "function_call_output"]
    # 5턴 중 최근 3턴(3,4,5)은 원본, 오래된 1·2턴은 스텁
    assert outs[0]["output"].startswith("[오래된 도구 출력 생략")
    assert outs[1]["output"].startswith("[오래된 도구 출력 생략")
    assert outs[2]["output"] == "x" * 1000
    assert outs[4]["output"] == "x" * 1000
    # 원본 리스트는 불변
    assert items[3]["output"] == "x" * 1000
    # 작은 출력은 오래돼도 그대로
    small = make_history(5, out_size=100)
    assert all(o["output"] == "x" * 100
               for o in compact.prepare_for_send(small)
               if o["type"] == "function_call_output")


def test_fold_split():
    compact.KEEP_TURNS = 8
    items = make_history(12)
    folded, kept = compact.fold_split(items)
    assert compact.count_turns(folded) == 4
    assert compact.count_turns(kept) == 8
    assert folded + kept == items
    # 경계는 유저 메시지 시작점 → call/output 짝이 안 갈라짐
    assert kept[0]["type"] == "message" and kept[0]["role"] == "user"
    # 접을 게 없으면 그대로
    few = make_history(5)
    assert compact.fold_split(few) == ([], few)


def test_should_compact():
    compact.TRIGGER_TURNS = 12
    assert not compact.should_compact(make_history(11))
    assert compact.should_compact(make_history(12))


def test_update_digest():
    def fake_complete(system, user_text):
        assert "[기존 기억]" in user_text and "질문 1" in user_text
        return "```\n- 요약된 기억\n```"

    new = compact.update_digest(fake_complete, "- 예전 기억", make_history(3))
    assert new == "- 요약된 기억"  # 코드펜스 제거됨
    # 모델이 빈 응답이면 기존 digest 유지
    assert compact.update_digest(lambda s, u: "", "- 예전", make_history(1)) == "- 예전"


if __name__ == "__main__":
    for fn in [test_prepare_for_send, test_fold_split, test_should_compact, test_update_digest]:
        fn()
        print(f"OK {fn.__name__}")
    print("모든 테스트 통과")
