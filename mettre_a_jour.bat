@echo off
rem Recupere la derniere version de l'outil et met a jour les dependances.
chcp 65001 >nul
cd /d "%~dp0"
git pull
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -m pip install -e ".[api,rapport]"
echo  Mise a jour terminee.
pause
