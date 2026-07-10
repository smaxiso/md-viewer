#!/usr/bin/env bash

# Change to script directory
cd "$(dirname "$0")"

echo "🛑 Cleaning up any old instances..."
pkill -f "uvicorn main:app --port 8001" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1

echo "🚀 Starting Backend (FastAPI on port 8001)..."
cd backend
export MDVIEW_DIR=${MDVIEW_DIR:-$HOME/workspace}
.venv/bin/uvicorn main:app --port 8001 > backend.log 2>&1 &
BACKEND_PID=$!
cd ..

echo "🚀 Starting Frontend (Vite on port 8000)..."
cd frontend
npm run dev > frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo "⏳ Waiting for services to initialize..."
sleep 3

# Check status
BACKEND_OK=0
FRONTEND_OK=0

if ps -p $BACKEND_PID > /dev/null; then
    echo "✅ Backend is running (PID: $BACKEND_PID)"
    BACKEND_OK=1
else
    echo "❌ Backend failed to start. Check backend/backend.log"
fi

if ps -p $FRONTEND_PID > /dev/null; then
    echo "✅ Frontend is running (PID: $FRONTEND_PID)"
    FRONTEND_OK=1
else
    echo "❌ Frontend failed to start. Check frontend/frontend.log"
fi

echo ""
echo "========================================================"
if [ $BACKEND_OK -eq 1 ] && [ $FRONTEND_OK -eq 1 ]; then
    echo "🌟 MdViewer is LIVE!"
    echo "👉 Open your browser and navigate to: http://localhost:8000"
    echo "📝 Serving markdown files from: $MDVIEW_DIR"
else
    echo "⚠️ Warning: One or more services failed to start."
fi
echo "========================================================"
echo ""
echo "To stop the services, run: mdview-stop"
