#!/bin/bash

cd "$(dirname "$0")"
PROJ_DIR="$(pwd)"

echo "🚀 ork2step launcher"
echo "────────────────────────────────────────"

# ── 1. Launch Docker Desktop if not running ───────────────────────────────
if ! docker info &>/dev/null; then
  echo "⏳ Starting Docker Desktop..."
  open -a "Docker"
  WAIT=0
  until docker info &>/dev/null; do
    sleep 2
    WAIT=$((WAIT + 2))
    if [ $WAIT -ge 60 ]; then
      echo "❌ Docker didn't start in time. Please open it manually."
      read -n 1 -s -r -p "Press any key to close..."
      exit 1
    fi
    echo "   Waiting for Docker... (${WAIT}s)"
  done
  echo "✅ Docker is ready."
else
  echo "✅ Docker already running."
fi

# ── 2. Check conda/python environment ─────────────────────────────────────
# Try to find conda python with cadquery
PYTHON=""
for candidate in \
    "$HOME/miniconda3/envs/ork2step/bin/python" \
    "$HOME/anaconda3/envs/ork2step/bin/python" \
    "$HOME/miniforge3/envs/ork2step/bin/python" \
    "$HOME/opt/miniconda3/envs/ork2step/bin/python" \
    "$HOME/opt/anaconda3/envs/ork2step/bin/python" \
    "$HOME/opt/miniforge3/envs/ork2step/bin/python"; do
  if [ -f "$candidate" ]; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  # Fall back to system python
  PYTHON=$(which python3)
fi

echo "🐍 Using Python: $PYTHON"

# ── 3. Start backend natively ─────────────────────────────────────────────
echo "⏳ Starting backend..."
cd "$PROJ_DIR/backend"
"$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo $BACKEND_PID > "$PROJ_DIR/.backend.pid"

# Wait for backend to be ready
WAIT=0
until curl -s http://localhost:8000/health | grep -q "ok"; do
  sleep 1
  WAIT=$((WAIT + 1))
  if [ $WAIT -ge 30 ]; then
    echo "❌ Backend failed to start."
    kill $BACKEND_PID 2>/dev/null
    exit 1
  fi
done
echo "✅ Backend ready."

# ── 4. Start frontend in Docker ───────────────────────────────────────────
cd "$PROJ_DIR"
echo "⏳ Starting frontend..."
docker compose up -d --build

# ── 5. Open browser ───────────────────────────────────────────────────────
sleep 2
echo "✅ ork2step is ready!"
open http://localhost:3000

echo ""
echo "App running at http://localhost:3000"
echo "Double-click stop.command when done."
echo "────────────────────────────────────────"
