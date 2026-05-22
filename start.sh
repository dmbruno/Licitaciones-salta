#!/usr/bin/env bash
# Inicia backend y frontend en paralelo

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Arrancando backend en http://localhost:8000"
cd "$ROOT/backend"
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "==> Arrancando frontend en http://localhost:5173"
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "  Ctrl+C para detener todo"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
