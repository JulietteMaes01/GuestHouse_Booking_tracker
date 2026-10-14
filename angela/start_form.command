#!/bin/bash
# Mac version of start_form.bat, to test Angela's kit on a Mac: same checks,
# same messages. The modules are installed in a private folder (python-env)
# next to this file, so nothing else on the Mac is touched.

pause() { echo; read -r -p "Appuyez sur Entrée pour fermer…" _; }

cd "$(dirname "$0")" || exit 1
KIT="$(pwd)"
# Finder doesn't load the shell profile: add the usual Python locations
export PATH="$HOME/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "================================================"
echo "  La Ferme de la Cour - Formulaire reservations"
echo "================================================"
echo

if [ ! -f GuestHouse_Booking_tracker/scripts/app.py ]; then
    echo " [!] Le dossier GuestHouse_Booking_tracker est introuvable."
    echo "     start_form.command doit rester DANS le dossier \"La Ferme de la Cour - Angela\"."
    pause; exit 1
fi

if ! python3 --version >/dev/null 2>&1; then
    echo " [!] Python n'est pas installé sur cet ordinateur."
    echo "     La page de téléchargement s'ouvre : installez Python, puis relancez."
    open https://www.python.org/downloads/
    pause; exit 1
fi

if ! python-env/bin/python -c "import flask, gspread, google_auth_oauthlib" >/dev/null 2>&1; then
    echo " Première utilisation sur cet ordinateur :"
    echo " installation des modules, patientez une minute..."
    echo
    if ! { python3 -m venv python-env &&
           python-env/bin/pip install --quiet --disable-pip-version-check -r GuestHouse_Booking_tracker/requirements-form.txt; }; then
        echo " [!] L'installation des modules n'a pas fonctionné. Vérifiez internet et relancez."
        pause; exit 1
    fi
fi

if [ ! -f creds/credentials.json ]; then
    echo " [!] La connexion Google est introuvable : copiez le dossier \"creds\""
    echo "     dans \"La Ferme de la Cour - Angela\", à côté de start_form.command."
    pause; exit 1
fi

echo " Ne fermez pas cette fenêtre !"
echo " Le formulaire va s'ouvrir dans le navigateur."
echo " (Sinon, allez sur http://localhost:5051)"
echo
cd GuestHouse_Booking_tracker/scripts && "$KIT/python-env/bin/python" app.py --open

echo
echo " Le formulaire s'est arrêté."
pause
