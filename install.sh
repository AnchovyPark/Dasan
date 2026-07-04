#!/usr/bin/env bash
# Dasan 원격 설치 (macOS/Linux).
#   curl -fsSL https://raw.githubusercontent.com/AnchovyPark/Dasan/main/install.sh | bash
#
# GitHub에서 최신 Dasan을 받아 pipx로 전역 설치한다. `dasan` 명령이 PATH에 놓인다.
# 개발용(이 리포에서 직접 수정)은 이 스크립트가 아니라 `pip install -e .` 를 쓴다.
set -euo pipefail

REPO="https://github.com/AnchovyPark/Dasan.git"
BRANCH="${DASAN_BRANCH:-main}"

# 1) 파이썬 확인
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "!! python3가 필요합니다. 먼저 설치하세요: https://www.python.org/downloads/" >&2
  exit 1
fi
echo "==> Python: $("$PY" --version 2>&1) ($PY)"

# 2) pipx 확보 (없으면 사용자 영역에 설치)
if ! "$PY" -m pipx --version >/dev/null 2>&1; then
  echo "==> pipx 설치 중..."
  "$PY" -m pip install --user -q pipx
  "$PY" -m pipx ensurepath >/dev/null 2>&1 || true
fi

# 3) Dasan 설치 (이미 있으면 최신으로 교체)
echo "==> Dasan 설치 중  (git+$REPO@$BRANCH)"
"$PY" -m pipx install --force "git+$REPO@$BRANCH"

echo ""
echo "==> 설치 완료!"
echo "    새 터미널을 연 뒤:   dasan login   →   dasan start"
echo "    ('dasan' 이 안 잡히면 새 터미널을 여세요. pipx가 PATH를 갱신합니다.)"
