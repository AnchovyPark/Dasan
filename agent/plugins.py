"""Plugin 로더 — 설치된 외부 패키지가 dasan agent에 '도구(capability)'를 심는다.

dasan을 모놀리식 앱이 아니라 platform으로 본다: core는 파일/명령 같은 기본 도구만
갖고, wiki 같은 능력은 별도 git·별도 패키지(plugin)로 분리해 붙인다. bongsu·discord
같은 '창구(surface)'는 밖에서 API로 호출하므로 plugin이 아니다 — plugin은 프로세스
안으로 들어와 도구를 늘리는 in-process 확장만 가리킨다.

plugin 계약 (남들이 이걸 보고 구현한다):
  1) 패키지가 entry point를 광고한다:
         [project.entry-points."dasan.plugins"]
         wiki = "dasan_wiki:register"
  2) 그 register는 다음 시그니처를 만족한다:
         def register(registry: ToolRegistry, ctx: PluginContext) -> list[str]:
             registry.register(make_my_tool(ctx.workspace))
             return ["my_tool"]        # 노출할 도구 이름들
  ctx로 config·workspace를 물려주고, plugin은 자기 설정(vault 경로 등)은 자기
  환경변수에서 읽는다. 한 plugin이 터져도 core는 죽지 않고 경고 후 넘어간다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .config import Config
from .tools.registry import ToolRegistry
from .workspace import Workspace

PLUGIN_GROUP = "dasan.plugins"


@dataclass(frozen=True)
class PluginContext:
    """plugin이 도구를 만들 때 물려받는 core 자원."""
    config: Config
    workspace: Workspace


def _discover() -> list:
    """설치된 배포판에서 dasan.plugins entry point들을 모은다(3.10~ 호환)."""
    from importlib.metadata import entry_points

    eps = entry_points()
    if hasattr(eps, "select"):  # 3.10+ SelectableGroups / 3.12+ EntryPoints
        return list(eps.select(group=PLUGIN_GROUP))
    return list(eps.get(PLUGIN_GROUP, []))  # 구형 폴백


def load_plugins(
    registry: ToolRegistry,
    ctx: PluginContext,
    *,
    entries: list | None = None,
) -> list[str]:
    """설치된 plugin들의 register를 호출해 도구를 등록하고, 노출할 이름 목록을 반환.

    entries: 테스트용 주입구(각 항목은 .name 과 .load()를 가진 entry point 유사 객체).
             없으면 실제 설치된 entry point를 디스커버한다.
    DASAN_DISABLE_PLUGINS 가 설정되면 아무 plugin도 로드하지 않는다.
    """
    if os.environ.get("DASAN_DISABLE_PLUGINS"):
        return []

    eps = entries if entries is not None else _discover()
    exposed: list[str] = []
    for ep in eps:
        name = getattr(ep, "name", "?")
        try:
            register = ep.load()
            names = register(registry, ctx) or []
            exposed.extend(names)
        except Exception as e:  # 깨진 plugin이 core를 죽이지 않게
            print(f"[plugin] '{name}' 로드 실패라 건너뜁니다: {e}")
    return exposed
