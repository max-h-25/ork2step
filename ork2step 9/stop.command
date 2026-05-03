#!/bin/bash

# ── ork2step stopper ───────────────────────────────────────────────────────
cd "$(dirname "$0")"

echo "🛑 Stopping ork2step..."
docker compose down
echo "✅ ork2step stopped."
sleep 2
