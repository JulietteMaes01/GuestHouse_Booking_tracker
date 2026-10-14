# La Ferme de la Cour — Booking Tracker

Keeps the guesthouse bookings in one Google Sheet and publishes the daily schedule.

1. **elloha emails → Sheet.** Booking.com, Expedia and website bookings arrive by email; `email_parser.py` copies them into the Sheet.
2. **Booking form → Sheet.** Phone, email and walk-in bookings are typed in by Angela in a small web form (`app.py`).
3. **Sheet → website.** `schedule_generator.py` and `analytics.py` turn the Sheet into the pages at
   **https://juliettemaes01.github.io/GuestHouse_Booking_tracker/**

Steps 1 and 3 run by themselves on GitHub Actions every 20 minutes (`.github/workflows/update_bookings.yml`),
started by cron-job.org (see [Every 20 minutes](#every-20-minutes)). Nothing needs to run on a laptop except the form.

---

## Where things are

```
scripts/
  email_parser.py        elloha emails → Sheet                 (GitHub Actions)
  schedule_generator.py  Sheet → docs/index, weekly, upcoming  (GitHub Actions)
  analytics.py           Sheet → docs/analytics.html           (GitHub Actions)
  app.py                 booking form, http://localhost:5051   (Angela's laptop)
  setup.py               log in to Google (first time, or when the login expired)

  config.py              every setting: rooms, massages, sources, commissions, goals
  bookings.py            a Sheet row as a Booking (dates, amounts, meals)
  sheet.py               reading and writing the Google Sheet
  guests.py              returning guests, nationality from the phone number
  pages.py               fills templates/ and saves pages into docs/
  clock.py               today's date in Belgium
  auth.py                Google login (token in ../creds/)
  processed_emails.json  emails already copied (so none is applied twice)

templates/               page layouts: schedule pages, analytics, booking form
docs/                    the published website (written by GitHub Actions — don't edit)
angela/                  Angela's Windows launcher and instructions
tools/                   build Angela's kit; refactoring safety net
tests/                   automated tests
```

Settings you're likely to change all live in `scripts/config.py`.

---

## The booking form

**On a Mac:** double-click `start_form.command` (in the folder above the repo), or:

```bash
cd scripts
python app.py
```

Then open http://localhost:5051. Other devices on the same Wi-Fi can use the second address it prints.

**For Angela (Windows):** build her kit and send it to her:

```bash
python tools/build_angela_kit.py
```

This creates `La Ferme de la Cour - Angela.zip` next to the repo, with the form only and never the Google login.
She extracts it over her folder; the steps are in `angela/INSTRUCTIONS_ANGELA.md`.
She needs Python 3.8+ and, once: `pip install -r requirements-form.txt`.

---

## First-time setup on a new computer

1. Install the Python packages (or `requirements-form.txt` if only the form is needed):
   ```bash
   pip install -r requirements.txt
   ```
2. Put the Google files in a `creds/` folder **next to** the repo (never inside it):
   ```
   La Ferme de la Cour/
     creds/
       credentials.json    ← OAuth client, from console.cloud.google.com (type "Desktop app")
       token.pickle        ← created by step 3
     GuestHouse_Booking_tracker/
   ```
3. Log in:
   ```bash
   cd scripts
   python setup.py
   ```

GitHub Actions gets the same two files from the repo secrets `GOOGLE_CREDENTIALS_B64` and `GOOGLE_TOKEN_B64`
(base64 of each file).

---

## Every 20 minutes

GitHub's own timer is unreliable for free repos (it can run hours late), so a free service,
[cron-job.org](https://cron-job.org), asks GitHub to run the update every 20 minutes.
GitHub's hourly timer stays as a backup.

The cron-job.org job sends a `POST` to
`https://api.github.com/repos/JulietteMaes01/GuestHouse_Booking_tracker/actions/workflows/update_bookings.yml/dispatches`
with body `{"ref":"main"}` and these headers:

```
Accept: application/vnd.github+json
Authorization: Bearer <token>
X-GitHub-Api-Version: 2022-11-28
```

The token is a GitHub fine-grained token limited to this repository with only
**Actions: Read and write**. It expires after a year: create a new one and paste it into the cron-job.org job.

---

## Changing the code safely

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

For changes that could affect how pages look, the screenshot check compares every page and form state,
pixel for pixel, at six test dates:

```bash
python tools/snapshot_sheet.py                    # once: copy the Sheet to tests/fixtures/
python tools/render_and_screenshot.py save before # before your change
python tools/render_and_screenshot.py compare before
```

`tests/fixtures/` and `tests/golden/` contain guest data: they are gitignored and stay on your computer.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Pages not updating | GitHub → **Actions** tab → open the last red run. No runs at all? Check the job's history on cron-job.org (expired token?) |
| `credentials.json not found` | Download it from Google Cloud Console (see setup step 2) |
| Google login expired | Delete `creds/token.pickle`, run `python setup.py`, then update the `GOOGLE_TOKEN_B64` secret |
| "Access blocked: app not verified" | Google Cloud Console → OAuth consent screen → Test users → add the farm's Gmail address |
| An email wasn't copied | It must come from `no-reply@elloha.com` with a reference like `\| U…` or `\| P…` in the subject |
| Form says "Erreur de connexion au Google Sheet" | Check the internet connection; then the Google login (row above) |
