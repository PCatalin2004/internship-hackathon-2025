@echo off
echo Activating venv...
call venv\Scripts\activate

echo Starting FastAPI backend...
start cmd /k "cd backend && uvicorn app:app --reload --port 8000"

echo Waiting 3 seconds...
timeout /t 3 >nul

echo Starting NiceGUI frontend...
start cmd /k "cd frontend && python app.py"

echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:8502
pause
