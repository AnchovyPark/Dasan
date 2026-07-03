"""Anthropic 모델 호출을 통일된 인터페이스로 감싸는 어댑터.

설계 원칙(프로바이더 추상화): 루프 코드는 anthropic SDK의 타입/메시지
포맷을 직접 알지 못한다. 루프는 아래 정규화된 타입(ModelResponse,
ToolCall)과 어댑터의 메시지 빌더 헬퍼만 사용한다. 프로바이더를 바꾸려면
이 파일만 교체하면 된다.
"""
from __future__ import annotations

from dataclasses import dataclass

import anthropic

# 대화를 이어가려면 모델이 돌려준 assistant content 블록을 그대로 다시
# 넣어줘야 한다. 루프는 그 원본(raw_content)을 불투명(opaque)하게 취급하고,
# 텍스트/도구호출만 정규화된 형태로 들여다본다.


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ModelResponse:
    text: str
    tool_calls: list[ToolCall]
    raw_content: list[dict]  # 프로바이더 네이티브 블록(재전송용, 루프는 안 들여다봄)
    stop_reason: str | None


class AnthropicAdapter:
    def __init__(self, api_key: str | None, model: str, max_tokens: int) -> None:
        # api_key가 None이면 SDK 기본 해석(환경변수/ant 프로필)에 맡긴다.
        self._client = (
            anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        )
        self._model = model
        self._max_tokens = max_tokens

    def call(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
    ) -> ModelResponse:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
            "tools": tools or [],
        }
        if system:
            kwargs["system"] = system

        resp = self._client.messages.create(**kwargs)

        text = "".join(b.text for b in resp.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=dict(b.input))
            for b in resp.content
            if b.type == "tool_use"
        ]
        raw_content = [b.model_dump() for b in resp.content]
        return ModelResponse(
            text=text,
            tool_calls=tool_calls,
            raw_content=raw_content,
            stop_reason=resp.stop_reason,
        )

    # --- 메시지 빌더 (프로바이더별 포맷을 여기서 캡슐화) ---
    # 루프가 messages.extend(...) 하므로 항상 아이템 리스트를 반환한다.

    @staticmethod
    def user_message(text: str) -> list[dict]:
        return [{"role": "user", "content": text}]

    @staticmethod
    def assistant_message(resp: ModelResponse) -> list[dict]:
        return [{"role": "assistant", "content": resp.raw_content}]

    @staticmethod
    def tool_result_message(results: list[tuple[ToolCall, str, bool]]) -> list[dict]:
        blocks = [
            {
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": output,
                "is_error": is_error,
            }
            for tc, output, is_error in results
        ]
        return [{"role": "user", "content": blocks}]
