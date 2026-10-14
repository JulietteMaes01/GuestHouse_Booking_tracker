@echo off
cd /d "%~dp0GuestHouse_Booking_tracker\scripts"

echo ================================================
echo   La Ferme de la Cour - Formulaire reservations
echo ================================================
echo.
echo  Ne fermez pas cette fenetre !
echo  Le formulaire est accessible sur : http://localhost:5051
echo.

start "" http://localhost:5051
python app.py

echo.
echo ================================================
echo  Le serveur s'est arrete.
echo  Si vous voyez une erreur ci-dessus, prenez une
echo  photo et envoyez-la a Juliette.
echo ================================================
pause
