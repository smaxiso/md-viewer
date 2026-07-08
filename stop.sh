#!/usr/bin/env bash

echo "🛑 Stopping MdViewer services..."
pkill -f "uvicorn main:app --port 8001" 2>/dev/null && echo "✅ Backend stopped" || echo "⚠️ Backend was not running"
pkill -f "vite" 2>/dev/null && echo "✅ Frontend stopped" || echo "⚠️ Frontend was not running"
echo "✅ All services stopped."
