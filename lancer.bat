@echo off
rem Assistant RE2020 - double-cliquer pour lancer (Windows). La premiere fois, installe tout.
chcp 65001 >nul
cd /d "%~dp0"
title Assistant RE2020
if exist ".venv\Scripts\python.exe" goto lancer

echo.
echo  Premiere utilisation : installation, quelques minutes...
py -3.12 -m venv .venv
if errorlevel 1 goto sans_python
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -e ".[api,rapport]"
if errorlevel 1 goto echec

:lancer
".venv\Scripts\python.exe" -m re2020.api %*
pause
exit /b 0

:sans_python
echo.
echo  Python 3.12 est introuvable. Installez-le depuis https://www.python.org/downloads/
echo  en cochant "Add python.exe to PATH", puis relancez ce fichier.
pause
exit /b 1

:echec
echo.
echo  L'installation a echoue : supprimez le dossier .venv et relancez, ou envoyez une capture de cette fenetre.
pause
exit /b 1
