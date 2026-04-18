#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

APP_NAME="PhotoBurstAnalyzer"
SPEC="packaging/pyinstaller/PhotoBurstAnalyzer.spec"
VENV=".venv_x86_64"

echo "[*] Root: $ROOT"
echo "[*] Building x86_64 under Rosetta"

if ! /usr/bin/pgrep oahd >/dev/null 2>&1; then
  echo "[*] Rosetta not detected (oahd not running). Installing Rosetta..."
  sudo softwareupdate --install-rosetta --agree-to-license
fi

INTEL_PY="/usr/local/opt/python@3.12/bin/python3.12"
if [[ ! -x "$INTEL_PY" ]]; then
  echo "[!] Intel Homebrew Python not found at $INTEL_PY"
  echo "    Install Intel Homebrew + python@3.12, or run build_x86_64.sh on an Intel Mac."
  exit 3
fi

arch -x86_64 "$INTEL_PY" -c "import platform; print('[*] Intel python arch:', platform.machine())"

echo "[*] Recreating venv: $VENV"
rm -rf "$VENV"
arch -x86_64 "$INTEL_PY" -m venv "$VENV"

arch -x86_64 /bin/bash -c "source '$VENV/bin/activate' && python -m pip install -U pip wheel && python -m pip install 'pyinstaller<7,>=6.0' 'pillow>=10.0.0' 'pyqt5==5.15.10' && deactivate"

echo "[*] Ensuring .icns exists"
"$ROOT/packaging/macos/make_icns.sh"

rm -rf build dist
mkdir -p dist

echo "[*] Building (x86_64 via Rosetta)..."
arch -x86_64 /bin/bash -c "source '$VENV/bin/activate' && pyinstaller '$SPEC' --noconfirm && deactivate"

if [[ -d "dist/${APP_NAME}.app" ]]; then
  mv "dist/${APP_NAME}.app" "dist/${APP_NAME}-macOS-x86_64.app"
  echo "[✓] Output: dist/${APP_NAME}-macOS-x86_64.app"
else
  echo "[!] Expected dist/${APP_NAME}.app not found"
  ls -la dist || true
  exit 2
fi
