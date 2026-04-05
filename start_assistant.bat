@echo off
cd /d %~dp0

echo Activation environnement...
call .venv\Scripts\activate

echo Lancement serveur...
start http://127.0.0.1:8000/summary-readable
python -m uvicorn app.main:app --reload

pause