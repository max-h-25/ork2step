#!/bin/bash
cd "$(dirname "$0")"

echo "🛑 Stopping ork2step..."

# Stop frontend container
docker compose down 2>/dev/null

# Stop backend process
if [ -f .backend.pid ]; then
  kill $(cat .backend.pid) 2>/dev/null
  rm .backend.pid
fi

echo "✅ Stopped."
sleep 2
