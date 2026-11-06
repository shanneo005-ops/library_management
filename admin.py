
import calendar
import re
import secrets
import socket
import sqlite3
from datetime import date, timedelta
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from jinja2 import DictLoader

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

                                                                           
ADMIN_USERNAME = "Adminpogi123"
ADMIN_PASSWORD = "Password"

                                                                 
SEED_DEMO_DATA = True

                                                                                   
BOOKS_DB = Path(__file__).with_name("library.db")
BOOKS_SQL = Path(__file__).with_name("books_sqlite.sql")

# ---------------------------------------------------------------- book database
def _contains(title, term):
    return term.lower() in title.lower()      # case-insensitive, handles accents (e.g. Último)

def db():
    con = sqlite3.connect(BOOKS_DB)
    con.row_factory = lambda cur, row: {c[0]: row[i] for i, c in enumerate(cur.description)}
    con.create_function("contains", 2, _contains)
    return con

REQUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS requests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    token      TEXT NOT NULL UNIQUE,
    status     TEXT NOT NULL DEFAULT 'pending',   -- pending / borrowed / returned / declined
    book_id    INTEGER NOT NULL REFERENCES books(id),
    name       TEXT NOT NULL,
    student_id TEXT NOT NULL,
    section    TEXT NOT NULL,
    course     TEXT NOT NULL,
    year       TEXT NOT NULL,
    contact    TEXT NOT NULL,
    email      TEXT NOT NULL,
    date       TEXT NOT NULL,                      -- ISO date borrowed
    due        TEXT NOT NULL                       -- ISO date to return
)
"""

def init_db():
    """Create library.db from books_sqlite.sql if missing, and make sure the requests table exists."""
    if not BOOKS_DB.exists():
        if not BOOKS_SQL.exists():
            raise SystemExit("library.db and books_sqlite.sql are both missing - keep them next to this file.")
        con = sqlite3.connect(BOOKS_DB)
        con.executescript(BOOKS_SQL.read_text(encoding="utf-8"))
        con.commit()
        con.close()
    with db() as con:
        con.execute(REQUESTS_TABLE)

def all_books():
    with db() as con:
        return con.execute("SELECT id, title FROM books ORDER BY id").fetchall()

def search_books(term):
    with db() as con:
        return con.execute("SELECT id, title FROM books WHERE contains(title, ?) ORDER BY id", (term,)).fetchall()

def get_book(book_id):
    with db() as con:
        return con.execute("SELECT id, title FROM books WHERE id = ?", (book_id,)).fetchone()

init_db()

YEAR_LEVELS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]
FORM_FIELDS = ["name", "student_id", "section", "course", "year", "contact", "email", "date"]

# Borrow requests are stored in the "requests" table of library.db (see init_db).

                                                                          
def add_one_month(d):
    """Exactly one calendar month later (Jan 31 -> Feb 28/29, Dec 15 -> Jan 15)."""
    year = d.year + d.month // 12
    month = d.month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

def plural_days(n):
    return f"{n} day{'' if n == 1 else 's'}"

def duration_info(r):
    """Time span of a borrowed book: label, colour state and progress bar %."""
    today = date.today()
    total = (r["due"] - r["date"]).days
    used = (today - r["date"]).days
    left = (r["due"] - today).days
    pct = max(0, min(100, round(used / total * 100))) if total > 0 else 100
    if left < 0:
        return {"label": f"{plural_days(-left)} overdue", "state": "over", "pct": 100, "left": left}
    if left == 0:
        return {"label": "Due today", "state": "soon", "pct": pct, "left": left}
    return {"label": f"{plural_days(left)} left", "state": "soon" if left <= 3 else "ok",
            "pct": pct, "left": left}

def _to_req(row):
    """DB row -> dict with real date objects and the book title."""
    if row is None:
        return None
    r = dict(row)
    r["date"] = date.fromisoformat(r["date"])
    r["due"] = date.fromisoformat(r["due"])
    return r

_REQ_SELECT = ("SELECT r.*, b.title AS book FROM requests r "
               "JOIN books b ON b.id = r.book_id ")

def list_requests(status):
    with db() as con:
        rows = con.execute(_REQ_SELECT + "WHERE r.status = ? ORDER BY r.id", (status,)).fetchall()
    return [_to_req(x) for x in rows]

def get_request(req_id):
    with db() as con:
        return _to_req(con.execute(_REQ_SELECT + "WHERE r.id = ?", (req_id,)).fetchone())

def get_request_by_token(token):
    with db() as con:
        return _to_req(con.execute(_REQ_SELECT + "WHERE r.token = ?", (token,)).fetchone())

def set_status(req_id, status):
    with db() as con:
        con.execute("UPDATE requests SET status = ? WHERE id = ?", (status, req_id))

def count_pending():
    with db() as con:
        return con.execute("SELECT COUNT(*) AS n FROM requests WHERE status = 'pending'").fetchone()["n"]

def add_request(book, info, status="pending"):
    with db() as con:
        cur = con.execute(
            "INSERT INTO requests (token, status, book_id, name, student_id, section, course, year,"
            " contact, email, date, due) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (secrets.token_urlsafe(9), status, book["id"], info["name"], info["student_id"],
             info["section"], info["course"], info["year"], info["contact"], info["email"],
             info["date"].isoformat(), add_one_month(info["date"]).isoformat()))
        new_id = cur.lastrowid
    return get_request(new_id)

def book_by_title(title):
    with db() as con:
        return con.execute("SELECT id, title FROM books WHERE title = ?", (title,)).fetchone()

def seed_demo_data():
    with db() as con:
        if con.execute("SELECT COUNT(*) AS n FROM requests").fetchone()["n"]:
            return                      # already has data - don't duplicate on every restart
    t = date.today()

    pending = [
        ("Joshua Batumbakal", "Noli Me Tangere"),
        ("Jane Matimtim", "El Filibusterismo"),
        ("Darwin Karambo", "Ibong Adarna"),
        ("Justine Alatigar", "Alamat ng Saging"),
        ("Jem Boy Alakan", "Wimpy Kid")
    ]

    borrowed = [
        ("Maria Santos", "Noli Me Tangere", 25),
        ("Juan Dela Cruz", "Ibong Adarna", 12),
        ("Ana Reyes", "Wimpy Kid", 3),
        ("Pedro Lim", "El Filibusterismo", 35)
    ]

    def info(name, d, n):
        return {
            "name": name,
            "student_id": f"2026-{1000 + n}",
            "section": "LFCA311N114",
            "course": "BSIT",
            "year": "1st Year",
            "contact": "09123456789",
            "email": "student@example.com",
            "date": d
        }

    for i, (name, title) in enumerate(pending):
        book = book_by_title(title)
        if book:
            add_request(book, info(name, t - timedelta(days=i), i))

    for i, (name, title, ago) in enumerate(borrowed, start=10):
        book = book_by_title(title)
        if book:
            add_request(
                book,
                info(name, t - timedelta(days=ago), i),
                status="borrowed"
            )
def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))                                    
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()

def validate(form):
    errors = []
    labels = {"name": "Full name", "student_id": "Student ID number", "section": "Section",
              "course": "Course", "year": "Year level", "contact": "Contact number",
              "email": "Email", "date": "Date"}
    for key in FORM_FIELDS:
        if not form[key]:
            errors.append(f"{labels[key]} is required.")
    if errors:
        return errors, None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", form["email"]):
        errors.append("Please enter a valid email address.")
    if not re.fullmatch(r"[0-9+\-\s()]{7,20}", form["contact"]):
        errors.append("Please enter a valid contact number.")
    if form["year"] not in YEAR_LEVELS:
        errors.append("Please choose a year level.")
    try:
        chosen = date.fromisoformat(form["date"])
        if chosen < date.today():
            errors.append("The date cannot be in the past.")
    except ValueError:
        chosen = None
        errors.append("Please enter a valid date.")
    return errors, chosen

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapper

@app.template_filter("mdy")
def fmt_mdy(d):
    return f"{d.month:02d} - {d.day:02d} - {d.year}"

@app.template_filter("longdate")
def fmt_long(d):
    return f"{d:%B} {d.day}, {d.year}"

@app.context_processor
def inject_counts():
    return {"pending_count": count_pending()}

                                                                            
CSS = """
<style>
  :root { --bg:#dfccad; --brown:#b3905b; --tan:#dfccad; --border:#111; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); font-family:"Times New Roman", Times, serif; color:#000; }
  a { color:inherit; }
  .center-page { min-height:100vh; display:flex; align-items:center; justify-content:center; padding:16px; }
  .card { background:#fff; border:2px solid var(--border); border-radius:48px; width:100%; max-width:480px;
          padding:28px 44px 48px; text-align:center; }
  .card h1 { font-size:34px; margin:0 0 24px; line-height:1.25; }
  .btn { display:block; width:220px; margin:0 auto 28px; padding:14px 0; border:2px solid var(--border);
         border-radius:14px; font:bold 15px Arial, sans-serif; color:#000; text-decoration:none; cursor:pointer; }
  .btn-login { background:var(--brown); }
  .btn-brown { display:inline-block; background:var(--brown); border:2px solid var(--border); border-radius:12px;
         padding:12px 26px; font:bold 15px Arial, sans-serif; color:#000; text-decoration:none; cursor:pointer; }
  .btn-light { background:#fff; }
  label { display:block; text-align:left; font-size:18px; margin:18px 0 4px 4px; }
  .inp { width:100%; padding:12px 14px; border:3px solid var(--brown); border-radius:12px;
         font:16px Arial, sans-serif; background:#fff; }
  .inp.center { text-align:center; padding:14px; }
  .inp:focus { outline:none; border-color:#8a6a3a; }
  .error { color:#b00020; font-weight:bold; margin:10px 0 0; }

  
  .layout { display:flex; min-height:100vh; }
  .sidebar { width:287px; background:var(--brown); padding:24px 8px; display:flex; flex-direction:column; flex-shrink:0; }
  .sidebar h1 { font-size:38px; margin:0; }
  .sidebar h2 { font-size:24px; margin:6px 0 50px; }
  .nav a { display:flex; align-items:center; gap:14px; padding:12px 18px; margin-bottom:10px; border-radius:18px;
           color:#000; text-decoration:none; font-weight:bold; font-size:18px; }
  .nav a.active { background:#fff; }
  .badge { background:#f5b971; border-radius:50%; width:28px; height:28px; display:inline-flex;
           align-items:center; justify-content:center; font-size:14px; margin-left:4px; }
  .sidebar .spacer { flex:1; min-height:120px; }
  .sidebar hr { border:0; border-top:3px solid #000; width:calc(100% - 40px); margin:0 0 20px; }
  .sidebar .logout { color:#000; text-decoration:none; font-weight:bold; padding-left:8px; }
  .main { flex:1; padding:20px 20px 30px; min-width:0; }
  .topbar { display:flex; justify-content:space-between; align-items:center; padding:0 12px 0 48px; }
  .topbar h1 { font-size:36px; margin:12px 0 22px; }
  .topbar span { font-weight:bold; font-size:14px; }
  .stats { display:flex; gap:20px; margin-bottom:20px; flex-wrap:wrap; }
  .stat { flex:1; min-width:180px; background:#fff; border-radius:18px; padding:14px 16px; }
  .stat small { display:block; font-weight:bold; font-size:14px; }
  .stat strong { font-size:22px; display:block; margin-top:4px; padding-left:2px; }
  .panel { background:#fff; border-radius:28px; padding:18px 20px 40px; min-height:300px; }
  .panel h2 { font-size:26px; margin:0 0 18px; }
  .table-wrap { overflow-x:auto; }
  table { width:100%; border-collapse:collapse; }
  thead th { background:var(--tan); text-align:left; padding:10px 10px; font-size:15px; white-space:nowrap; }
  thead th:first-child { border-radius:14px 0 0 14px; }
  thead th:last-child { border-radius:0 14px 14px 0; text-align:center; }
  tbody td { padding:14px 10px; border-bottom:3px solid var(--brown); font-size:15px; vertical-align:middle; }
  tbody td.name { font-weight:bold; }
  .sub { font-weight:normal; font-size:12px; color:#555; margin-top:2px; }
  td.actions { text-align:center; white-space:nowrap; }
  td.actions form { display:inline; }
  .act { display:inline-block; padding:8px 24px; border:2px solid var(--border); border-radius:10px;
         font:15px "Times New Roman", serif; cursor:pointer; color:#000; text-decoration:none; background:#fff; }
  .accept { background:var(--brown); }
  .decline { margin-left:14px; }
  .flash { background:#fff8e6; border:2px solid var(--brown); border-radius:12px; padding:8px 14px; margin-bottom:14px; }
  .empty { color:#555; padding:20px 0; }
  .pill { display:inline-block; padding:3px 10px; border-radius:999px; font:bold 13px Arial, sans-serif; white-space:nowrap; }
  .pill.ok { background:#dff0d8; } .pill.soon { background:#fff0c2; } .pill.over { background:#f8d0d0; }
  .bar { height:8px; background:#eadfca; border-radius:6px; margin-top:6px; overflow:hidden; min-width:110px; }
  .bar div { height:100%; background:var(--brown); }
  .bar.over div { background:#c0392b; }
  .hint { font:13px Arial, sans-serif; color:#555; }

  
  .member-wrap { max-width:820px; margin:0 auto; padding:28px 16px 48px; }
  .member-head h1 { font-size:36px; text-align:center; margin:8px 0 24px; line-height:1.25; }
  .search-card { background:#fff; border-radius:28px; padding:16px 18px; margin-bottom:18px; }
  .search-form { display:flex; gap:12px; }
  .search-form .inp { flex:1; }
  .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px 18px; }
  .span2 { grid-column:1 / -1; }
  .field label { font-size:16px; font-weight:bold; margin:0 0 4px 4px; }
  .book-chip { background:var(--tan); border-radius:16px; padding:12px 16px; margin-bottom:18px; font-size:18px; }
  .errors { background:#fdecea; border:2px solid #c0392b; border-radius:12px; padding:10px 16px; margin-bottom:16px;
            font:14px Arial, sans-serif; }
  .errors ul { margin:4px 0 0 18px; padding:0; }
  .receipt { background:#fff; border:2px solid var(--border); border-radius:28px; padding:28px 32px; }
  .receipt h2 { text-align:center; margin:0 0 4px; font-size:28px; }
  .receipt .meta { text-align:center; color:#444; margin-bottom:6px; }
  .receipt dl { display:grid; grid-template-columns:170px 1fr; gap:8px 12px; margin:0; }
  .receipt dt { font-weight:bold; } .receipt dd { margin:0; word-break:break-word; }
  .receipt hr { border:0; border-top:2px dashed var(--brown); margin:16px 0; }
  .return-box { background:var(--tan); border-radius:16px; padding:14px; text-align:center; margin-top:6px; }
  .return-box strong { display:block; font-size:26px; margin-top:2px; }
  .receipt-actions { display:flex; gap:12px; justify-content:center; margin-top:18px; flex-wrap:wrap; }

  .qr-panel { text-align:center; }
  .qr-frame { display:inline-block; background:#fff; border:3px solid var(--border); border-radius:24px; padding:20px; margin:6px 0 14px; }
  .qr-frame img { display:block; width:280px; height:280px; image-rendering:pixelated; }
  .qr-scan { display:inline-block; background:var(--brown); border:2px solid var(--border); border-radius:16px;
             padding:8px 28px; font:bold 20px Arial, sans-serif; letter-spacing:1px; margin-bottom:10px; }
  .qr-link { display:flex; gap:12px; max-width:560px; margin:14px auto 0; }
  .qr-link .inp { flex:1; }

  @media (max-width:800px) {
    .layout { flex-direction:column; }
    .sidebar { width:100%; }
    .sidebar h2 { margin-bottom:20px; }
    .topbar { padding-left:12px; }
    .form-grid { grid-template-columns:1fr; }
    .search-form { flex-direction:column; }
    .receipt dl { grid-template-columns:1fr; gap:2px 0; }
    .receipt dd { margin-bottom:8px; }
    .card { padding:24px 24px 40px; }
  }
  @media print {
    body { background:#fff; }
    .no-print { display:none !important; }
    .sidebar, .topbar span { display:none !important; }
    .layout { display:block; }
    .member-wrap { padding:0; }
    .receipt { border:2px solid #000; }
  }
</style>
"""

TEMPLATES = {
    "base.html": """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}Library Book Management System{% endblock %}</title>""" + CSS + """
{% block head %}{% endblock %}
</head><body>{% block body %}{% endblock %}</body></html>
""",

                                                                                
    "login.html": """{% extends 'base.html' %}
{% block title %}Admin Login{% endblock %}
{% block body %}
<div class="center-page"><div class="card">
  <h1>Library Book<br>Management System</h1>
  <div style="font-weight:bold;font-size:17px">Welcome back, Admin / Staff</div>
  <div style="font-size:17px;margin-bottom:10px">Login</div>
  <form method="post" autocomplete="off">
    <label for="username">Username:</label>
    <input class="inp center" type="text" id="username" name="username" placeholder="Enter username here" required>
    <label for="password" style="margin-top:26px">Password:</label>
    <input class="inp center" type="password" id="password" name="password" placeholder="Enter password here" required>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <button class="btn btn-login" type="submit" style="margin-top:26px">Login</button>
  </form>
</div></div>
{% endblock %}
""",

    "admin_base.html": """{% extends 'base.html' %}
{% block title %}{{ title }} - Library Admin{% endblock %}
{% block body %}
<div class="layout">
  <aside class="sidebar">
    <h1>Library</h1><h2>Admin Panel</h2>
    <nav class="nav">
      <a href="{{ url_for('dashboard') }}" class="{{ 'active' if active=='dashboard' }}">&#8962;&nbsp; Dashboard</a>
      <a href="{{ url_for('borrow_requests_page') }}" class="{{ 'active' if active=='requests' }}">&#128276; Borrow Requests
        <span class="badge">{{ pending_count }}</span></a>
      <a href="{{ url_for('qr_code_page') }}" class="{{ 'active' if active=='qr' }}">&#9638;&nbsp; QR Code</a>
    </nav>
    <div class="spacer"></div>
    <hr>
    <a class="logout" href="{{ url_for('logout') }}">Logout</a>
  </aside>
  <main class="main">
    <div class="topbar"><h1>{{ title }}</h1><span>Admin</span></div>
    {% for m in get_flashed_messages() %}<div class="flash">{{ m }}</div>{% endfor %}
    {% block content %}{% endblock %}
  </main>
</div>
{% endblock %}
""",

    "dashboard.html": """{% extends 'admin_base.html' %}{% block content %}
<div class="stats">
  <div class="stat"><small>Borrowed:</small><strong>{{ borrowed|length }}</strong></div>
  <div class="stat"><small>Overdue:</small><strong>{{ overdue }}</strong></div>
  <div class="stat"><small>Pending Request:</small><strong>{{ pending_count }}</strong></div>
</div>
<div class="panel">
  <h2>Books Currently Borrowed</h2>
  {% if borrowed %}
  <div class="table-wrap"><table>
    <thead><tr><th>Members</th><th>Book</th><th>Date Borrowed</th><th>Return By</th><th>Time Left</th><th>Action</th></tr></thead>
    <tbody>
    {% for r in borrowed %}
      <tr>
        <td class="name">{{ r.name }}<div class="sub">{{ r.student_id }}</div></td>
        <td>{{ r.book }}</td>
        <td>{{ r.date|mdy }}</td>
        <td>{{ r.due|mdy }}</td>
        <td><span class="pill {{ r.state }}">{{ r.label }}</span>
            <div class="bar {{ 'over' if r.state=='over' }}"><div style="width:{{ r.pct }}%"></div></div></td>
        <td class="actions">
          <form method="post" action="{{ url_for('handle_request', req_id=r.id, action='return') }}">
            <button class="act accept">Returned</button></form>
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p class="empty">No books are currently borrowed.</p>{% endif %}
</div>
{% endblock %}""",

    "qr.html": """{% extends 'admin_base.html' %}{% block content %}
<div class="panel qr-panel">
  <h2>Member QR Code</h2>
  <p class="hint">Members scan this with their phone camera to open the borrow page. Print it and post it in the library.</p>
  <div class="qr-frame"><div id="qr"></div></div><br>
  <div class="qr-scan">SCAN TO BORROW A BOOK</div>
  <div class="hint" id="url" style="word-break:break-all"></div>
  <form class="qr-link no-print" onsubmit="draw(document.getElementById('link').value);return false;">
    <input class="inp" id="link" value="{{ link }}" aria-label="Member page link">
    <button class="btn-brown" type="submit">Update QR</button>
  </form>
  <p class="hint no-print">Using this computer on Wi-Fi? Keep the link as is. If the site is hosted online, paste its web address and press Update QR.</p>
  <div class="no-print" style="margin-top:14px"><button class="btn-brown" onclick="window.print()">Print QR Code</button></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js"></script>
<script>
  function draw(link) {
    link = link.trim();
    if (!/^https?:\\/\\//i.test(link)) link = "http://" + link;
    document.getElementById("url").textContent = link;
    var box = document.getElementById("qr");
    try {
      var qr = qrcode(0, "Q"); qr.addData(link); qr.make();
      box.innerHTML = qr.createImgTag(10, 0);
    } catch (e) {
      box.innerHTML = "<p class='error'>Could not load the QR generator. Check your internet connection and reload.</p>";
    }
  }
  draw(document.getElementById("link").value);
</script>
{% endblock %}""",

    "requests.html": """{% extends 'admin_base.html' %}{% block content %}
<div class="stats">
  <div class="stat"><small>Pending Request:</small><strong>{{ pending_count }}</strong></div>
</div>
<div class="panel">
  <h2>Pending Borrow Requests</h2>
  {% if pending %}
  <div class="table-wrap"><table>
    <thead><tr><th>Members</th><th>Book</th><th>Date Requested</th><th>Action</th></tr></thead>
    <tbody>
    {% for r in pending %}
      <tr>
        <td class="name">{{ r.name }}
          <div class="sub">ID {{ r.student_id }} &middot; {{ r.course }} &middot; {{ r.year }} &middot; {{ r.section }}</div>
          <div class="sub">{{ r.contact }} &middot; {{ r.email }}</div></td>
        <td>{{ r.book }}</td>
        <td>{{ r.date|mdy }}<div class="sub">Return by {{ r.due|mdy }}</div></td>
        <td class="actions">
          <form method="post" action="{{ url_for('handle_request', req_id=r.id, action='accept') }}"><button class="act accept">Accept</button></form>
          <form method="post" action="{{ url_for('handle_request', req_id=r.id, action='decline') }}"><button class="act decline">Decline</button></form>
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p class="empty">No pending requests.</p>{% endif %}
</div>
{% endblock %}""",

                                                                                   
    "member_base.html": """{% extends 'base.html' %}
{% block title %}Library Book Management System{% endblock %}
{% block body %}
<div class="member-wrap">
  <div class="member-head"><h1>Library Book<br>Management System</h1></div>
  {% block content %}{% endblock %}
</div>
{% endblock %}
""",

    "member_home.html": """{% extends 'member_base.html' %}{% block content %}
<div class="search-card">
  <form class="search-form" method="get" action="{{ url_for('member_home') }}">
    <input class="inp" type="search" name="q" value="{{ q }}" placeholder="Search for a book..."
           list="book-list" autocomplete="off">
    <datalist id="book-list">{% for b in all_books %}<option value="{{ b.title }}">{% endfor %}</datalist>
    <button class="btn-brown" type="submit">Search</button>
  </form>
</div>
<div class="panel">
  <h2>{{ 'Search Results' if q else 'Available Books' }}</h2>
  {% if books %}
  <div class="table-wrap"><table>
    <thead><tr><th>Book</th><th>Action</th></tr></thead>
    <tbody>
    {% for b in books %}
      <tr><td class="name">{{ b.title }}</td>
          <td class="actions"><a class="act accept" href="{{ url_for('member_request', book_id=b.id) }}">Borrow / Request</a></td></tr>
    {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p class="empty">No books found for &ldquo;{{ q }}&rdquo;.</p>{% endif %}
</div>
{% endblock %}""",

    "member_request.html": """{% extends 'member_base.html' %}{% block content %}
<div class="panel">
  <h2>Borrow Request</h2>
  <div class="book-chip">Book: <strong>{{ book.title }}</strong></div>
  {% if errors %}<div class="errors"><strong>Please fix the following:</strong>
    <ul>{% for e in errors %}<li>{{ e }}</li>{% endfor %}</ul></div>{% endif %}
  <form method="post" autocomplete="off">
    <div class="form-grid">
      <div class="field span2"><label for="name">Full Name</label>
        <input class="inp" id="name" name="name" value="{{ form.name }}" maxlength="100" required></div>
      <div class="field"><label for="student_id">Student ID Number</label>
        <input class="inp" id="student_id" name="student_id" value="{{ form.student_id }}" maxlength="100" required></div>
      <div class="field"><label for="section">Section</label>
        <input class="inp" id="section" name="section" value="{{ form.section }}" maxlength="100" required></div>
      <div class="field"><label for="course">Course</label>
        <input class="inp" id="course" name="course" value="{{ form.course }}" maxlength="100" required></div>
      <div class="field"><label for="year">Year Level</label>
        <select class="inp" id="year" name="year" required>
          <option value="" disabled {{ 'selected' if not form.year }}>Select year level</option>
          {% for y in years %}<option value="{{ y }}" {{ 'selected' if form.year == y }}>{{ y }}</option>{% endfor %}
        </select></div>
      <div class="field"><label for="contact">Contact Number</label>
        <input class="inp" id="contact" name="contact" type="tel" value="{{ form.contact }}" maxlength="20" required></div>
      <div class="field"><label for="email">Email</label>
        <input class="inp" id="email" name="email" type="email" value="{{ form.email }}" maxlength="100" required></div>
      <div class="field span2"><label for="date">Date</label>
        <input class="inp" id="date" name="date" type="date" value="{{ form.date }}" min="{{ today }}" required></div>
    </div>
    <p class="hint">The book must be returned exactly 1 month after this date.</p>
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:10px">
      <button class="btn-brown" type="submit">Submit Request</button>
      <a class="btn-brown btn-light" href="{{ url_for('member_home') }}">Cancel</a>
    </div>
  </form>
</div>
{% endblock %}""",

    "member_receipt.html": """{% extends 'member_base.html' %}{% block content %}
<div class="receipt">
  <h2>Borrowing Receipt</h2>
  <div class="meta">Receipt No. LBM-{{ '%04d' % r.id }}</div>
  <div class="meta no-print" style="font:14px Arial,sans-serif">Your request was sent to the librarian. Please keep or print this receipt.</div>
  <hr>
  <dl>
    <dt>Book</dt><dd>{{ r.book }}</dd>
    <dt>Full Name</dt><dd>{{ r.name }}</dd>
    <dt>Student ID Number</dt><dd>{{ r.student_id }}</dd>
    <dt>Course / Year</dt><dd>{{ r.course }} &middot; {{ r.year }}</dd>
    <dt>Section</dt><dd>{{ r.section }}</dd>
    <dt>Contact Number</dt><dd>{{ r.contact }}</dd>
    <dt>Email</dt><dd>{{ r.email }}</dd>
    <dt>Date Borrowed</dt><dd>{{ r.date|longdate }}</dd>
  </dl>
  <hr>
  <div class="return-box">Return the book on or before<strong>{{ r.due|longdate }}</strong>
    <span style="font:13px Arial,sans-serif">(1 month borrowing period)</span></div>
  <div class="receipt-actions no-print">
    <button class="btn-brown" onclick="window.print()">Print Receipt</button>
    <a class="btn-brown btn-light" href="{{ url_for('member_home') }}">Back to Search</a>
  </div>
</div>
{% endblock %}""",
}
app.jinja_loader = DictLoader(TEMPLATES)

                                                                                       
@app.route("/", methods=["GET", "POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USERNAME
                and request.form.get("password") == ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)

@app.route("/dashboard")
@login_required
def dashboard():
    borrowed = [dict(r, **duration_info(r)) for r in list_requests("borrowed")]
    borrowed.sort(key=lambda r: r["due"])                                        
    overdue = sum(1 for r in borrowed if r["state"] == "over")
    return render_template("dashboard.html", title="Dashboard", active="dashboard",
                           borrowed=borrowed, overdue=overdue)

@app.route("/borrow-requests")
@login_required
def borrow_requests_page():
    pending = list_requests("pending")
    return render_template("requests.html", title="Borrow Requests", active="requests",
                           pending=pending)

@app.route("/qr-code")
@login_required
def qr_code_page():
    host = request.host
    if host.split(":")[0] in ("127.0.0.1", "localhost"):      # phones can't reach "localhost"
        host = f"{get_lan_ip()}:{host.split(':')[1] if ':' in host else 80}"
    link = f"{request.scheme}://{host}{url_for('member_home')}"
    return render_template("qr.html", title="QR Code", active="qr", link=link)

@app.route("/requests/<int:req_id>/<action>", methods=["POST"])
@login_required
def handle_request(req_id, action):
    r = get_request(req_id)
    if r is None or action not in ("accept", "decline", "return"):
        abort(404)
    needed = "borrowed" if action == "return" else "pending"
    if r["status"] != needed:
        flash("That request was already handled.")
    elif action == "accept":
        set_status(req_id, "borrowed")
        flash(f"Accepted {r['name']}'s request for {r['book']}. Return by {r['due']:%m - %d - %Y}.")
    elif action == "decline":
        set_status(req_id, "declined")
        flash(f"Declined {r['name']}'s request for {r['book']}.")
    else:
        set_status(req_id, "returned")
        flash(f"{r['book']} returned by {r['name']}.")
    return redirect(url_for("dashboard" if action == "return" else "borrow_requests_page"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin_login"))

                                                                                           
@app.route("/member")
def member_home():
    q = request.args.get("q", "").strip()[:100]
    books = search_books(q) if q else all_books()
    return render_template("member_home.html", q=q, books=books, all_books=all_books())

@app.route("/member/request/<int:book_id>", methods=["GET", "POST"])
def member_request(book_id):
    book = get_book(book_id)
    if book is None:
        abort(404)
    form = {k: "" for k in FORM_FIELDS}
    form["date"] = date.today().isoformat()
    errors = []
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip()[:100] for k in FORM_FIELDS}
        errors, chosen = validate(form)
        if not errors:
            data = dict(form, date=chosen)
            r = add_request(book, data)
            return redirect(url_for("member_receipt", token=r["token"]))
    return render_template("member_request.html", book=book, form=form, errors=errors,
                           years=YEAR_LEVELS, today=date.today().isoformat())

@app.route("/member/receipt/<token>")
def member_receipt(token):
    r = get_request_by_token(token)
    if r is None:
        abort(404)
    return render_template("member_receipt.html", r=r)

if SEED_DEMO_DATA:
    seed_demo_data()

if __name__ == "__main__":
    PORT = 5000
    print(f"Staff login : http://127.0.0.1:{PORT}/")
    print(f"Member page : http://{get_lan_ip()}:{PORT}/member")
    app.run(host="0.0.0.0", port=PORT, debug=False)
