#!/bin/bash
# Rinha Clinic — start server + tunnel
# Usage: ./start.sh

set -e
cd "$(dirname "$0")"

VENV=".venv/bin/python"

echo "=== Rinha Clinic ==="
echo ""

# Kill old instances
pkill -f "uvicorn.*rinha" 2>/dev/null || true
pkill -f "ssh.*localhost.run" 2>/dev/null || true
sleep 1

# Find Python
if [ ! -f "$VENV" ]; then
    echo "ERROR: .venv not found. Run: python3.12 -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

# Check .env has keys
source <(grep -E '^(GROQ_API_KEY|SARVAM_API_KEY)=' .env 2>/dev/null || true)
if [ -z "$GROQ_API_KEY" ] || [ -z "$SARVAM_API_KEY" ]; then
    echo "WARNING: API keys missing in .env — the AI won't work."
    echo ""
fi

echo "[1/2] Starting server on port 8765..."
"$VENV" -c "
import uvicorn
uvicorn.run('rinha.main:app', host='0.0.0.0', port=8765, log_level='warning')
" &
sleep 2
echo "       Server: http://localhost:8765"

echo "[2/2] Starting tunnel..."
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
    -R 80:localhost:8765 nokey@localhost.run \
    > /tmp/rinha-tunnel.log 2>&1 &
sleep 4

URL=$(grep -oE 'https://[a-z0-9]+\.lhr\.life' /tmp/rinha-tunnel.log | head -1)

echo ""
echo "=============================================="
echo "  PUBLIC URL: $URL"
echo "=============================================="
echo ""
echo "  Twilio Voice Webhook (POST):  $URL/twilio-call"
echo "  Media Streams WebSocket:      wss://$(echo $URL | sed 's|https://||')/media-stream"
echo ""
echo "Press Ctrl+C to stop server + tunnel"
echo ""

wait
