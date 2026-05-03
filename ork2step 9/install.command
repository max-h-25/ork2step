#!/bin/bash

# ── ork2step installer ─────────────────────────────────────────────────────
# Run this once after unzipping to:
#   1. Convert the icon to .icns format
#   2. Register the .app so macOS treats it as a real application
#   3. Add a shortcut to your Desktop
# ──────────────────────────────────────────────────────────────────────────

cd "$(dirname "$0")"
PROJ_DIR="$(pwd)"
APP="$PROJ_DIR/ork2step.app"

echo "🚀 ork2step installer"
echo "────────────────────────────────────────"

# ── 1. Convert iconset → .icns ────────────────────────────────────────────
ICONSET="$APP/Contents/Resources/AppIcon.iconset"
ICNS="$APP/Contents/Resources/AppIcon.icns"

if [ -d "$ICONSET" ]; then
  echo "🎨 Generating app icon..."
  iconutil -c icns "$ICONSET" -o "$ICNS" 2>/dev/null && \
    echo "✅ Icon created." || \
    echo "⚠️  Icon conversion skipped (will use default icon)."
fi

# ── 2. Remove quarantine flag so macOS doesn't block it ───────────────────
echo "🔓 Removing quarantine flag..."
xattr -rd com.apple.quarantine "$APP" 2>/dev/null
xattr -rd com.apple.quarantine "$PROJ_DIR/start.command" 2>/dev/null
xattr -rd com.apple.quarantine "$PROJ_DIR/stop.command" 2>/dev/null
echo "✅ Done."

# ── 3. Tell Finder to refresh the icon ────────────────────────────────────
touch "$APP"

# ── 4. Create Desktop shortcut ────────────────────────────────────────────
DESKTOP="$HOME/Desktop/ork2step.app"
if [ ! -e "$DESKTOP" ]; then
  echo "🖥  Adding shortcut to Desktop..."
  ln -s "$APP" "$DESKTOP"
  echo "✅ Desktop icon created."
else
  echo "✅ Desktop icon already exists."
fi

echo ""
echo "────────────────────────────────────────"
echo "✅ Installation complete!"
echo ""
echo "You can now:"
echo "  • Double-click 'ork2step' on your Desktop to launch"
echo "  • Or double-click start.command in this folder"
echo ""
echo "The app will:"
echo "  → Start Docker Desktop automatically"
echo "  → Launch the ork2step containers"
echo "  → Open http://localhost:3000 in your browser"
echo "────────────────────────────────────────"
sleep 3
