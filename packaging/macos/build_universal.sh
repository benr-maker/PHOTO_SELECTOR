#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

APP_NAME="PhotoBurstAnalyzer"
ARM_APP="dist/${APP_NAME}-macOS-arm64.app"
X86_APP="dist/${APP_NAME}-macOS-x86_64.app"
UNI_APP="dist/${APP_NAME}-macOS-universal.app"

if [[ ! -d "$ARM_APP" || ! -d "$X86_APP" ]]; then
  echo "[!] Missing arm64 or x86_64 apps in dist/"
  echo "    Need: $ARM_APP and $X86_APP"
  exit 2
fi

rm -rf "$UNI_APP"
cp -R "$ARM_APP" "$UNI_APP"

ARM_BIN="$ARM_APP/Contents/MacOS/$APP_NAME"
X86_BIN="$X86_APP/Contents/MacOS/$APP_NAME"
OUT_BIN="$UNI_APP/Contents/MacOS/$APP_NAME"

echo "[*] Verifying binaries:"
file "$ARM_BIN" || true
file "$X86_BIN" || true

echo "[*] Merging with lipo..."
lipo -create "$ARM_BIN" "$X86_BIN" -output "$OUT_BIN"

echo "[*] Result:"
file "$OUT_BIN" || true

# lipo replaces the main executable, which invalidates PyInstaller's
# ad-hoc signature. Re-sign the entire bundle so spctl passes.
echo "[*] Re-signing universal bundle (required after lipo)..."
codesign --force --deep --sign - "$UNI_APP"
echo "[✓] Output: $UNI_APP"
