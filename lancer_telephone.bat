@echo off
rem Ouvre l'outil aussi depuis le telephone (meme wifi), protege par un mot de passe.
chcp 65001 >nul
cd /d "%~dp0"
set /p MDP= Choisir un mot de passe pour cette session : 
if "%MDP%"=="" goto fin
echo  Si Windows demande l'autorisation du pare-feu, choisir "Reseaux prives".
call lancer.bat --reseau --mot-de-passe "%MDP%"
:fin
