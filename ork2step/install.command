#!/bin/bash

cd "$(dirname "$0")"
PROJ_DIR="$(pwd)"
APP="$PROJ_DIR/ork2step.app"

echo "🚀 ork2step installer"
echo "────────────────────────────────────────"

# Remove quarantine from everything
echo "🔓 Removing macOS quarantine flags..."
xattr -rd com.apple.quarantine "$PROJ_DIR" 2>/dev/null
echo "✅ Done."

# Make all scripts executable
chmod +x "$PROJ_DIR/start.command"
chmod +x "$PROJ_DIR/stop.command"
chmod +x "$APP/Contents/MacOS/ork2step"

# Convert iconset → .icns
ICONSET="$APP/Contents/Resources/AppIcon.iconset"
ICNS="$APP/Contents/Resources/AppIcon.icns"
if [ -d "$ICONSET" ]; then
  echo "🎨 Generating app icon..."
  iconutil -c icns "$ICONSET" -o "$ICNS" 2>/dev/null && echo "✅ Icon created."
fi

touch "$APP"

# Copy (not symlink) the app to Desktop so paths resolve correctly
DESKTOP="$HOME/Desktop/ork2step.app"
echo "🖥  Adding ork2step to Desktop..."
rm -rf "$DESKTOP"
cp -r "$APP" "$DESKTOP"

# Update the executable inside the Desktop copy to use absolute path
cat > "$DESKTOP/Contents/MacOS/ork2step" << INNEREOF
#!/bin/bash
osascript -e "tell application \"Terminal\"
    activate
    do script \"cd '${PROJ_DIR}' && ./start.command\"
end tell"
INNEREOF
chmod +x "$DESKTOP/Contents/MacOS/ork2step"
xattr -rd com.apple.quarantine "$DESKTOP" 2>/dev/null

echo "✅ Desktop icon created."
echo ""
echo "────────────────────────────────────────"
echo "✅ Setup complete!"
echo ""
echo "Double-click the ork2step icon on your Desktop to launch."
echo "────────────────────────────────────────"
sleep 3
