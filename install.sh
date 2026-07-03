#!/usr/bin/env bash
# Dasan 설치: 패키지를 설치하고 `dasan` 명령을 (가능하면) 전역으로 연결한다.
set -euo pipefail

cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

echo "==> 패키지 설치 (pip install -e .)"
"$PY" -m pip install -e . -q

SCRIPTS_DIR="$("$PY" -c 'import sysconfig; print(sysconfig.get_path("scripts"))')"
DASAN_BIN="$SCRIPTS_DIR/dasan"

if [ ! -x "$DASAN_BIN" ]; then
  echo "!! 설치 후 dasan 실행파일을 찾지 못했습니다: $DASAN_BIN" >&2
  exit 1
fi

# 이미 PATH에서 dasan이 잡히면 끝
if command -v dasan >/dev/null 2>&1; then
  echo "==> 완료: 'dasan' 이 이미 PATH에서 잡힙니다 ($(command -v dasan))"
  echo "    다음 단계: dasan login"
  exit 0
fi

# PATH에 있는 '쓰기 가능' bin 폴더를 찾아 심링크
link_into() {
  local dir="$1"
  case ":$PATH:" in *":$dir:"*) ;; *) return 1 ;; esac   # PATH에 있어야
  [ -d "$dir" ] && [ -w "$dir" ] || return 1              # 존재 + 쓰기 가능
  ln -sf "$DASAN_BIN" "$dir/dasan" || return 1
  echo "==> 심링크 생성: $dir/dasan -> $DASAN_BIN"
  return 0
}

for d in /usr/local/bin /opt/homebrew/bin "$HOME/.local/bin"; do
  if link_into "$d"; then
    echo "==> 완료: 'dasan' 전역 사용 가능"
    echo "    다음 단계: dasan login"
    exit 0
  fi
done

# 심링크 걸 곳이 없으면 PATH 안내
echo "==> pip 스크립트 폴더가 PATH에 없어 자동 연결에 실패했습니다."
echo "    아래 한 줄을 ~/.zshrc 에 추가하고 새 터미널을 여세요:"
echo ""
echo "        export PATH=\"$SCRIPTS_DIR:\$PATH\""
echo ""
echo "    (당장은 'python3 -m agent.main <인자>' 로도 동일하게 쓸 수 있습니다.)"
