#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
VENV=.venv
if [[ ! -x "$VENV/bin/osken-manager" && -x ../.venv/bin/osken-manager ]]; then
  VENV=../.venv
fi
if [[ ! -x "$VENV/bin/osken-manager" ]]; then
  echo "Missing .venv; follow README setup first." >&2
  exit 1
fi
"$VENV/bin/osken-manager" controller.py > controller.log 2>&1 &
CTRL_PID=$!
cleanup() {
  sudo mn -c >/dev/null 2>&1 || true
  kill "$CTRL_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
for _ in $(seq 1 30); do
  if "$VENV/bin/python" -c 'import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(.2); s.sendto(b"{\"action\":\"status\"}",("127.0.0.1",9999)); s.recvfrom(2048)' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
sudo "$VENV/bin/python" run_demo.py
