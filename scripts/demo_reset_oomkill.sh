#!/usr/bin/env bash
set -euo pipefail

kubectl patch deployment demo-oomkill -n default --type merge -p '{"spec":{"template":{"spec":{"containers":[{"name":"memory-hog","image":"python:3.11-alpine","command":["python","-c","import time\n\ndata = bytearray(72 * 1024 * 1024)\nprint(f\"allocated {len(data)} bytes\", flush=True)\ntime.sleep(3600)"],"resources":{"limits":{"memory":"64Mi"},"requests":{"memory":"32Mi"}}}]}}}}'
kubectl rollout status deployment/demo-oomkill -n default

printf 'demo-oomkill reset to failing memory baseline.\n'
