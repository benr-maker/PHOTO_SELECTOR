#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

APP_PATH="${1:-}"
if [[ -z "$APP_PATH" ]]; then
  echo "Usage: $0 dist/PhotoBurstAnalyzer-macOS-arm64.app"
  exit 1
fi
if [[ ! -d "$APP_PATH" ]]; then
  echo "[!] App not found: $APP_PATH"
  exit 2
fi

APP_NAME="PhotoBurstAnalyzer"
DMG_OUT="dist/PhotoBurstAnalyzer.dmg"
VOL="PhotoBurstAnalyzer"

TMPDIR="$(mktemp -d)"
STAGE="$TMPDIR/$VOL"
mkdir -p "$STAGE"

# Always install as "PhotoBurstAnalyzer.app" regardless of source name
APP_IN_STAGE="$STAGE/${APP_NAME}.app"
cp -R "$APP_PATH" "$APP_IN_STAGE"

# Strip quarantine and re-sign ad-hoc. Users may still need right-click
# → Open on first launch on macOS 13+ without a paid Developer ID cert.
xattr -cr "$APP_IN_STAGE"
codesign --force --deep --sign - "$APP_IN_STAGE" 2>/dev/null || true

# Touch the bundle so Finder picks up the icon immediately on mount
touch "$APP_IN_STAGE"

ln -s /Applications "$STAGE/Applications"

rm -f "$DMG_OUT"
hdiutil create -volname "$VOL" -srcfolder "$STAGE" -ov -format UDZO "$DMG_OUT" >/dev/null

rm -rf "$TMPDIR"
echo "[✓] DMG: $DMG_OUT"
