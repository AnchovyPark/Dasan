"""도구 등록 + 스키마 노출 + 실행.

설계 원칙:
- 도구 등록 ≠ 노출: 레지스트리에 등록해도, 루프에 넘길 도구는
  schemas(names)로 명시적으로 골라 노출한다.
- 도구 계약: 모든 도구는 Pydantic 모델로 입력을 검증하고, 검증 실패는
  예외가 아니라 (에러문자열, is_error=True)로 돌려 모델이 스스로 고치게 한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Type

from pydantic import BaseModel, ValidationError


@dataclass
class Tool:
    name: str
    description: str
    input_model: Type[BaseModel]
    run: Callable[[BaseModel], str]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"이미 등록된 도구입니다: {tool.name}")
        self._tools[tool.name] = tool

    def schemas(self, names: list[str]) -> list[dict]:
        """노출할 도구만 골라 모델용 스키마 목록으로 반환."""
        out = []
        for name in names:
            tool = self._tools[name]
            schema = tool.input_model.model_json_schema()
            schema.pop("title", None)
            out.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": schema,
                }
            )
        return out

    def execute(self, name: str, raw_input: dict) -> tuple[str, bool]:
        """도구 실행. 반환: (출력문자열, is_error)."""
        tool = self._tools.get(name)
        if tool is None:
            return (f"알 수 없는 도구입니다: {name}", True)
        try:
            parsed = tool.input_model(**raw_input)
        except ValidationError as e:
            return (f"{name} 입력이 유효하지 않습니다: {e}", True)
        try:
            return (tool.run(parsed), False)
        except Exception as e:  # 도구 실행 실패도 대화로 되돌려준다
            return (f"{name} 실행 실패: {e}", True)
