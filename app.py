import os
import sqlite3
from functools import wraps
from pathlib import Path
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for, Response
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('DATABASE_PATH', BASE_DIR / 'instance' / 'feedbackhub.sqlite3'))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-only-change-this-before-deploying'),
    DATABASE=str(DB_PATH),
    MAX_CONTENT_LENGTH=1 * 1024 * 1024
)
csrf = CSRFProtect(app)


def get_db():
    """Retrieve or create request-scoped SQLite connection."""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'], timeout=20)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
        g.db.execute('PRAGMA journal_mode=WAL')
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    """Close the database connection at the end of the request context."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize relational database tables, integrity constraints, indexes, and analytics view."""
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','student')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS forms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_by INTEGER NOT NULL REFERENCES users(id),
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','closed')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        form_id INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'rating' CHECK(kind IN ('rating','text')),
        required INTEGER NOT NULL DEFAULT 1,
        position INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        form_id INTEGER NOT NULL REFERENCES forms(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(form_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
        question_id INTEGER NOT NULL REFERENCES questions(id),
        rating INTEGER CHECK(rating IS NULL OR rating BETWEEN 1 AND 5),
        comment TEXT,
        UNIQUE(submission_id, question_id)
    );

    -- Performance Indexes for foreign key lookups and aggregation queries
    CREATE INDEX IF NOT EXISTS idx_forms_status ON forms(status);
    CREATE INDEX IF NOT EXISTS idx_submissions_form ON submissions(form_id);
    CREATE INDEX IF NOT EXISTS idx_submissions_user_form ON submissions(user_id, form_id);
    CREATE INDEX IF NOT EXISTS idx_answers_question ON answers(question_id);

    -- Reporting View for rating metric aggregation
    CREATE VIEW IF NOT EXISTS v_question_summary AS
    SELECT 
        q.id AS question_id,
        q.form_id,
        q.text AS question_text,
        f.title AS form_title,
        ROUND(AVG(a.rating), 2) AS avg_rating,
        COUNT(a.rating) AS total_ratings
    FROM questions q
    JOIN forms f ON f.id = q.form_id
    LEFT JOIN answers a ON a.question_id = q.id
    WHERE q.kind = 'rating'
    GROUP BY q.id;
    """)
    db.commit()
    seed_initial_data(db)


def seed_initial_data(db):
    """Seed default administrator and 3 realistic sample forms if not already present."""
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@feedbackhub.com').strip().lower()
    admin_password = os.environ.get('ADMIN_PASSWORD', 'AdminPassword123!')
    admin_name = os.environ.get('ADMIN_NAME', 'System Administrator')

    # 1. Ensure Admin user exists
    admin = db.execute('SELECT id FROM users WHERE email = ?', (admin_email,)).fetchone()
    if not admin:
        cur = db.execute(
            'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
            (admin_name, admin_email, generate_password_hash(admin_password), 'admin')
        )
        admin_id = cur.lastrowid
        db.commit()
    else:
        admin_id = admin['id']

    # 2. Check if sample forms are already seeded
    form_count = db.execute('SELECT COUNT(*) FROM forms').fetchone()[0]
    if form_count == 0:
        sample_forms = [
            {
                'title': 'Course & Instructor Feedback: DBMS (CS301)',
                'description': 'Please share your feedback regarding course syllabus coverage, lecture clarity, and hands-on SQL laboratory assignments for Database Management Systems.',
                'status': 'published',
                'questions': [
                    ('How clearly did the instructor explain core database concepts (Normalization, ER Modeling, Indexing)?', 'rating'),
                    ('How would you rate the hands-on lab sessions and SQL query practice?', 'rating'),
                    ('Were the textbook references and practice problem sets helpful for your understanding?', 'rating'),
                    ('What topics did you find most challenging, and what can be improved in future lecture sessions?', 'text')
                ]
            },
            {
                'title': 'Campus Facilities & Computing Infrastructure Survey',
                'description': 'Help campus administration evaluate and improve computer laboratory hardware, high-speed Wi-Fi connectivity, library quiet zones, and study spaces.',
                'status': 'published',
                'questions': [
                    ('How satisfied are you with the computer lab workstations, software availability, and internet speed?', 'rating'),
                    ('How would you rate library resources, study desks, and access to technical journals?', 'rating'),
                    ('Rate the overall hygiene, cleanliness, and maintenance of academic classrooms.', 'rating'),
                    ('What specific equipment or facilities would you like to see upgraded or added on campus?', 'text')
                ]
            },
            {
                'title': 'Student Experience & Academic Mentorship Feedback',
                'description': 'Share your perspective on peer collaboration, career guidance workshops, extracurricular technical clubs, and faculty mentoring this semester.',
                'status': 'published',
                'questions': [
                    ('How accessible and supportive were your faculty advisors and mentors when seeking academic help?', 'rating'),
                    ('How would you rate technical workshops, hackathons, and guest speaker seminars held this term?', 'rating'),
                    ('Rate your overall academic growth and satisfaction with student life this semester.', 'rating'),
                    ('What suggestions or ideas do you have to make student mentorship and campus life even better?', 'text')
                ]
            }
        ]

        for form in sample_forms:
            with db:
                f_cur = db.execute(
                    'INSERT INTO forms (title, description, created_by, status) VALUES (?, ?, ?, ?)',
                    (form['title'], form['description'], admin_id, form['status'])
                )
                form_id = f_cur.lastrowid
                db.executemany(
                    'INSERT INTO questions (form_id, text, kind, position) VALUES (?, ?, ?, ?)',
                    [(form_id, text, kind, idx) for idx, (text, kind) in enumerate(form['questions'])]
                )


def login_required(view):
    """Enforce authentication on views."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please sign in to continue.', 'info')
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    """Enforce RBAC role checking on views."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get('role') != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def current_user():
    """Retrieve logged-in user profile from session context."""
    if not session.get('user_id'):
        return None
    return get_db().execute('SELECT id, name, email, role FROM users WHERE id=?', (session['user_id'],)).fetchone()


@app.context_processor
def inject_user():
    return {'current_user': current_user()}


@app.get('/health')
def health():
    return {'status': 'ok'}, 200


@app.route('/')
def home():
    db = get_db()
    stats = {
        'forms': db.execute("SELECT COUNT(*) FROM forms WHERE status='published'").fetchone()[0],
        'responses': db.execute('SELECT COUNT(*) FROM submissions').fetchone()[0],
        'students': db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0]
    }
    return render_template('index.html', stats=stats)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not name or len(name) > 80 or '@' not in email or len(password) < 8:
            flash('Enter a valid name and email. Password must be at least 8 characters.', 'error')
        else:
            try:
                db = get_db()
                cur = db.execute(
                    'INSERT INTO users(name, email, password_hash, role) VALUES(?,?,?,?)',
                    (name, email, generate_password_hash(password), 'student')
                )
                db.commit()
                session.clear()
                session.update(user_id=cur.lastrowid, role='student')
                flash('Account created. Welcome to FeedbackHub!', 'success')
                return redirect(url_for('student_dashboard'))
            except sqlite3.IntegrityError:
                flash('An account with that email already exists.', 'error')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = get_db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session.update(user_id=user['id'], role=user['role'])
            flash(f"Welcome back, {user['name']}.", 'success')
            return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'student_dashboard'))
        flash('Incorrect email or password.', 'error')
    return render_template('login.html')


@app.post('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been signed out.', 'success')
    return redirect(url_for('home'))


@app.route('/student/dashboard')
@role_required('student')
def student_dashboard():
    forms = get_db().execute("""
        SELECT f.*, u.name AS creator,
               EXISTS(SELECT 1 FROM submissions s WHERE s.form_id=f.id AND s.user_id=?) AS completed
        FROM forms f
        JOIN users u ON u.id = f.created_by
        WHERE f.status = 'published'
        ORDER BY f.created_at DESC
    """, (session['user_id'],)).fetchall()
    return render_template('student_dashboard.html', forms=forms)


@app.route('/student/form/<int:form_id>', methods=['GET', 'POST'])
@role_required('student')
def feedback_form(form_id):
    db = get_db()
    form = db.execute("SELECT * FROM forms WHERE id=? AND status='published'", (form_id,)).fetchone()
    if not form:
        abort(404)

    questions = db.execute('SELECT * FROM questions WHERE form_id=? ORDER BY position, id', (form_id,)).fetchall()
    if not questions:
        flash('This form has no questions yet.', 'error')
        return redirect(url_for('student_dashboard'))

    already = db.execute('SELECT 1 FROM submissions WHERE form_id=? AND user_id=?', (form_id, session['user_id'])).fetchone()
    if already:
        flash('You have already submitted this form.', 'info')
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        answers = []
        errors = []
        for q in questions:
            raw = request.form.get(f'rating_{q["id"]}', '').strip()
            comment = request.form.get(f'comment_{q["id"]}', '').strip()
            rating = None

            if q['kind'] == 'rating':
                try:
                    rating = int(raw) if raw else None
                except ValueError:
                    rating = None
                if q['required'] and rating is None:
                    errors.append(f'Please rate: {q["text"]}')
                elif rating is not None and rating not in range(1, 6):
                    errors.append('Ratings must be between 1 and 5.')
            elif q['required'] and not comment:
                errors.append(f'Please answer: {q["text"]}')

            answers.append((q['id'], rating, comment[:2000]))

        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            try:
                with db:
                    cur = db.execute('INSERT INTO submissions(form_id, user_id) VALUES(?,?)', (form_id, session['user_id']))
                    db.executemany(
                        'INSERT INTO answers(submission_id, question_id, rating, comment) VALUES(?,?,?,?)',
                        [(cur.lastrowid, qid, rating, comment) for qid, rating, comment in answers]
                    )
                flash('Thank you. Your feedback has been submitted.', 'success')
                return redirect(url_for('student_dashboard'))
            except sqlite3.IntegrityError:
                flash('This form has already been submitted.', 'error')
                return redirect(url_for('student_dashboard'))

    return render_template('feedback_form.html', form=form, questions=questions)


@app.route('/admin/dashboard')
@role_required('admin')
def admin_dashboard():
    db = get_db()
    stats = {
        'students': db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        'forms': db.execute('SELECT COUNT(*) FROM forms').fetchone()[0],
        'responses': db.execute('SELECT COUNT(*) FROM submissions').fetchone()[0],
        'average': db.execute('SELECT ROUND(AVG(rating),2) FROM answers WHERE rating IS NOT NULL').fetchone()[0] or 0
    }
    forms = db.execute('''
        SELECT f.*, COUNT(DISTINCT s.id) AS responses
        FROM forms f
        LEFT JOIN submissions s ON s.form_id = f.id
        GROUP BY f.id
        ORDER BY f.created_at DESC
    ''').fetchall()
    return render_template('admin_dashboard.html', stats=stats, forms=forms)


@app.route('/admin/forms/create', methods=['GET', 'POST'])
@role_required('admin')
def create_form():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        texts = request.form.getlist('question_text[]')
        kinds = request.form.getlist('question_kind[]')
        cleaned = [(t.strip(), k) for t, k in zip(texts, kinds) if t.strip()]

        if not title or len(title) > 120 or not cleaned or len(cleaned) > 30:
            flash('Add a title and between 1 and 30 questions.', 'error')
        elif any(k not in ('rating', 'text') for _, k in cleaned):
            flash('Invalid question type.', 'error')
        else:
            db = get_db()
            with db:
                cur = db.execute(
                    'INSERT INTO forms(title, description, created_by) VALUES(?,?,?)',
                    (title, description[:1000], session['user_id'])
                )
                db.executemany(
                    'INSERT INTO questions(form_id, text, kind, position) VALUES(?,?,?,?)',
                    [(cur.lastrowid, t[:300], k, i) for i, (t, k) in enumerate(cleaned)]
                )
            flash('Feedback form created as a draft.', 'success')
            return redirect(url_for('admin_dashboard'))
    return render_template('create_form.html')


@app.post('/admin/forms/<int:form_id>/status')
@role_required('admin')
def update_form_status(form_id):
    status = request.form.get('status')
    if status not in ('draft', 'published', 'closed'):
        abort(400)
    db = get_db()
    form = db.execute('SELECT id FROM forms WHERE id=?', (form_id,)).fetchone()
    if not form:
        abort(404)
    db.execute('UPDATE forms SET status=? WHERE id=?', (status, form_id))
    db.commit()
    flash(f'Form status changed to {status}.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/analytics')
@role_required('admin')
def analytics():
    db = get_db()
    summary = db.execute("""
        SELECT q.id, q.text, f.title, ROUND(AVG(a.rating), 2) AS average, COUNT(a.rating) AS count
        FROM questions q
        JOIN forms f ON f.id = q.form_id
        LEFT JOIN answers a ON a.question_id = q.id
        WHERE q.kind = 'rating'
        GROUP BY q.id
        ORDER BY f.title, q.position
    """).fetchall()

    dist_raw = db.execute('''
        SELECT rating, COUNT(*) AS total
        FROM answers
        WHERE rating IS NOT NULL
        GROUP BY rating
        ORDER BY rating
    ''').fetchall()

    # Normalize distribution dictionary to cover 1 through 5 ratings
    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for row in dist_raw:
        if row['rating'] in distribution:
            distribution[row['rating']] = row['total']

    comments = db.execute("""
        SELECT f.title, q.text, a.comment, a.rating, s.submitted_at
        FROM answers a
        JOIN submissions s ON s.id = a.submission_id
        JOIN questions q ON q.id = a.question_id
        JOIN forms f ON f.id = s.form_id
        WHERE a.comment IS NOT NULL AND TRIM(a.comment) != ''
        ORDER BY s.submitted_at DESC
        LIMIT 30
    """).fetchall()

    return render_template('analytics.html', summary=summary, distribution=distribution, comments=comments)


@app.route('/admin/export.csv')
@role_required('admin')
def export_csv():
    import csv
    from io import StringIO
    rows = get_db().execute("""
        SELECT f.title, q.text, a.rating, a.comment, s.submitted_at
        FROM answers a
        JOIN questions q ON q.id = a.question_id
        JOIN submissions s ON s.id = a.submission_id
        JOIN forms f ON f.id = s.form_id
        ORDER BY s.submitted_at DESC
    """).fetchall()
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(['Feedback form', 'Question', 'Rating', 'Comment', 'Submitted at'])
    writer.writerows([tuple(row) for row in rows])
    return Response(
        stream.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=feedbackhub-responses.csv'}
    )


@app.errorhandler(403)
def forbidden(_error):
    return render_template('error.html', code=403, message='You do not have permission to view this page.'), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template('error.html', code=404, message='The page you requested could not be found.'), 404


@app.cli.command('create-admin')
def create_admin_command():
    email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
    password = os.environ.get('ADMIN_PASSWORD', '')
    if not email or len(password) < 12:
        raise SystemExit('Set ADMIN_EMAIL and ADMIN_PASSWORD (at least 12 characters).')
    with app.app_context():
        init_db()
        db = get_db()
        try:
            db.execute(
                'INSERT INTO users(name, email, password_hash, role) VALUES(?,?,?,?)',
                ('FeedbackHub Admin', email, generate_password_hash(password), 'admin')
            )
            db.commit()
            print(f'Admin account created: {email}')
        except sqlite3.IntegrityError:
            raise SystemExit('That admin email already exists.')


@app.cli.command('init-db')
def init_db_command():
    init_db()
    print(f'Database ready at {app.config["DATABASE"]}')


with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
