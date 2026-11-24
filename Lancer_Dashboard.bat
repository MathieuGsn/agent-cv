@echo off
rem ==========================================================================
rem  Agent CV - lance le dashboard de candidatures et ouvre le navigateur.
rem  Double-clic pour lancer. Fermer cette fenetre arrete le dashboard.
rem ==========================================================================
setlocal
chcp 65001 >nul
title Agent CV - dashboard
cd /d "%~dp0"

set "PORT=8501"
set "URL=http://localhost:%PORT%"

rem Deja lance ? On ouvre juste le navigateur.
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if %errorlevel%==0 (
    echo Le dashboard tourne deja : ouverture de %URL%
    start "" "%URL%"
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)

rem Python : "python" puis le lanceur "py" en secours.
set "PY=python"
where python >nul 2>nul || set "PY=py"
%PY% -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERREUR] Python ou Streamlit est introuvable.
    echo Installe-les avec :  python -m pip install streamlit pandas altair pyyaml jinja2
    echo.
    pause
    exit /b 1
)

echo.
echo   Agent CV - dashboard de candidatures
echo   ------------------------------------
echo   Adresse : %URL%
echo   Le navigateur va s'ouvrir tout seul.
echo   Pour arreter le dashboard : ferme cette fenetre.
echo.

rem Ouvre le navigateur quand le serveur repond (max ~30 s), en arriere-plan.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command ^
  "for($i=0;$i -lt 60;$i++){try{Invoke-WebRequest '%URL%' -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process '%URL%'; break}catch{Start-Sleep -Milliseconds 500}}"

%PY% -m streamlit run dashboard\app.py --server.port %PORT% --server.headless true

echo.
echo Le dashboard s'est arrete.
pause
