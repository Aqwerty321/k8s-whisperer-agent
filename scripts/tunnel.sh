#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
cloudflared tunnel --url "http://localhost:${PORT}"
