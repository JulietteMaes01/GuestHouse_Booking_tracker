"""
Build the zip Juliette sends to Angela: the booking form and nothing else.

    python tools/build_angela_kit.py

Creates "La Ferme de la Cour - Angela.zip" next to the repo. Angela extracts it
over her existing folder; her creds/ folder (Google login) is never in the zip.
The form's Python files are found by following app.py's imports, so the kit
can't miss a module after the code changes.
"""
import ast
import os
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
KIT_FOLDER = "La Ferme de la Cour - Angela"
ZIP_PATH = os.path.join(os.path.dirname(REPO_ROOT), f"{KIT_FOLDER}.zip")
REPO_IN_KIT = f"{KIT_FOLDER}/GuestHouse_Booking_tracker"


def main():
    files = {
        f"{KIT_FOLDER}/start_form.bat": "angela/start_form.bat",
        f"{KIT_FOLDER}/INSTRUCTIONS_ANGELA.md": "angela/INSTRUCTIONS_ANGELA.md",
        f"{REPO_IN_KIT}/requirements-form.txt": "requirements-form.txt",
        f"{REPO_IN_KIT}/templates/booking_form.html": "templates/booking_form.html",
        f"{REPO_IN_KIT}/docs/logo.png": "docs/logo.png",
    }
    for module in sorted(form_modules()):
        files[f"{REPO_IN_KIT}/scripts/{module}.py"] = f"scripts/{module}.py"

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as kit:
        for name_in_zip, repo_path in files.items():
            kit.write(os.path.join(REPO_ROOT, repo_path), name_in_zip)
    print(f"✓ {ZIP_PATH}")
    for name_in_zip in files:
        print(f"    {name_in_zip}")


def form_modules(module="app", found=None) -> set:
    """app plus every module of scripts/ it imports, directly or indirectly."""
    found = set() if found is None else found
    found.add(module)
    with open(os.path.join(SCRIPTS_DIR, f"{module}.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            if name not in found and os.path.exists(os.path.join(SCRIPTS_DIR, f"{name}.py")):
                form_modules(name, found)
    return found


if __name__ == "__main__":
    main()
