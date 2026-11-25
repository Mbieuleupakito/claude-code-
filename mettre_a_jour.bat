@echo off
rem La mise a jour est maintenant automatique a chaque lancement : ce fichier lance simplement l'outil.
cd /d "%~dp0"
call lancer.bat %*
