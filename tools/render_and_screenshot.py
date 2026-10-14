"""
Refactoring safety net: prove the pages still look exactly the same.

Renders every published page and every booking-form state from the Sheet
snapshot (tests/fixtures/sheet.json) at a set of frozen dates, screenshots them
with headless Chrome, and compares the pixels with a saved "golden" set.

    python tools/render_and_screenshot.py save v1        # create golden set v1
    python tools/render_and_screenshot.py compare v1     # check current code against v1
    python tools/render_and_screenshot.py textdiff v1 v2 # visible-text differences

Golden sets live in tests/golden/ (gitignored: they contain guest data).
"""
import base64
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "sheet.json")
GOLDEN_DIR = os.path.join(REPO_ROOT, "tests", "golden")
LOGO = os.path.join(REPO_ROOT, "docs", "logo.png")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Each date shows at least one tricky case on the daily/weekly pages.
# Times are UTC; 08:00 UTC is 10:00 in Brussels during summer time.
FROZEN_DATES = {
    "2026-07-15": "Umfulana 50% payment",
    "2026-07-20": "massage",
    "2026-09-19": "room turnover + table d'hôtes on specific nights",
    "2026-10-14": "synthetic meal-only + brunch bookings",
    "2026-10-16": "repeat guest + table d'hôtes dates + synthetic meal",
    "2026-12-24": "empty days",
}
PAGES = ["index.html", "weekly.html", "upcoming.html", "analytics.html"]
FORM_TABS = ["room", "meal", "email", "extras"]
WIDTHS = [390, 1280]

# The real data has no meal-only or brunch bookings, so these fake rows
# exercise those code paths. Same shape as a Sheet row.
SYNTHETIC_ROWS = [
    {"booking_source": "Email/phone", "booking_date": "01/10/2026", "email_type": "Booking",
     "status": "Confirmed", "reference": "M9001", "arrival_date": "14/10/2026",
     "departure_date": "14/10/2026", "amount": 90, "guest_name": "Test Brunch",
     "nationality": "Belgique", "nights": 0, "notes": "[☕ Brunch | 🌱 Végétalien] Anniversaire",
     "repeat_guest": "FALSE", "visit_count": 1, "table_dhotes": "FALSE", "breakfast": "TRUE",
     "guest_count": 4},
    {"booking_source": "Email/phone", "booking_date": "02/10/2026", "email_type": "Booking",
     "status": "Confirmed", "reference": "M9002", "arrival_date": "16/10/2026",
     "departure_date": "16/10/2026", "amount": 240, "guest_name": "Test Dîner",
     "nationality": "France", "nights": 0, "notes": "",
     "repeat_guest": "FALSE", "visit_count": 1, "table_dhotes": "TRUE", "breakfast": "FALSE",
     "guest_count": 6},
    {"booking_source": "Email/phone", "booking_date": "02/10/2026", "email_type": "Booking",
     "status": "Confirmed", "reference": "M9003", "arrival_date": "14/10/2026",
     "departure_date": "14/10/2026", "amount": "", "guest_name": "Test Sans Nombre",
     "nationality": "", "nights": 0, "notes": "", "massage": "Massage du dos 30min (30€) · Duo",
     "repeat_guest": "FALSE", "visit_count": 1, "table_dhotes": "TRUE", "breakfast": "TRUE",
     "guest_count": ""},
]


# ── Fake Google Sheet ─────────────────────────────────────────────────────────

def _snapshot_worksheet():
    """The Sheet snapshot plus SYNTHETIC_ROWS, served exactly as gspread returned it."""
    sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
    from fake_sheet import FakeWorksheet
    with open(FIXTURE, encoding="utf-8") as fh:
        snapshot = json.load(fh)
    synthetic = FakeWorksheet.from_rows(snapshot["values"][0], SYNTHETIC_ROWS)
    return FakeWorksheet(snapshot["records"] + synthetic.records,
                         snapshot["values"] + synthetic.values[1:])


# ── Rendering (runs in a fresh subprocess per date) ───────────────────────────

def _point_output_to(out_dir):
    """Make the generators write into out_dir instead of the repo's docs/."""
    import config
    config.DOCS_DIR = os.path.join(out_dir, "docs")


def _render_one_date(frozen_date, out_dir):
    from freezegun import freeze_time

    sys.path.insert(0, SCRIPTS_DIR)
    import auth
    worksheet = _snapshot_worksheet()
    auth.get_worksheet = lambda: worksheet
    _point_output_to(out_dir)
    # Import before freezing: numpy's C code breaks if imported under freezegun.
    import schedule_generator
    import analytics

    with freeze_time(f"{frozen_date} 08:00:00"):
        schedule_generator.run()
        analytics.main()
        if frozen_date == min(FROZEN_DATES):
            _render_form(worksheet, out_dir)


def _render_form(worksheet, out_dir):
    import app as form_app
    client = form_app.app.test_client()
    form_dir = os.path.join(out_dir, "form")
    os.makedirs(form_dir, exist_ok=True)

    def save(name, response):
        with open(os.path.join(form_dir, name), "wb") as fh:
            fh.write(response.data)

    for tab in FORM_TABS:
        save(f"tab_{tab}.html", client.get(f"/?tab={tab}"))
    save("error_missing_fields.html", client.post("/", data={"form_type": "room"}))
    save("error_conflict.html", client.post("/", data=_conflicting_booking(worksheet)))


def _conflicting_booking(worksheet):
    """Form data that overlaps the last confirmed room booking in the snapshot."""
    from datetime import datetime
    for rec in reversed(worksheet.get_all_records()):
        if rec["status"] == "Confirmed" and rec["room1"]:
            arrival = datetime.strptime(rec["arrival_date"], "%d/%m/%Y")
            departure = datetime.strptime(rec["departure_date"], "%d/%m/%Y")
            return {
                "form_type": "room", "rooms": rec["room1"],
                "arrival_date": arrival.strftime("%Y-%m-%d"),
                "departure_date": departure.strftime("%Y-%m-%d"),
                "guest_name": "Test Conflit", "phone": "0470000000",
            }
    raise RuntimeError("No confirmed room booking in snapshot")


def render_all(out_dir):
    """Render every page for every frozen date into out_dir/<date>/."""
    for frozen_date in FROZEN_DATES:
        date_dir = os.path.join(out_dir, frozen_date)
        os.makedirs(os.path.join(date_dir, "docs"), exist_ok=True)
        result = subprocess.run(
            [sys.executable, __file__, "_render_one", frozen_date, date_dir],
            cwd=SCRIPTS_DIR, capture_output=True, text=True,
        )
        if result.returncode != 0:
            sys.exit(f"Rendering {frozen_date} failed:\n{result.stderr[-3000:]}")
        shutil.copy(LOGO, os.path.join(date_dir, "docs", "logo.png"))
    form_src = os.path.join(out_dir, min(FROZEN_DATES), "form")
    shutil.move(form_src, os.path.join(out_dir, "form"))


# ── Screenshots ───────────────────────────────────────────────────────────────

def _screenshot(html_path, png_path, width, query=""):
    """Full-page screenshot: grow the window until the bottom is empty background."""
    from PIL import Image
    height = 4000
    while True:
        url = "file://" + html_path.replace(" ", "%20") + query
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", f"--window-size={width},{height}",
             f"--screenshot={png_path}", url],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        image = Image.open(png_path).convert("RGB")
        bottom = image.crop((0, height - 40, width, height))
        if len(bottom.getcolors(maxcolors=4) or []) == 1 or height >= 60000:
            return
        height *= 2


def _screenshot_targets(render_dir):
    """(html_path, png_name, query) for every page and form state."""
    for frozen_date in FROZEN_DATES:
        for page in PAGES:
            path = os.path.join(render_dir, frozen_date, "docs", page)
            yield path, f"{frozen_date}_{page}", ""
    for tab in FORM_TABS:
        path = os.path.join(render_dir, "form", f"tab_{tab}.html")
        yield path, f"form_{tab}", f"?tab={tab}"
    for state in ("error_missing_fields", "error_conflict"):
        yield os.path.join(render_dir, "form", f"{state}.html"), f"form_{state}", ""


def _chart_images(html_path):
    """Decoded PNGs embedded in a page (analytics charts)."""
    with open(html_path, encoding="utf-8") as fh:
        return [base64.b64decode(b64) for b64 in
                re.findall(r'src="data:image/png;base64,([^"]+)"', fh.read())]


def capture(render_dir, shots_dir):
    """Screenshot every target at every width, and extract chart PNGs."""
    os.makedirs(shots_dir, exist_ok=True)
    for html_path, name, query in _screenshot_targets(render_dir):
        for width in WIDTHS:
            _screenshot(html_path, os.path.join(shots_dir, f"{name}@{width}.png"), width, query)
        for i, png in enumerate(_chart_images(html_path)):
            with open(os.path.join(shots_dir, f"{name}#chart{i:02d}.png"), "wb") as fh:
                fh.write(png)


# ── Comparing ─────────────────────────────────────────────────────────────────

def _same_pixels(path_a, path_b):
    from PIL import Image, ImageChops
    a, b = Image.open(path_a).convert("RGB"), Image.open(path_b).convert("RGB")
    return a.size == b.size and ImageChops.difference(a, b).getbbox() is None


def compare(golden_shots, new_shots):
    expected = sorted(os.listdir(golden_shots))
    actual = sorted(os.listdir(new_shots))
    problems = [f"missing: {n}" for n in expected if n not in actual]
    problems += [f"extra:   {n}" for n in actual if n not in expected]
    problems += [f"differs: {n}" for n in expected if n in actual
                 and not _same_pixels(os.path.join(golden_shots, n), os.path.join(new_shots, n))]
    return problems


def _visible_text(html_path):
    from bs4 import BeautifulSoup
    with open(html_path, encoding="utf-8") as fh:
        soup = BeautifulSoup(fh.read(), "html.parser")
    for tag in soup(["style", "script"]):
        tag.decompose()
    return [line for line in soup.get_text("\n", strip=True).splitlines() if line]


def text_diff(label_a, label_b):
    root_a = os.path.join(GOLDEN_DIR, label_a, "html")
    root_b = os.path.join(GOLDEN_DIR, label_b, "html")
    for html_path, name, _ in _screenshot_targets(root_a):
        other = html_path.replace(root_a, root_b)
        diff = [line for line in difflib.unified_diff(
            _visible_text(html_path), _visible_text(other), lineterm="", n=0)
            if line[:1] in "+-" and line[:3] not in ("+++", "---")]
        if diff:
            print(f"── {name}")
            print("\n".join(diff))


# ── Commands ──────────────────────────────────────────────────────────────────

def save(label):
    target = os.path.join(GOLDEN_DIR, label)
    shutil.rmtree(target, ignore_errors=True)
    render_all(os.path.join(target, "html"))
    capture(os.path.join(target, "html"), os.path.join(target, "shots"))
    print(f"Golden set '{label}' saved → {target}")


def check(label):
    with tempfile.TemporaryDirectory() as tmp:
        render_all(os.path.join(tmp, "html"))
        capture(os.path.join(tmp, "html"), os.path.join(tmp, "shots"))
        problems = compare(os.path.join(GOLDEN_DIR, label, "shots"), os.path.join(tmp, "shots"))
    if problems:
        print("\n".join(problems))
        print(f"✗ {len(problems)} difference(s) vs '{label}'")
        sys.exit(1)
    print(f"✓ Pixel-identical to golden set '{label}'")


if __name__ == "__main__":
    command, *args = sys.argv[1:] or ["help"]
    if command == "save":
        save(*args)
    elif command == "compare":
        check(*args)
    elif command == "textdiff":
        text_diff(*args)
    elif command == "_render_one":
        _render_one_date(*args)
    else:
        sys.exit(__doc__)
