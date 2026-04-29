#!/bin/sh
# Script de demarrage Raya pour Docker (utilise par CMD du Dockerfile).
#
# Resout la variable PORT injectee par Railway au runtime (fallback 8080
# en local). Le 'exec' final remplace le shell par le process uvicorn,
# qui devient ainsi PID 1 (gestion propre des signaux SIGTERM, etc.).
#
# Note importante : pour que ce script soit execute, la Custom Start
# Command de Railway doit etre vide (cf commentaire Dockerfile).

PORT_TO_USE="${PORT:-8080}"
echo "[entrypoint] Starting uvicorn on port $PORT_TO_USE"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT_TO_USE"
