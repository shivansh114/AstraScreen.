@echo off
cd /d %~dp0
echo Installing packages (needs internet the first time)...
python -m pip install -r requirements.txt
echo.
echo Starting AstraScreen at http://localhost:8000
python run.py
pause
