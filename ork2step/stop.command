#!/bin/bash
cd "$(dirname "$0")"
echo "🛑 Stopping ork2step..."
docker compose down
echo "✅ Stopped."
sleep 2
