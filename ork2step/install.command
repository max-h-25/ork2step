#!/bin/bash

cd "$(dirname "$0")"
PROJ_DIR="$(pwd)"
APP="$PROJ_DIR/ork2step.app"

echo "🚀 ork2step installer"
echo "────────────────────────────────────────"

# Remove quarantine from everything in the project
echo "🔓 Removing macOS quarantine flags..."
xattr -rd com.apple.quarantine "$PROJ_DIR" 2>/dev/null
echo "✅ Done."

# Make all scripts executable
chmod +x "$PROJ_DIR/start.command"
chmod +x "$PROJ_DIR/stop.command"
chmod +x "$APP/Contents/MacOS/ork2step" 2>/dev/null

# Convert iconset → .icns
ICONSET="$APP/Contents/Resources/AppIcon.iconset"
ICNS="$APP/Contents/Resources/AppIcon.icns"
if [ -d "$ICONSET" ]; then
  echo "🎨 Generating app icon..."
  iconutil -c icns "$ICONSET" -o "$ICNS" 2>/dev/null && echo "✅ Icon created."
fi

# Touch app so Finder refreshes icon
touch "$APP"

# Create Desktop shortcut
DESKTOP="$HOME/Desktop/ork2step.app"
if [ ! -e "$DESKTOP" ]; then
  echo "🖥  Adding ork2step to Desktop..."
  ln -s "$APP" "$DESKTOP"
  echo "✅ Desktop icon created."
else
  echo "✅ Desktop icon already exists."
fi

echo ""
echo "────────────────────────────────────────"
echo "✅ Setup complete!"
echo ""
echo "Double-click the ork2step icon on your Desktop to launch."
echo "────────────────────────────────────────"
sleep 3
