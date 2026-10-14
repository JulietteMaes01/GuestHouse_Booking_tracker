@echo off
rem Starts Angela's booking form. Checks the usual problems first and says
rem in plain French what to do. Keep this file ASCII-only (no accents).
title Formulaire reservations - La Ferme de la Cour

cd /d "%~dp0GuestHouse_Booking_tracker\scripts" 2>nul
if errorlevel 1 goto wrong_folder

echo ================================================
echo   La Ferme de la Cour - Formulaire reservations
echo ================================================
echo.

rem -- 1. Is Python installed? (python, or the "py" launcher)
set "PY="
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY goto no_python

rem -- 2. Are the modules installed? If not, install them (needs internet, once).
%PY% -c "import flask, gspread, google_auth_oauthlib" >nul 2>&1
if errorlevel 1 (
    echo  Premiere utilisation sur cet ordinateur :
    echo  installation des modules, patientez une minute...
    echo.
    %PY% -m pip install --user --quiet --disable-pip-version-check --no-warn-script-location -r ..\requirements-form.txt
    if errorlevel 1 goto install_failed
)

rem -- 3. Is the Google login file there?
if not exist "..\..\creds\credentials.json" goto no_creds

echo  Ne fermez pas cette fenetre !
echo  Le formulaire va s'ouvrir dans le navigateur.
echo  (Sinon, allez sur http://localhost:5051)
echo.
%PY% app.py --open

echo.
echo ================================================
echo  Le formulaire s'est arrete.
echo  Si vous voyez une erreur ci-dessus, prenez une
echo  photo et envoyez-la a Juliette.
echo ================================================
goto end

:wrong_folder
echo.
echo  [!] Le dossier GuestHouse_Booking_tracker est introuvable.
echo.
echo      start_form.bat doit rester DANS le dossier
echo      "La Ferme de la Cour - Angela", a cote du dossier GuestHouse_Booking_tracker.
echo.
echo      Pour l'avoir sur le bureau : clic droit sur start_form.bat
echo      puis "Envoyer vers" puis "Bureau (creer un raccourci)".
goto end

:no_python
echo  [!] Python n'est pas installe sur cet ordinateur.
echo.
echo      1. Ouvrez le Microsoft Store (menu Demarrer, tapez "Microsoft Store").
echo      2. Cherchez "Python" et installez la version la plus recente
echo         publiee par "Python Software Foundation" (bouton Obtenir).
echo      3. Quand c'est fini, relancez start_form.bat.
goto end

:install_failed
echo.
echo  [!] L'installation des modules n'a pas fonctionne.
echo      Verifiez la connexion internet, puis relancez start_form.bat.
echo      Si cela recommence, prenez une photo et envoyez-la a Juliette.
goto end

:no_creds
echo  [!] La connexion Google est introuvable.
echo.
echo      Copiez le dossier "creds" de l'ancien ordinateur dans
echo      "La Ferme de la Cour - Angela", a cote de start_form.bat,
echo      puis relancez start_form.bat.
goto end

:end
echo.
pause
