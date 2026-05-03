#!/bin/bash

cd "$(dirname "$0")"

echo "🚀 ork2step launcher"
echo "────────────────────────────────────────"

# Launch Docker Desktop if not running
if ! docker info &>/dev/null; then
  echo "⏳ Starting Docker Desktop..."
  open -a "Docker"
  WAIT=0
  until docker info &>/dev/null; do
    sleep 2
    WAIT=$((WAIT + 2))
    if [ $WAIT -ge 60 ]; then
      echo "❌ Docker didn't start in time."
      echo "   Please open Docker Desktop manually and try again."
      read -n 1 -s -r -p "Press any key to close..."
      exit 1
    fi
    echo "   Waiting for Docker... (${WAIT}s)"
  done
  echo "✅ Docker is ready."
else
  echo "✅ Docker already running."
fi

echo "⏳ Starting ork2step..."
docker compose up --build -d

if [ $? -ne 0 ]; then
  echo "❌ Failed to start. Check the output above."
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi

echo "⏳ Waiting for app to be ready..."
WAIT=0
until curl -s http://localhost:8000/health | grep -q "ok"; do
  sleep 2
  WAIT=$((WAIT + 2))
  if [ $WAIT -ge 60 ]; then
    echo "⚠️  Taking longer than expected — opening browser anyway."
    break
  fi
done

echo "✅ ork2step is ready!"
open http://localhost:3000

echo ""
echo "App is running at http://localhost:3000"
echo "Double-click stop.command when you're done."
echo "────────────────────────────────────────"
