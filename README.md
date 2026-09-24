# CivicTrack Bengaluru — Setup Guide (for absolute beginners)

This is a working prototype of a civic complaint reporting system for Bengaluru,
with three roles: **Citizen**, **Officer**, and **Admin**.

You do NOT need to understand every line of code to run this. Just follow the
steps below in order.

---

## STEP 1 — Install Python

1. Go to https://www.python.org/downloads/
2. Download and install the latest Python 3 version.
3. **Important (Windows only):** During installation, tick the box that says
   "Add Python to PATH" before clicking Install.
4. To check it worked, open a terminal (Command Prompt / PowerShell / Terminal
   on Mac) and type:
   ```
   python --version
   ```
   You should see something like `Python 3.12.x`.

---

## STEP 2 — Get the project onto your computer

Unzip the `civictrack_bengaluru` folder you downloaded anywhere you like,
for example on your Desktop.

Open a terminal and navigate into that folder:
```
cd Desktop/civictrack_bengaluru
```
(Adjust the path depending on where you placed it.)

---

## STEP 3 — Create a virtual environment (keeps your project's packages separate)

```
python -m venv venv
```

Activate it:
- **Windows:** `venv\Scripts\activate`
- **Mac/Linux:** `source venv/bin/activate`

You'll know it worked because your terminal line will now start with `(venv)`.

---

## STEP 4 — Install Flask (the web framework this app uses)

```
pip install -r requirements.txt
```

---

## STEP 5 — Run the app

```
python app.py
```

You should see something like:
```
* Running on http://127.0.0.1:5000
```

Open that link (http://127.0.0.1:5000) in your browser. That's it — the app
is running locally on your own computer.

The first time you run it, a file called `civictrack.db` is automatically
created — this is your database (SQLite), with some demo officer/admin
accounts already added for you.

---

## STEP 6 — Try it out

**As a citizen:**
1. Click "Register", create an account, pick a ward.
2. Log in, click "Report New Issue", fill the form (try uploading a photo).
3. Notice it tells you which department it was auto-routed to.

**As an officer** (log out first, then log back in with a demo account):
- `officer_roads@civictrack.com` / `officer123` (handles Pothole/Road complaints)
- `officer_bescom@civictrack.com` / `officer123` (handles Streetlight complaints)
- `officer_bwssb@civictrack.com` / `officer123` (handles Drainage/Water complaints)
- `officer_sanitation@civictrack.com` / `officer123` (handles Garbage complaints)

Update the complaint you just submitted: change status to "Resolved", add a
remark, maybe upload a "proof" photo, and submit.

**Back as the citizen:**
Open the complaint again — you'll now see a box asking "Is the issue actually
fixed?" with Yes/No buttons. This citizen-verification step is the core idea
of the whole project (see the Motivation section in your report).

**As admin:**
- `admin@civictrack.com` / `admin123`
See the stats dashboard and every complaint across all departments.

---

## Project structure (what each file does)

```
civictrack_bengaluru/
│
├── app.py                  ← All the logic: routes, database, auto-routing rules
├── requirements.txt        ← List of Python packages needed
├── civictrack.db            ← Auto-created database file (don't edit by hand)
│
├── templates/               ← HTML pages (what the user sees)
│   ├── base.html            ← Shared layout (navbar) every page extends
│   ├── login.html
│   ├── register.html
│   ├── citizen_dashboard.html
│   ├── submit_complaint.html
│   ├── complaint_detail.html
│   ├── officer_dashboard.html
│   └── admin_dashboard.html
│
└── static/
    ├── style.css             ← All the visual styling
    └── uploads/               ← Photos citizens/officers upload get saved here
```

---

## How the "auto-routing" works (important for your viva/presentation)

Inside `app.py`, look for this dictionary near the top:

```python
CATEGORY_DEPARTMENT_MAP = {
    'Pothole / Road Damage': 'GBA Corporation - Roads Wing',
    'Streetlight Not Working': 'BESCOM',
    'Garbage / Sanitation': 'GBA Corporation - Sanitation Wing',
    'Drainage / Water Supply': 'BWSSB',
}
```

When a citizen submits a complaint, whatever category they pick is looked up
in this dictionary, and the matching department is saved automatically with
the complaint. That's your "auto-assignment" feature — no manual routing
needed. To add a new category, just add a new line here.

---

## Features included in this version

Beyond the basic report → assign → resolve → verify loop, this build includes:

- **SLA timer & auto-escalation** — each category has a deadline
  (`SLA_DAYS` in `app.py`, e.g. potholes = 7 days). Any complaint that's
  still open past its deadline gets automatically flagged 🚩 Escalated,
  visible to officers and admin. This is checked every time a dashboard
  loads (`auto_escalate()` function).
- **Duplicate detection** — if a citizen tries to report the same category
  of issue in the same ward as an existing open complaint, they're shown
  the existing one first and can choose to view it instead of creating a
  disconnected duplicate.
- **Public transparency map** — `/map` shows every located complaint as a
  colour-coded pin (using Leaflet.js + OpenStreetMap), so the accountability
  side of the project isn't just internal to departments.
- **Admin reassignment** — an admin can manually move a complaint to a
  different department if it was mis-categorised, directly from the admin
  dashboard.
- **Location capture** — citizens can click "Use My Current Location" when
  submitting a complaint (uses the browser's geolocation API) to plot it on
  the public map.

## Known limitation to mention if asked in a viva

If a duplicate is detected and the citizen chooses "Submit Anyway," any
photo they'd attached is not carried over (browsers don't allow file inputs
to be refilled via hidden form fields for security reasons) — they'd need to
re-attach it. This is a good "future improvement" line for your report:
storing the pending submission server-side (e.g. in the session) instead of
in hidden form fields would fix this.

## Ideas to extend later (for your final submission / demo "future scope" slide)

- Deploy it online (e.g. using Render.com or PythonAnywhere) so it's not just
  local — this makes for a much stronger demo.
- Add multilingual support (Kannada/English toggle).
- Add voice-based complaint submission using speech-to-text.
- Replace the manual "Use My Location" button with a click-on-map picker.

---

## If something goes wrong

- **"flask: command not found" or "ModuleNotFoundError: No module named flask"**
  → You forgot to activate the virtual environment, or `pip install -r requirements.txt`
  didn't run successfully. Re-check Step 3 and 4.
- **Port already in use** → Another program is using port 5000. Close it, or
  change the last line of `app.py` to `app.run(debug=True, port=5001)`.
- **Want a fresh database?** → Close the app, delete `civictrack.db`, and run
  `python app.py` again — it'll recreate it with fresh demo accounts.
