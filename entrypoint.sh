#!/bin/sh
# Script de demarrage Raya pour Docker.
# Resout la variable PORT injectee par Railway (fallback 8080 en local).
# Pourquoi un script et pas CMD inline : le CMD JSON ne fait pas la substitution
# de variables sur Railway, donc on isole le shell ici.

PORT_TO_USE="${PORT:-8080}"
echo "[entrypoint] Starting uvicorn on port $PORT_TO_USE"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT_TO_USE"
