# La Ferme de la Cour — Booking Tracker

## Folder structure

```
scripts/              Python scripts (run from here)
  config.py           All settings (sheet ID, rooms, etc.)
  auth.py             Google OAuth (run once, caches token)
  email_parser.py     Gmail → parse elloha emails → Google Sheet
  schedule_generator.py  Google Sheet → HTML → GitHub Pages
  app.py              Flask form for manual/phone bookings
  setup.py            One-time setup wizard
  run.py              Daily shortcut: email_parser + schedule_generator
  fix_phone_errors.py One-time script in case of phone number parsing errors

docs/                 Generated HTML (served by GitHub Pages)
  index.html          Today's schedule (main page)
  weekly.html         This week's summary
  logo.png            Farm logo (copied automatically)

templates/            Flask HTML template
start_form.command    Double-click to launch the booking form (macOS)
```

---

## First-time setup (do this once)

### 1. Install Python dependencies

```bash
cd "/Users/jules/Documents/other/La Ferme de la Cour/scripts"
pip install -r ../requirements.txt
```

### 2. Get Google credentials

1. Go to https://console.cloud.google.com/
2. Select (or create) your project
3. **APIs & Services → Library** → enable:
   - Gmail API
   - Google Sheets API
4. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Click Create → **Download JSON**
5. Rename the file to `credentials.json`
6. Create a folder called `creds/` **next to** (not inside) the repo folder, and put the file there:
   ```
   La Ferme de la Cour/          ← parent folder
     creds/
       credentials.json          ← here
     GuestHouse_Booking_tracker/ ← the repo
       scripts/
   ```
   (It is gitignored — it will never be committed accidentally)

> If you see "Access blocked" when authenticating:
> Go to **APIs & Services → OAuth consent screen → Test users → + Add Users**
> and add `lafermedelacour2016@gmail.com`

### 3. Run the setup wizard

```bash
cd scripts
python setup.py
```

A browser window will open. Sign in with `lafermedelacour2016@gmail.com` and click **Allow**.
This creates `token.pickle` (also gitignored). You won't need to do this again unless you delete it.

### 4. Clone the GitHub repo (if not already done)

```bash
git clone https://github.com/JulietteMaes01/GuestHouse_Booking_tracker.git
```

Make sure the repo path in `config.py` → `GITHUB_REPO_PATH` points to your local clone.
If you run scripts from inside the repo folder, the default `"."` already works.

---

## Daily use

### Parse new elloha emails + update the schedule

```bash
cd scripts
python run.py
```

This does two things in one command:
1. Reads new emails from Gmail and updates the Google Sheet
2. Generates today's and this week's HTML and pushes to GitHub Pages

### Or run them separately

```bash
python email_parser.py       # only sync emails → Sheet
python schedule_generator.py # only generate HTML → GitHub
```

---

## Manual booking form (for phone/direct bookings)

Your mother-in-law can use this from her laptop, phone, or tablet.

### Starting it (you or her)

**Option A — double-click:**
Open `start_form.command` (in the root folder). Terminal opens, browser launches automatically.

**Option B — from the terminal:**
```bash
cd scripts
python app.py
```

Then open http://localhost:5051 in any browser.

**From her phone or tablet (same Wi-Fi):**
When the app starts, the terminal prints a local network URL like `http://192.168.x.x:5000`.
She can bookmark that on her phone.

### What the form does
- Fills in a form: rooms, dates, guest name, phone, email, nationality, amount, notes
- Automatically calculates number of nights
- Detects if the guest is a returning customer
- Saves directly to the Google Sheet

---

## How to view the schedule

Open the GitHub Pages URL in any browser (phone, tablet, laptop):

```
https://JulietteMaes01.github.io/GuestHouse_Booking_tracker/
```

- **Today's schedule**: the main page (`index.html`)
- **This week's summary**: click "Cette semaine" or go to `.../weekly.html`

---

## Automating daily runs on your Mac (optional)

To run `python run.py` automatically every day at 8am, add a launchd job:

1. Create `~/Library/LaunchAgents/com.lfdlc.dailyupdate.plist` with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.lfdlc.dailyupdate</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/jules/.pyenv/versions/3.10.11/bin/python</string>
    <string>/Users/jules/Documents/other/La Ferme de la Cour/scripts/run.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/tmp/lfdlc_update.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/lfdlc_update.log</string>
</dict>
</plist>
```

2. Load it:
```bash
launchctl load ~/Library/LaunchAgents/com.lfdlc.dailyupdate.plist
```

> Your Mac must be on (not sleeping) at 8am for this to run.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `credentials.json not found` | Download it from Google Cloud Console (see step 2) |
| `Access blocked: app not verified` | Add the Gmail address as a Test User in OAuth consent screen |
| `token.pickle` expired | Delete `creds/token.pickle` (next to the repo) and re-run `python setup.py` |
| Email not parsed | Check that the email is from `no-reply@elloha.com` and has a reference like `\| U...` or `\| P...` |
| Git push fails | Make sure you're authenticated with GitHub (`gh auth login` or SSH key) |
| Flask form not saving | Check that `token.pickle` exists and has Sheets scope |
