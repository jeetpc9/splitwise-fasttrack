#!/usr/bin/env bash
# Build "Splitwise FastTrack.app" in the project root (double-click or Dock).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Splitwise FastTrack"
APP_DIR="$ROOT/$APP_NAME.app"
ICON_SRC="$ROOT/scripts/app-icon.png"
OLD_APP="$ROOT/Splitwise Bulk Upload.app"

echo "Creating $APP_NAME.app …"

rm -rf "$APP_DIR" "$OLD_APP"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/MacOS/launcher" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail

APP_BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="$(cd "$APP_BUNDLE/.." && pwd)"
GUI="$PROJECT_ROOT/.venv/bin/splitwise-fasttrack"
if [[ ! -x "$GUI" ]]; then
  GUI="$PROJECT_ROOT/.venv/bin/splitwise-bulk-gui"
fi

alert() {
  /usr/bin/osascript -e "display alert \"Splitwise FastTrack\" message \"$1\" as warning"
}

cd "$PROJECT_ROOT"

if [[ ! -x "$GUI" ]]; then
  alert "Virtual env not found. Open Terminal in the project folder and run: ./scripts/setup.sh"
  exit 1
fi

export PATH="$PROJECT_ROOT/.venv/bin:$PATH"

# Prefer native Apple Silicon — avoids Rosetta / "Intel" app warnings on future macOS.
if [[ "$(uname -m)" == "arm64" ]]; then
  exec /usr/bin/arch -arm64 "$GUI"
fi
exec "$GUI"
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/launcher"

if [[ -f "$ICON_SRC" ]]; then
  ICONSET="$ROOT/scripts/.app-icon.iconset"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$ICON_SRC" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$ICON_SRC" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/AppIcon.icns"
  rm -rf "$ICONSET"
fi

cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>en</string>
	<key>CFBundleExecutable</key>
	<string>launcher</string>
	<key>CFBundleIdentifier</key>
	<string>com.jeet.splitwise-fasttrack</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>Splitwise FastTrack</string>
	<key>CFBundleDisplayName</key>
	<string>Splitwise FastTrack</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>0.1.0</string>
	<key>CFBundleVersion</key>
	<string>1</string>
	<key>LSMinimumSystemVersion</key>
	<string>11.0</string>
	<key>LSArchitecturePriority</key>
	<array>
		<string>arm64</string>
	</array>
	<key>NSHighResolutionCapable</key>
	<true/>
</dict>
</plist>
PLIST

if [[ -f "$APP_DIR/Contents/Resources/AppIcon.icns" ]]; then
  /usr/bin/plutil -insert CFBundleIconFile -string AppIcon "$APP_DIR/Contents/Info.plist"
fi

echo ""
echo "Done: $APP_DIR"
echo ""
echo "Next steps:"
echo "  1. Double-click \"$APP_NAME.app\" in Finder"
echo "  2. Or drag it to the Dock for one-click launch"
echo "  3. Optional: drag to /Applications or Desktop"
