# Dasan 원격 설치 (Windows PowerShell).
#   irm https://raw.githubusercontent.com/AnchovyPark/Dasan/main/install.ps1 | iex
#
# GitHub에서 최신 Dasan을 받아 pipx로 전역 설치한다. `dasan` 명령이 PATH에 놓인다.
# 개발용(이 리포에서 직접 수정)은 이 스크립트가 아니라 `pip install -e .` 를 쓴다.
$ErrorActionPreference = 'Stop'

$Repo = 'https://github.com/AnchovyPark/Dasan.git'
$Branch = if ($env:DASAN_BRANCH) { $env:DASAN_BRANCH } else { 'main' }

# 1) 파이썬 확인
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $py) {
  Write-Error 'Python이 필요합니다. 먼저 설치하세요: https://www.python.org/downloads/'
  exit 1
}
Write-Host "==> Python: $(& $py --version) ($py)"

# 2) pipx 확보 (없으면 사용자 영역에 설치)
& $py -m pipx --version *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host '==> pipx 설치 중...'
  & $py -m pip install --user -q pipx
  & $py -m pipx ensurepath *> $null
}

# 3) Dasan 설치 (이미 있으면 최신으로 교체)
Write-Host "==> Dasan 설치 중  (git+$Repo@$Branch)"
& $py -m pipx install --force "git+$Repo@$Branch"

Write-Host ''
Write-Host '==> 설치 완료!'
Write-Host '    새 터미널을 연 뒤:   dasan login   ->   dasan start'
Write-Host "    ('dasan' 이 안 잡히면 새 터미널을 여세요. pipx가 PATH를 갱신합니다.)"
