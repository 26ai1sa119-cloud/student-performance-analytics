"""
Student Performance Analytics & Record Management System
Single-file Python project  |  pip install flask  |  python app.py seed  |  python app.py
Open: http://127.0.0.1:5000
"""
import csv
import io
import random
import sqlite3
import sys
from datetime import date, timedelta
from statistics import mean

from flask import Flask, Response, flash, g, redirect, render_template, request, url_for
from jinja2 import DictLoader

DB_FILE = "student.db"
app = Flask(__name__)
app.secret_key = "change-this-secret"

# ----------------------------------------------------------------------------
# 1. DATA LAYER (normalized relational schema)
# ----------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    department TEXT NOT NULL,
    semester INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    credits INTEGER NOT NULL DEFAULT 3
);
CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE (student_id, course_id)
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    assessment TEXT NOT NULL,
    score REAL NOT NULL,
    max_score REAL NOT NULL DEFAULT 100,
    recorded_on TEXT NOT NULL
);
"""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    con = sqlite3.connect(DB_FILE)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


# ----------------------------------------------------------------------------
# 2. BUSINESS LOGIC / ANALYTICS
# ----------------------------------------------------------------------------
def grade_letter(p):
    for cutoff, letter in ((90, "A"), (75, "B"), (60, "C"), (50, "D")):
        if p >= cutoff:
            return letter
    return "F"


def trend_slope(values):
    """Least-squares slope: change in score % per assessment."""
    n = len(values)
    if n < 3:
        return 0.0
    xm, ym = (n - 1) / 2, mean(values)
    den = sum((x - xm) ** 2 for x in range(n))
    return round(sum((x - xm) * (y - ym) for x, y in enumerate(values)) / den, 2)


def student_report(student):
    rows = db().execute(
        """SELECT r.score, r.max_score, r.recorded_on, r.assessment, c.code
           FROM results r
           JOIN enrollments e ON e.id = r.enrollment_id
           JOIN courses c ON c.id = e.course_id
           WHERE e.student_id = ? ORDER BY r.recorded_on, r.id""",
        (student["id"],),
    ).fetchall()

    timeline, per_course = [], {}
    for r in rows:
        p = round(r["score"] / r["max_score"] * 100, 2)
        timeline.append({"date": r["recorded_on"], "percent": p,
                         "course": r["code"], "assessment": r["assessment"]})
        per_course.setdefault(r["code"], []).append(p)

    percents = [t["percent"] for t in timeline]
    avg = round(mean(percents), 2) if percents else None
    slope = trend_slope(percents)

    level, reasons = "unknown", []
    if avg is not None:
        level = "low"
        if avg < 50:
            level = "high"
            reasons.append(f"Average {avg}% is below 50%")
        elif avg < 60:
            level = "medium"
            reasons.append(f"Average {avg}% is below 60%")
        if slope < -3:
            level = {"low": "medium", "medium": "high"}.get(level, level)
            reasons.append(f"Declining trend ({slope} per assessment)")
        weak = [c for c, v in per_course.items() if mean(v) < 40]
        if weak:
            level = "medium" if level == "low" else level
            reasons.append("Weak in: " + ", ".join(weak))

    return {
        "student": student, "average": avg,
        "grade": grade_letter(avg) if avg is not None else "-",
        "slope": slope, "risk": level, "reasons": reasons,
        "course_avg": {c: round(mean(v), 2) for c, v in per_course.items()},
        "timeline": timeline,
    }


def all_reports():
    students = db().execute("SELECT * FROM students ORDER BY roll_no").fetchall()
    return [student_report(s) for s in students]


# ----------------------------------------------------------------------------
# 3. PRESENTATION LAYER (HTML templates kept inside this file)
# ----------------------------------------------------------------------------
TEMPLATES = {
    "base.html": """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EduTrack - Student Analytics</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#f4f6fb;--card:#fff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--brand:#6366f1}
.dark{--bg:#0b1020;--card:#151b2e;--text:#e5e7eb;--muted:#94a3b8;--line:#243049}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--text);display:flex;min-height:100vh}
a{color:var(--brand);text-decoration:none}
.side{width:230px;background:linear-gradient(180deg,#4f46e5,#7c3aed);color:#fff;padding:20px 14px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:18px}
.logo{font-size:22px;font-weight:700;padding:0 8px}
.side nav{display:flex;flex-direction:column;gap:4px;flex:1}
.side nav a{color:#e0e7ff;padding:10px 12px;border-radius:10px;transition:.2s}
.side nav a:hover{background:#ffffff26}.side nav a.on{background:#fff;color:#4f46e5;font-weight:600}
.theme{background:#ffffff26;color:#fff;border:0;padding:10px;border-radius:10px;cursor:pointer}
main{flex:1;padding:28px;max-width:1200px;margin:auto;width:100%;min-width:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:18px;box-shadow:0 4px 18px #0000000d;animation:up .4s ease;overflow-x:auto}
@keyframes up{from{opacity:0;transform:translateY(10px)}}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}
.stat{color:#fff;border:0;font-size:14px}.stat b{font-size:34px;display:block;margin-top:4px}
.g1{background:linear-gradient(135deg,#6366f1,#8b5cf6)}.g2{background:linear-gradient(135deg,#06b6d4,#3b82f6)}.g3{background:linear-gradient(135deg,#f43f5e,#f97316)}
h2,h3{margin-top:0}
table{width:100%;border-collapse:collapse}
th{color:var(--muted);font-size:12px;text-transform:uppercase}
th,td{padding:10px 8px;border-bottom:1px solid var(--line);font-size:14px;text-align:left}
tr:hover td{background:#6366f112}
input,select{width:100%;padding:10px 12px;margin:5px 0;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--text);font-size:14px}
input:focus,select:focus{outline:2px solid var(--brand);border-color:transparent}
button{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border:0;padding:9px 16px;border-radius:10px;cursor:pointer;font-weight:600;transition:.2s}
button:hover{transform:translateY(-1px);box-shadow:0 6px 14px #6366f155}
button.del{background:linear-gradient(135deg,#ef4444,#dc2626)}
.badge{color:#fff;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;background:#6b7280;text-transform:uppercase}
.high{background:#ef4444}.medium{background:#f59e0b}.low{background:#10b981}
.av{display:inline-flex;width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#ec4899);color:#fff;align-items:center;justify-content:center;font-weight:700;font-size:13px;margin-right:6px}
.av.big{width:62px;height:62px;font-size:26px}
.msg{position:fixed;top:18px;right:18px;background:#10b981;color:#fff;padding:12px 18px;border-radius:12px;box-shadow:0 8px 24px #0003;z-index:9;animation:up .3s}
@media(max-width:800px){body{flex-direction:column}.side{width:100%;height:auto;position:static;flex-direction:row;align-items:center;flex-wrap:wrap}.side nav{flex-direction:row;flex-wrap:wrap}.logo span{display:none}main{padding:14px}}
@media print{.side,.noprint{display:none}body{display:block}.card{box-shadow:none}}
</style>
<script>if(localStorage.theme==='dark')document.documentElement.classList.add('dark');</script>
<script>const cs=getComputedStyle(document.documentElement);Chart.defaults.color=cs.getPropertyValue('--muted');Chart.defaults.borderColor=cs.getPropertyValue('--line');</script>
</head><body>
<aside class="side"><div class="logo">🎓 <span>EduTrack</span></div>
<nav>
<a class="{{ 'on' if request.endpoint=='dashboard' }}" href="{{ url_for('dashboard') }}">📊 Dashboard</a>
<a class="{{ 'on' if request.endpoint in ('students','student_detail','edit_student','report_page') }}" href="{{ url_for('students') }}">👨‍🎓 Students</a>
<a class="{{ 'on' if request.endpoint in ('grades','edit_result') }}" href="{{ url_for('grades') }}">📝 Enter Grades</a>
<a href="{{ url_for('export_csv') }}">📄 Export CSV</a>
</nav>
<button class="theme" onclick="localStorage.theme=document.documentElement.classList.toggle('dark')?'dark':'light';location.reload()">🌓 Dark / Light</button></aside>
<main>
{% for m in get_flashed_messages() %}<div class="msg">{{ m }}</div>{% endfor %}
{% block body %}{% endblock %}
</main>
<script>setTimeout(()=>document.querySelectorAll('.msg').forEach(e=>e.remove()),3500)</script>
</body></html>""",

    "dashboard.html": """{% extends "base.html" %}{% block body %}
<div class="grid">
  <div class="card stat g1">👨‍🎓 Total Students<b>{{ total }}</b></div>
  <div class="card stat g2">📈 Overall Average<b>{{ overall }}%</b></div>
  <div class="card stat g3">⚠️ At-Risk Students<b>{{ risky|length }}</b></div>
</div>
<div class="grid">
  <div class="card"><h3>Average % by Course</h3><canvas id="c1"></canvas></div>
  <div class="card"><h3>Grade Distribution</h3><canvas id="c2"></canvas></div>
</div>
<div class="card"><h3>⚠️ At-Risk Students</h3>
<table><tr><th>Roll</th><th>Name</th><th>Avg %</th><th>Trend</th><th>Risk</th><th>Reasons</th></tr>
{% for r in risky %}<tr>
 <td>{{ r.student.roll_no }}</td>
 <td><a href="{{ url_for('student_detail', sid=r.student.id) }}">{{ r.student.name }}</a></td>
 <td>{{ r.average }}</td><td>{{ r.slope }}</td>
 <td><span class="badge {{ r.risk }}">{{ r.risk }}</span></td><td>{{ r.reasons|join('; ') }}</td></tr>
{% else %}<tr><td colspan="6">No at-risk students 🎉</td></tr>{% endfor %}</table></div>
<script>
new Chart(c1,{type:'bar',data:{labels:{{ course_labels|tojson }},datasets:[{label:'Avg %',data:{{ course_values|tojson }},backgroundColor:'#4f46e5'}]},options:{scales:{y:{min:0,max:100}}}});
new Chart(c2,{type:'bar',data:{labels:['A','B','C','D','F'],datasets:[{label:'Students',data:{{ grade_counts|tojson }},backgroundColor:'#10b981'}]},options:{scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
</script>{% endblock %}""",

    "students.html": """{% extends "base.html" %}{% block body %}
<div class="grid">
<form class="card" method="post"><h3>Add Student</h3>
 <input name="roll_no" placeholder="Roll no" required>
 <input name="name" placeholder="Name" required>
 <input name="email" type="email" placeholder="Email" required>
 <input name="department" placeholder="Department" required>
 <input name="semester" type="number" min="1" max="8" value="1" required>
 <button>Add</button></form>
<div class="card"><input id="f" placeholder="🔍 Search by name, roll no or department..." value="{{ q }}" oninput="filt()">
<table id="tb"><tr><th>Roll</th><th>Name</th><th>Dept</th><th>Sem</th></tr>
{% for s in students %}<tr><td>{{ s.roll_no }}</td>
 <td><span class="av">{{ s.name[0] }}</span><a href="{{ url_for('student_detail', sid=s.id) }}">{{ s.name }}</a></td>
 <td>{{ s.department }}</td><td>{{ s.semester }}</td></tr>{% endfor %}</table></div>
</div><script>function filt(){const v=f.value.toLowerCase();document.querySelectorAll('#tb tr:not(:first-child)').forEach(r=>r.style.display=r.textContent.toLowerCase().includes(v)?'':'none')}filt()</script>{% endblock %}""",

    "student.html": """{% extends "base.html" %}{% block body %}
<div class="card"><div style="display:flex;gap:14px;align-items:center"><span class="av big">{{ r.student.name[0] }}</span><h2 style="margin:0">{{ r.student.name }} <small>({{ r.student.roll_no }})</small></h2></div>
<p>{{ r.student.department }} · Sem {{ r.student.semester }} · {{ r.student.email }}</p>
<p>Average: <b>{{ r.average if r.average is not none else 'N/A' }}%</b> · Grade: <b>{{ r.grade }}</b> ·
Trend: <b>{{ r.slope }}</b> · Risk: <span class="badge {{ r.risk }}">{{ r.risk }}</span></p>
{% for x in r.reasons %}<p style="color:#dc2626">• {{ x }}</p>{% endfor %}</div>
<div class="grid">
<div class="card"><h3>Performance Trend</h3><canvas id="c"></canvas></div>
<div class="card"><h3>Courses</h3><ul>
{% for e in enrollments %}<li>{{ e.code }} – {{ e.name }}: {{ r.course_avg.get(e.code, 'no grades') }}%</li>{% endfor %}</ul>
<form method="post" action="{{ url_for('enroll', sid=r.student.id) }}">
<select name="course_id">{% for c in courses %}<option value="{{ c.id }}">{{ c.code }} – {{ c.name }}</option>{% endfor %}</select>
<button>Enroll</button></form><br>
<a href="{{ url_for('edit_student', sid=r.student.id) }}"><button type="button">Edit Student</button></a>
<a href="{{ url_for('report_page', sid=r.student.id) }}"><button type="button">Report</button></a><br><br>
<form method="post" action="{{ url_for('delete_student', sid=r.student.id) }}" onsubmit="return confirm('Delete student?')">
<button class="del">Delete Student</button></form></div></div>
<div class="card"><h3>Marks</h3>
<table><tr><th>Date</th><th>Course</th><th>Assessment</th><th>Score</th><th></th></tr>
{% for m in marks %}<tr><td>{{ m.recorded_on }}</td><td>{{ m.code }}</td><td>{{ m.assessment }}</td>
<td>{{ m.score }}/{{ m.max_score }}</td>
<td><a href="{{ url_for('edit_result', rid=m.id) }}">Edit</a> |
<form method="post" action="{{ url_for('delete_result', rid=m.id) }}" style="display:inline" onsubmit="return confirm('Delete this mark?')">
<button class="del" style="padding:2px 8px">Delete</button></form></td></tr>
{% else %}<tr><td colspan="5">No marks yet</td></tr>{% endfor %}</table></div>
<script>
const t={{ r.timeline|tojson }};
new Chart(c,{type:'line',data:{labels:t.map(x=>x.date+' '+x.course),datasets:[{label:'Score %',data:t.map(x=>x.percent),borderColor:'#4f46e5'}]},options:{scales:{y:{min:0,max:100}}}});
</script>{% endblock %}""",

    "grades.html": """{% extends "base.html" %}{% block body %}
<form class="card" method="post" style="max-width:480px;margin:auto"><h3>Enter Grade</h3>
<select name="enrollment_id" required><option value="">Select student – course</option>
{% for e in enrollments %}<option value="{{ e.id }}">{{ e.roll_no }} {{ e.name }} – {{ e.code }}</option>{% endfor %}</select>
<input name="assessment" placeholder="Assessment (e.g. Midterm)" required>
<input name="score" type="number" step="0.01" placeholder="Score" required>
<input name="max_score" type="number" step="0.01" value="100" required>
<input name="recorded_on" type="date" value="{{ today }}" required>
<button>Save Grade</button></form>{% endblock %}""",
}
TEMPLATES.update({
    "edit_student.html": """{% extends "base.html" %}{% block body %}
<form class="card" method="post" style="max-width:480px;margin:auto"><h3>Edit Student</h3>
<input name="roll_no" value="{{ s.roll_no }}" required>
<input name="name" value="{{ s.name }}" required>
<input name="email" type="email" value="{{ s.email }}" required>
<input name="department" value="{{ s.department }}" required>
<input name="semester" type="number" min="1" max="8" value="{{ s.semester }}" required>
<button>Update</button></form>{% endblock %}""",

    "edit_result.html": """{% extends "base.html" %}{% block body %}
<form class="card" method="post" style="max-width:480px;margin:auto">
<h3>Edit Marks – {{ m.code }}</h3>
<input name="assessment" value="{{ m.assessment }}" required>
<input name="score" type="number" step="0.01" value="{{ m.score }}" required>
<input name="max_score" type="number" step="0.01" value="{{ m.max_score }}" required>
<input name="recorded_on" type="date" value="{{ m.recorded_on }}" required>
<button>Update</button></form>{% endblock %}""",

    "report.html": """{% extends "base.html" %}{% block body %}
<div class="card"><h2>Academic Performance Report</h2>
<p><b>Name:</b> {{ r.student.name }} &nbsp; <b>Roll No:</b> {{ r.student.roll_no }}<br>
<b>Department:</b> {{ r.student.department }} &nbsp; <b>Semester:</b> {{ r.student.semester }}<br>
<b>Generated on:</b> {{ today }}</p>
<p><b>Overall Percentage:</b> {{ r.average if r.average is not none else 'N/A' }}% &nbsp;
<b>Grade:</b> {{ r.grade }} &nbsp; <b>Trend:</b> {{ r.slope }} &nbsp;
<b>Risk:</b> <span class="badge {{ r.risk }}">{{ r.risk }}</span></p>
{% for x in r.reasons %}<p>• {{ x }}</p>{% endfor %}
<h3>Course-wise Performance</h3>
<table><tr><th>Course</th><th>Average %</th></tr>
{% for c, v in r.course_avg.items() %}<tr><td>{{ c }}</td><td>{{ v }}</td></tr>{% endfor %}</table>
<h3>Assessment Details</h3>
<table><tr><th>Date</th><th>Course</th><th>Assessment</th><th>Percent</th></tr>
{% for t in r.timeline %}<tr><td>{{ t.date }}</td><td>{{ t.course }}</td><td>{{ t.assessment }}</td><td>{{ t.percent }}</td></tr>{% endfor %}</table>
<br><button class="noprint" onclick="window.print()">Print / Save as PDF</button></div>{% endblock %}""",
})
app.jinja_loader = DictLoader(TEMPLATES)


# ----------------------------------------------------------------------------
# 4. ROUTES
# ----------------------------------------------------------------------------
@app.route("/")
def dashboard():
    reports = all_reports()
    scored = [r for r in reports if r["average"] is not None]
    counts = {g: 0 for g in "ABCDF"}
    for r in scored:
        counts[r["grade"]] += 1

    course_rows = db().execute(
        """SELECT c.code, ROUND(AVG(r.score * 100.0 / r.max_score), 2) AS avg
           FROM results r JOIN enrollments e ON e.id = r.enrollment_id
           JOIN courses c ON c.id = e.course_id GROUP BY c.code ORDER BY c.code"""
    ).fetchall()

    order = {"high": 0, "medium": 1}
    risky = sorted((r for r in reports if r["risk"] in order),
                   key=lambda r: (order[r["risk"]], r["average"]))
    return render_template(
        "dashboard.html", total=len(reports),
        overall=round(mean(r["average"] for r in scored), 2) if scored else 0,
        risky=risky, course_labels=[c["code"] for c in course_rows],
        course_values=[c["avg"] for c in course_rows],
        grade_counts=[counts[g] for g in "ABCDF"],
    )


@app.route("/students", methods=["GET", "POST"])
def students():
    if request.method == "POST":
        f = request.form
        try:
            db().execute(
                "INSERT INTO students (roll_no, name, email, department, semester) VALUES (?,?,?,?,?)",
                (f["roll_no"].strip(), f["name"].strip(), f["email"].strip(),
                 f["department"].strip(), int(f["semester"])))
            db().commit()
            flash("Student added.")
        except sqlite3.IntegrityError:
            flash("Roll number or email already exists.")
        return redirect(url_for("students"))

    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    rows = db().execute(
        "SELECT * FROM students WHERE name LIKE ? OR roll_no LIKE ? OR department LIKE ? ORDER BY roll_no",
        (like, like, like)).fetchall()
    return render_template("students.html", students=rows, q=q)


@app.route("/students/<int:sid>")
def student_detail(sid):
    s = db().execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()
    if not s:
        return "Student not found", 404
    enrollments = db().execute(
        """SELECT c.code, c.name FROM enrollments e JOIN courses c ON c.id = e.course_id
           WHERE e.student_id = ?""", (sid,)).fetchall()
    courses = db().execute("SELECT * FROM courses ORDER BY code").fetchall()
    marks = db().execute(
        """SELECT r.id, r.assessment, r.score, r.max_score, r.recorded_on, c.code
           FROM results r JOIN enrollments e ON e.id = r.enrollment_id
           JOIN courses c ON c.id = e.course_id
           WHERE e.student_id = ? ORDER BY r.recorded_on DESC, r.id DESC""", (sid,)).fetchall()
    return render_template("student.html", r=student_report(s), enrollments=enrollments,
                           courses=courses, marks=marks)


@app.route("/students/<int:sid>/enroll", methods=["POST"])
def enroll(sid):
    try:
        db().execute("INSERT INTO enrollments (student_id, course_id) VALUES (?,?)",
                     (sid, int(request.form["course_id"])))
        db().commit()
        flash("Enrolled successfully.")
    except sqlite3.IntegrityError:
        flash("Already enrolled in this course.")
    return redirect(url_for("student_detail", sid=sid))


@app.route("/students/<int:sid>/delete", methods=["POST"])
def delete_student(sid):
    db().execute("DELETE FROM students WHERE id = ?", (sid,))
    db().commit()
    flash("Student deleted.")
    return redirect(url_for("students"))


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
def edit_student(sid):
    s = db().execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()
    if not s:
        return "Student not found", 404
    if request.method == "POST":
        f = request.form
        try:
            db().execute(
                "UPDATE students SET roll_no=?, name=?, email=?, department=?, semester=? WHERE id=?",
                (f["roll_no"].strip(), f["name"].strip(), f["email"].strip(),
                 f["department"].strip(), int(f["semester"]), sid))
            db().commit()
            flash("Student updated.")
            return redirect(url_for("student_detail", sid=sid))
        except sqlite3.IntegrityError:
            flash("Roll number or email already exists.")
    return render_template("edit_student.html", s=s)


@app.route("/results/<int:rid>/edit", methods=["GET", "POST"])
def edit_result(rid):
    m = db().execute(
        """SELECT r.*, e.student_id, c.code FROM results r
           JOIN enrollments e ON e.id = r.enrollment_id JOIN courses c ON c.id = e.course_id
           WHERE r.id = ?""", (rid,)).fetchone()
    if not m:
        return "Mark not found", 404
    if request.method == "POST":
        f = request.form
        score, mx = float(f["score"]), float(f["max_score"])
        if mx <= 0 or not 0 <= score <= mx:
            flash("Score must be between 0 and max score.")
        else:
            db().execute(
                "UPDATE results SET assessment=?, score=?, max_score=?, recorded_on=? WHERE id=?",
                (f["assessment"].strip(), score, mx, f["recorded_on"], rid))
            db().commit()
            flash("Marks updated.")
            return redirect(url_for("student_detail", sid=m["student_id"]))
    return render_template("edit_result.html", m=m)


@app.route("/results/<int:rid>/delete", methods=["POST"])
def delete_result(rid):
    row = db().execute(
        "SELECT e.student_id FROM results r JOIN enrollments e ON e.id = r.enrollment_id WHERE r.id = ?",
        (rid,)).fetchone()
    if not row:
        return "Mark not found", 404
    db().execute("DELETE FROM results WHERE id = ?", (rid,))
    db().commit()
    flash("Mark deleted.")
    return redirect(url_for("student_detail", sid=row["student_id"]))


@app.route("/students/<int:sid>/report")
def report_page(sid):
    s = db().execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()
    if not s:
        return "Student not found", 404
    return render_template("report.html", r=student_report(s), today=date.today().isoformat())


@app.route("/export.csv")
def export_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Roll No", "Name", "Department", "Semester", "Average %", "Grade", "Trend", "Risk"])
    for r in all_reports():
        st = r["student"]
        w.writerow([st["roll_no"], st["name"], st["department"], st["semester"],
                    r["average"] if r["average"] is not None else "", r["grade"], r["slope"], r["risk"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=performance_report.csv"})


@app.route("/grades", methods=["GET", "POST"])
def grades():
    if request.method == "POST":
        f = request.form
        score, mx = float(f["score"]), float(f["max_score"])
        if mx <= 0 or not 0 <= score <= mx:
            flash("Score must be between 0 and max score.")
        else:
            db().execute(
                "INSERT INTO results (enrollment_id, assessment, score, max_score, recorded_on) VALUES (?,?,?,?,?)",
                (int(f["enrollment_id"]), f["assessment"].strip(), score, mx, f["recorded_on"]))
            db().commit()
            flash("Grade saved.")
        return redirect(url_for("grades"))

    enrollments = db().execute(
        """SELECT e.id, s.roll_no, s.name, c.code FROM enrollments e
           JOIN students s ON s.id = e.student_id JOIN courses c ON c.id = e.course_id
           ORDER BY s.roll_no, c.code""").fetchall()
    return render_template("grades.html", enrollments=enrollments, today=date.today().isoformat())


# ----------------------------------------------------------------------------
# 5. DEMO DATA  ->  python app.py seed
# ----------------------------------------------------------------------------
def seed():
    random.seed(7)
    con = sqlite3.connect(DB_FILE)
    con.executescript("DROP TABLE IF EXISTS results; DROP TABLE IF EXISTS enrollments;"
                      "DROP TABLE IF EXISTS courses; DROP TABLE IF EXISTS students;")
    con.executescript(SCHEMA)
    names = ["Aarav Sharma", "Isha Verma", "Rohan Patel", "Ananya Gupta", "Karan Mehta",
             "Sneha Joshi", "Vikram Singh", "Priya Nair", "Arjun Reddy", "Diya Kapoor",
             "Manav Jain", "Riya Soni", "Yash Tiwari", "Neha Agrawal", "Harsh Malviya"]
    depts = ["Computer Science", "Electronics", "Mechanical"]
    courses = [("CS101", "Programming Fundamentals", 4), ("CS102", "Database Systems", 3),
               ("MA101", "Engineering Mathematics", 4), ("PH101", "Applied Physics", 3)]
    con.executemany("INSERT INTO courses (code, name, credits) VALUES (?,?,?)", courses)
    course_ids = [r[0] for r in con.execute("SELECT id FROM courses")]

    for i, name in enumerate(names, 1):
        cur = con.execute(
            "INSERT INTO students (roll_no, name, email, department, semester) VALUES (?,?,?,?,?)",
            (f"2024{i:03d}", name, f"{name.split()[0].lower()}{i}@college.edu",
             random.choice(depts), random.randint(1, 4)))
        sid = cur.lastrowid
        base = random.choice([35, 48, 58, 68, 75, 85])   # ability level
        drift = random.choice([-4, -1, 0, 1, 3])          # improving / declining
        for cid in random.sample(course_ids, 3):
            eid = con.execute("INSERT INTO enrollments (student_id, course_id) VALUES (?,?)",
                              (sid, cid)).lastrowid
            for k, a in enumerate(["Quiz 1", "Quiz 2", "Midterm", "Assignment", "Quiz 3"]):
                score = max(0, min(100, base + drift * k + random.randint(-8, 8)))
                when = (date.today() - timedelta(days=(5 - k) * 18)).isoformat()
                con.execute("INSERT INTO results (enrollment_id, assessment, score, max_score, recorded_on)"
                            " VALUES (?,?,?,100,?)", (eid, a, score, when))
    con.commit()
    con.close()
    print("Demo data created in", DB_FILE)


if __name__ == "__main__":
    init_db()
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed()
    else:
        app.run(debug=True)