#!/bin/bash

cd "$(dirname "$0")"
PROJ_DIR="$(pwd)"
APP="$PROJ_DIR/ork2step.app"

echo "🚀 ork2step installer"
echo "────────────────────────────────────────"

# Remove quarantine
echo "🔓 Removing macOS quarantine flags..."
xattr -rd com.apple.quarantine "$PROJ_DIR" 2>/dev/null
chmod +x "$PROJ_DIR/start.command" "$PROJ_DIR/stop.command"
chmod +x "$APP/Contents/MacOS/ork2step" 2>/dev/null
echo "✅ Done."

# ── Install backend dependencies natively via conda ───────────────────────
# Find conda
CONDA=""
for candidate in \
    "$HOME/miniconda3/bin/conda" \
    "$HOME/anaconda3/bin/conda" \
    "$HOME/miniforge3/bin/conda" \
    "$HOME/opt/miniconda3/bin/conda" \
    "$HOME/opt/anaconda3/bin/conda" \
    "$HOME/opt/miniforge3/bin/conda" \
    "/opt/homebrew/Caskroom/miniconda/base/bin/conda"; do
  if [ -f "$candidate" ]; then
    CONDA="$candidate"
    break
  fi
done

if [ -n "$CONDA" ]; then
  echo "🐍 Found conda at: $CONDA"
  echo "📦 Creating ork2step conda environment (this takes a few minutes)..."
  "$CONDA" create -n ork2step python=3.11 -y 2>/dev/null || true
  "$CONDA" install -n ork2step -y -c cadquery -c conda-forge cadquery
  # Get the env python path
  ENV_PYTHON=$("$CONDA" run -n ork2step which python)
  "$ENV_PYTHON" -m pip install fastapi "uvicorn[standard]" python-multipart lxml pydantic
  echo "✅ Backend environment ready."
else
  echo "⚠️  conda not found — trying pip install instead..."
  pip3 install cadquery fastapi "uvicorn[standard]" python-multipart lxml pydantic
  echo "✅ Done (pip install)."
fi

# ── Convert iconset → .icns ───────────────────────────────────────────────
ICONSET="$APP/Contents/Resources/AppIcon.iconset"
ICNS="$APP/Contents/Resources/AppIcon.icns"
if [ -d "$ICONSET" ]; then
  echo "🎨 Generating app icon..."
  iconutil -c icns "$ICONSET" -o "$ICNS" 2>/dev/null && echo "✅ Icon created."
fi
touch "$APP"

# ── Desktop icon (copy with hardcoded path) ───────────────────────────────
DESKTOP="$HOME/Desktop/ork2step.app"
echo "🖥  Adding ork2step to Desktop..."
rm -rf "$DESKTOP"
cp -r "$APP" "$DESKTOP"
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
echo "✅ Installation complete!"
echo "Double-click the ork2step icon on your Desktop to launch."
echo "────────────────────────────────────────"
sleep 3
