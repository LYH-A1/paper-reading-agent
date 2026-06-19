@echo off
cd /d "D:\桌面\agent - 2\paper-reading-agent"
echo Starting Paper Reading Agent...
echo Open http://localhost:8000 in your browser
echo Press Ctrl+C to stop
echo.
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
pause
