"""
CivicTrack Bengaluru
---------------------
A citizen complaint reporting + government work tracking prototype.

WHAT THIS FILE DOES (read this if you're new to Flask):
- Flask is a Python "web framework" - it lets you turn Python functions into web pages.
- Each function below with an @app.route(...) above it handles one URL/page.
- We use SQLite as our database (a single file, no server needed - perfect for learning).
- Sessions are used to remember who is logged in (citizen / officer / admin).
"""

import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------- BASIC SETUP ----------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'civictrack.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app = Flask(__name__)
app.secret_key = 'change-this-secret-key-later'  # used to secure session cookies
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# This dictionary is the heart of "auto-routing" - it maps a complaint
# category to the government department responsible for it, based on
# how civic issues are actually divided in Bengaluru (GBA / BESCOM / BWSSB).
CATEGORY_DEPARTMENT_MAP = {
    'Pothole / Road Damage': 'GBA Corporation - Roads Wing',
    'Streetlight Not Working': 'BESCOM',
    'Garbage / Sanitation': 'GBA Corporation - Sanitation Wing',
    'Drainage / Water Supply': 'BWSSB',
}

STATUS_FLOW = ['Submitted', 'In Progress', 'Resolved (Awaiting Verification)', 'Closed', 'Reopened']

# How many days a department has to resolve each category before it's
# considered overdue and gets auto-escalated. This is what powers the
# "SLA timer" / accountability feature.
SLA_DAYS = {
    'Pothole / Road Damage': 7,
    'Streetlight Not Working': 5,
    'Garbage / Sanitation': 3,
    'Drainage / Water Supply': 7,
}

WARDS = ['Koramangala', 'Indiranagar', 'Whitefield', 'Jayanagar', 'HSR Layout',
         'Malleshwaram', 'Yelahanka', 'BTM Layout', 'Rajajinagar', 'Marathahalli']


# ---------- DATABASE HELPERS ----------

def get_db():
    """Open one database connection per request, reuse it, and store it on 'g'
    (a special Flask object that lives only for the current request)."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row  # lets us access columns by name, e.g. row['email']
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Creates the tables if they don't exist yet, and seeds demo accounts."""
    db = sqlite3.connect(DATABASE)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,             -- citizen / officer / admin
        department TEXT,                -- only used for officers
        ward TEXT                       -- only used for citizens
    );

    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        citizen_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        department TEXT NOT NULL,
        ward TEXT NOT NULL,
        description TEXT NOT NULL,
        photo_filename TEXT,
        status TEXT NOT NULL DEFAULT 'Submitted',
        officer_remark TEXT,
        proof_filename TEXT,
        latitude REAL,
        longitude REAL,
        escalated INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (citizen_id) REFERENCES users (id)
    );
    ''')
    db.commit()

    # Seed demo officer + admin logins so you can test all 3 roles immediately.
    demo_users = [
        ('Roads Officer', 'officer_roads@civictrack.com', 'officer123', 'officer', 'GBA Corporation - Roads Wing', None),
        ('Sanitation Officer', 'officer_sanitation@civictrack.com', 'officer123', 'officer', 'GBA Corporation - Sanitation Wing', None),
        ('BESCOM Officer', 'officer_bescom@civictrack.com', 'officer123', 'officer', 'BESCOM', None),
        ('BWSSB Officer', 'officer_bwssb@civictrack.com', 'officer123', 'officer', 'BWSSB', None),
        ('System Admin', 'admin@civictrack.com', 'admin123', 'admin', None, None),
    ]
    for name, email, pw, role, dept, ward in demo_users:
        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if not existing:
            db.execute(
                'INSERT INTO users (name, email, password_hash, role, department, ward) VALUES (?, ?, ?, ?, ?, ?)',
                (name, email, generate_password_hash(pw), role, dept, ward)
            )
    db.commit()
    db.close()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def logged_in_as(role=None):
    """Small helper: checks if someone is logged in, and optionally checks their role."""
    if 'user_id' not in session:
        return False
    if role and session.get('role') != role:
        return False
    return True


# ---------- SLA / ESCALATION HELPERS ----------

def days_open(created_at_str):
    """How many whole days have passed since a complaint was created."""
    created = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
    return (datetime.now() - created).days


def sla_limit_for(category):
    return SLA_DAYS.get(category, 7)  # default 7 days if category not found


def is_overdue(complaint):
    """A complaint is overdue if it's still open AND has passed its SLA days."""
    if complaint['status'] in ('Closed', 'Resolved (Awaiting Verification)'):
        return False
    return days_open(complaint['created_at']) > sla_limit_for(complaint['category'])


def auto_escalate():
    """Scans all open complaints and marks any that have breached their SLA
    as escalated. This is what turns a silent, ignored complaint into a
    flagged one that shows up on the admin dashboard - the 'accountability'
    part of CivicTrack. In a real deployment this would run as a scheduled
    background job; here we simply run it whenever a dashboard is opened."""
    db = get_db()
    open_complaints = db.execute(
        "SELECT id, category, created_at FROM complaints WHERE status IN ('Submitted', 'In Progress') AND escalated = 0"
    ).fetchall()
    for c in open_complaints:
        if days_open(c['created_at']) > sla_limit_for(c['category']):
            db.execute('UPDATE complaints SET escalated = 1 WHERE id = ?', (c['id'],))
    db.commit()


# Make these available directly inside Jinja templates (so we can write
# {{ days_open(c['created_at']) }} etc. straight in HTML).
app.jinja_env.globals.update(days_open=days_open, sla_limit_for=sla_limit_for, is_overdue=is_overdue)


# ---------- HOME / AUTH ----------

@app.route('/')
def home():
    if 'user_id' in session:
        if session['role'] == 'citizen':
            return redirect(url_for('citizen_dashboard'))
        elif session['role'] == 'officer':
            return redirect(url_for('officer_dashboard'))
        elif session['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        ward = request.form['ward']

        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            flash('An account with this email already exists.')
            return redirect(url_for('register'))

        db.execute(
            'INSERT INTO users (name, email, password_hash, role, ward) VALUES (?, ?, ?, ?, ?)',
            (name, email, generate_password_hash(password), 'citizen', ward)
        )
        db.commit()
        flash('Account created! Please log in.')
        return redirect(url_for('login'))

    return render_template('register.html', wards=WARDS)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            session['department'] = user['department']
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password.')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---------- CITIZEN ----------

@app.route('/citizen/dashboard')
def citizen_dashboard():
    if not logged_in_as('citizen'):
        return redirect(url_for('login'))

    auto_escalate()
    db = get_db()
    complaints = db.execute(
        'SELECT * FROM complaints WHERE citizen_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    return render_template('citizen_dashboard.html', complaints=complaints)


@app.route('/citizen/submit', methods=['GET', 'POST'])
def submit_complaint():
    if not logged_in_as('citizen'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        category = request.form['category']
        ward = request.form['ward']
        description = request.form['description']
        latitude = request.form.get('latitude') or None
        longitude = request.form.get('longitude') or None
        department = CATEGORY_DEPARTMENT_MAP.get(category, 'General Grievance Cell')
        db = get_db()

        # --- DUPLICATE DETECTION ---
        # If someone already reported the same category of problem in the
        # same ward recently and it's still open, warn the citizen instead
        # of silently creating a second, disconnected complaint. This is
        # what "duplicate merging" looks like in a lightweight, beginner
        # friendly way: we don't auto-merge, we just surface the match and
        # let the citizen decide.
        if not request.form.get('confirm_new'):
            possible_duplicates = db.execute('''
                SELECT * FROM complaints
                WHERE category = ? AND ward = ? AND status NOT IN ('Closed')
                ORDER BY created_at DESC
            ''', (category, ward)).fetchall()

            if possible_duplicates:
                # Re-show the form's values so nothing is lost if the citizen
                # decides to go back and edit instead of submitting anyway.
                return render_template(
                    'duplicate_warning.html',
                    duplicates=possible_duplicates,
                    form_data=request.form
                )

        photo_filename = None
        photo = request.files.get('photo')
        if photo and photo.filename and allowed_file(photo.filename):
            photo_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(photo.filename)}"
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute('''
            INSERT INTO complaints
            (citizen_id, category, department, ward, description, photo_filename, status, latitude, longitude, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Submitted', ?, ?, ?, ?)
        ''', (session['user_id'], category, department, ward, description, photo_filename, latitude, longitude, now, now))
        db.commit()
        flash(f'Complaint submitted! Auto-routed to: {department}')
        return redirect(url_for('citizen_dashboard'))

    return render_template('submit_complaint.html', categories=CATEGORY_DEPARTMENT_MAP.keys(), wards=WARDS)


@app.route('/complaint/<int:complaint_id>')
def complaint_detail(complaint_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    complaint = db.execute('SELECT * FROM complaints WHERE id = ?', (complaint_id,)).fetchone()

    if not complaint:
        flash('Complaint not found.')
        return redirect(url_for('home'))

    # Citizens can only open their OWN complaints. Officers/admin can open any.
    if session['role'] == 'citizen' and complaint['citizen_id'] != session['user_id']:
        flash('You do not have access to that complaint.')
        return redirect(url_for('citizen_dashboard'))

    return render_template('complaint_detail.html', c=complaint)


@app.route('/citizen/complaint/<int:complaint_id>/verify', methods=['POST'])
def verify_complaint(complaint_id):
    """This is CivicTrack's key feature: the citizen - not the officer - has
    the final say on whether a complaint is truly resolved."""
    if not logged_in_as('citizen'):
        return redirect(url_for('login'))

    action = request.form['action']  # 'confirm' or 'reopen'
    db = get_db()
    complaint = db.execute('SELECT * FROM complaints WHERE id = ?', (complaint_id,)).fetchone()

    if not complaint or complaint['citizen_id'] != session['user_id']:
        flash('You do not have access to that complaint.')
        return redirect(url_for('citizen_dashboard'))

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_status = 'Closed' if action == 'confirm' else 'Reopened'
    db.execute('UPDATE complaints SET status = ?, updated_at = ? WHERE id = ?',
               (new_status, now, complaint_id))
    db.commit()
    flash('Thanks for confirming!' if action == 'confirm' else 'Complaint reopened and sent back to the department.')
    return redirect(url_for('complaint_detail', complaint_id=complaint_id))


# ---------- OFFICER ----------

@app.route('/officer/dashboard')
def officer_dashboard():
    if not logged_in_as('officer'):
        return redirect(url_for('login'))

    auto_escalate()
    db = get_db()
    complaints = db.execute(
        'SELECT * FROM complaints WHERE department = ? ORDER BY created_at DESC',
        (session['department'],)
    ).fetchall()
    return render_template('officer_dashboard.html', complaints=complaints, department=session['department'])


@app.route('/officer/complaint/<int:complaint_id>/update', methods=['POST'])
def update_complaint(complaint_id):
    if not logged_in_as('officer'):
        return redirect(url_for('login'))

    db = get_db()
    complaint = db.execute('SELECT * FROM complaints WHERE id = ?', (complaint_id,)).fetchone()
    if not complaint or complaint['department'] != session['department']:
        flash('You do not have access to that complaint.')
        return redirect(url_for('officer_dashboard'))

    new_status = request.form['status']
    remark = request.form.get('remark', '')

    proof_filename = complaint['proof_filename']
    proof = request.files.get('proof')
    if proof and proof.filename and allowed_file(proof.filename):
        proof_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(proof.filename)}"
        proof.save(os.path.join(app.config['UPLOAD_FOLDER'], proof_filename))

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute('''
        UPDATE complaints
        SET status = ?, officer_remark = ?, proof_filename = ?, updated_at = ?
        WHERE id = ?
    ''', (new_status, remark, proof_filename, now, complaint_id))
    db.commit()
    flash('Complaint updated.')
    return redirect(url_for('officer_dashboard'))


# ---------- ADMIN ----------

@app.route('/admin/dashboard')
def admin_dashboard():
    if not logged_in_as('admin'):
        return redirect(url_for('login'))

    auto_escalate()
    db = get_db()
    complaints = db.execute('SELECT * FROM complaints ORDER BY created_at DESC').fetchall()

    stats = {}
    for status in STATUS_FLOW:
        count = db.execute('SELECT COUNT(*) FROM complaints WHERE status = ?', (status,)).fetchone()[0]
        stats[status] = count

    escalated_count = db.execute('SELECT COUNT(*) FROM complaints WHERE escalated = 1').fetchone()[0]

    dept_stats = db.execute('''
        SELECT department, COUNT(*) as total,
        SUM(CASE WHEN status IN ('Submitted', 'In Progress') THEN 1 ELSE 0 END) as pending,
        SUM(escalated) as escalated
        FROM complaints GROUP BY department
    ''').fetchall()

    all_departments = sorted(set(CATEGORY_DEPARTMENT_MAP.values()))

    return render_template('admin_dashboard.html', complaints=complaints, stats=stats,
                            dept_stats=dept_stats, escalated_count=escalated_count,
                            all_departments=all_departments)


@app.route('/admin/complaint/<int:complaint_id>/reassign', methods=['POST'])
def reassign_complaint(complaint_id):
    """Lets an admin manually move a complaint to a different department -
    useful when a citizen picked the wrong category, or an issue turns out
    to involve two departments (e.g. a BWSSB leak that damaged a road)."""
    if not logged_in_as('admin'):
        return redirect(url_for('login'))

    new_department = request.form['department']
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db = get_db()
    db.execute('UPDATE complaints SET department = ?, updated_at = ? WHERE id = ?',
               (new_department, now, complaint_id))
    db.commit()
    flash(f'Complaint #{complaint_id} reassigned to {new_department}.')
    return redirect(url_for('admin_dashboard'))


# ---------- PUBLIC MAP ----------

@app.route('/map')
def public_map():
    """A publicly viewable map of reported issues - this is the
    'transparency' half of CivicTrack: anyone (not just officials) can see
    what's been reported and what's still open, plotted by location."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    complaints = db.execute('''
        SELECT id, category, department, ward, status, latitude, longitude, description
        FROM complaints
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    ''').fetchall()

    # Convert to plain dictionaries so we can safely turn them into JSON for the map's JavaScript.
    points = [dict(c) for c in complaints]
    return render_template('public_map.html', points=points)


if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    app.run(debug=True)
