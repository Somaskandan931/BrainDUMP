#!/bin/sh
set -e

# Start the daemon in the background, wait for it to accept connections,
# then pull the model onto the mounted disk (see render.yaml's disk for
# this service — without a persistent disk this re-downloads on every
# restart/deploy).
ollama serve &
SERVE_PID=$!

until ollama list >/dev/null 2>&1; do
  sleep 1
done

ollama pull "${OLLAMA_MODEL:-qwen3:8b}"

wait "$SERVE_PID"
