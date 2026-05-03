#!/bin/bash

# ── ork2step launcher ──────────────────────────────────────────────────────
# Double-click this file to start ork2step.
# It will launch Docker Desktop if needed, start the containers,
# and open http://localhost:3000 in your default browser.
# ──────────────────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

echo "🚀 ork2step launcher"
echo "────────────────────────────────────────"

# ── 1. Launch Docker Desktop if it isn't running ──────────────────────────
if ! docker info &>/dev/null; then
  echo "⏳ Starting Docker Desktop..."
  open -a "Docker"

  # Wait up to 60 seconds for the engine to be ready
  WAIT=0
  until docker info &>/dev/null; do
    sleep 2
    WAIT=$((WAIT + 2))
    if [ $WAIT -ge 60 ]; then
      echo ""
      echo "❌ Docker didn't start in time."
      echo "   Please open Docker Desktop manually and try again."
      read -n 1 -s -r -p "Press any key to close..."
      exit 1
    fi
    echo "   Still waiting for Docker... (${WAIT}s)"
  done
  echo "✅ Docker is ready."
else
  echo "✅ Docker is already running."
fi

echo ""

# ── 2. Start the containers ───────────────────────────────────────────────
echo "⏳ Starting ork2step containers..."
docker compose up --build -d

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Failed to start containers. Check the output above for errors."
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi

echo ""

# ── 3. Wait for the backend to be healthy ─────────────────────────────────
echo "⏳ Waiting for the app to be ready..."
WAIT=0
until curl -s http://localhost:8000/health | grep -q "ok"; do
  sleep 2
  WAIT=$((WAIT + 2))
  if [ $WAIT -ge 60 ]; then
    echo "⚠️  App is taking longer than expected — opening browser anyway."
    break
  fi
done

echo "✅ ork2step is ready!"
echo ""

# ── 4. Open in default browser ────────────────────────────────────────────
echo "🌐 Opening http://localhost:3000 ..."
open http://localhost:3000

echo ""
echo "────────────────────────────────────────"
echo "ork2step is running."
echo "To stop it, run:  docker compose down"
echo "Or double-click stop.command"
echo "────────────────────────────────────────"
