import os
import sqlite3
from datetime import datetime, date, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key-before-deploying")

# Render's filesystem is ephemeral by default. Set DATABASE_PATH to a mounted
# persistent disk path if you want SQLite data to survive restarts/redeploys.
DATABASE_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parent / "library.db"))

def db_connection():
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def query_db(sql, params=(), fetch=True):
    conn = db_connection()
    try:
        cur = conn.execute(sql, params)
        if fetch:
            return [dict(row) for row in cur.fetchall()]
        conn.commit()
        return None
    finally:
        conn.close()

def init_db():
    conn = db_connection()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member','admin')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            isbn TEXT DEFAULT '',
            description TEXT,
            total_copies INTEGER NOT NULL DEFAULT 1,
            available_copies INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS borrowings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK(status IN ('Pending','Approved','Borrowed','Returned','Rejected')),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
        );
        """)
        count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        if count == 0:
            conn.executemany("""
                INSERT INTO books (title,author,category,isbn,description,total_copies,available_copies)
                VALUES (?,?,?,?,?,?,?)
            """, [
                ("The Little Prince", "Antoine de Saint-Exupéry", "Fiction", "9780156012195",
                 "A poetic classic about friendship, love, and seeing with the heart.", 3, 3),
                ("Pride and Prejudice", "Jane Austen", "Classic", "9780141439518",
                 "A classic novel of manners, family, and first impressions.", 2, 2),
                ("Atomic Habits", "James Clear", "Self-help", "9780735211292",
                 "A practical guide to building good habits and breaking bad ones.", 2, 2),
                ("Noli Me Tangere", "José Rizal", "Filipino Literature", "9789710810735",
                 "José Rizal's landmark novel on colonial Philippine society.", 4, 4),
                ("Introduction to Python", "Community Edition", "Technology", "9780000000001",
                 "A beginner-friendly introduction to programming concepts.", 2, 2),
            ])
        conn.commit()
    finally:
        conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access is required.", "danger")
            return redirect(url_for("index"))
        return fn(*args, **kwargs)
    return wrapped

@app.context_processor
def inject_globals():
    return {"current_user": session.get("user_name"), "user_role": session.get("role")}

@app.route("/")
def index():
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    sql = "SELECT * FROM books WHERE 1=1"
    params = []
    if search:
        sql += " AND (title LIKE ? OR author LIKE ? OR isbn LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY title"
    books = query_db(sql, tuple(params))
    categories = query_db("SELECT DISTINCT category FROM books ORDER BY category")
    return render_template("index.html", books=books, categories=categories, q=search, selected_category=category)

@app.route("/book/<int:book_id>")
def book_detail(book_id):
    rows = query_db("SELECT * FROM books WHERE id=?", (book_id,))
    if not rows:
        flash("Book not found.", "danger")
        return redirect(url_for("index"))
    return render_template("book_detail.html", book=rows[0])

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Enter your name and email, and use a password with at least 8 characters.", "warning")
            return render_template("register.html")
        try:
            query_db("INSERT INTO users (name,email,password_hash) VALUES (?,?,?)",
                     (name, email, generate_password_hash(password)), fetch=False)
            flash("Account created. You can now sign in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "danger")
        except sqlite3.Error:
            flash("The database could not save your account. Please try again.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        rows = query_db("SELECT * FROM users WHERE email=?", (email,))
        if rows and check_password_hash(rows[0]["password_hash"], password):
            user = rows[0]
            session.update(user_id=user["id"], user_name=user["name"], role=user["role"])
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "my_borrowings"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("index"))

@app.route("/borrow/<int:book_id>", methods=["POST"])
@login_required
def borrow_book(book_id):
    rows = query_db("SELECT * FROM books WHERE id=?", (book_id,))
    if not rows:
        flash("Book not found.", "danger")
    elif rows[0]["available_copies"] < 1:
        flash("This book is currently unavailable.", "warning")
    else:
        existing = query_db("""SELECT id FROM borrowings
            WHERE user_id=? AND book_id=? AND status IN ('Pending','Approved','Borrowed')""",
            (session["user_id"], book_id))
        if existing:
            flash("You already have an active request for this book.", "warning")
        else:
            query_db("INSERT INTO borrowings (user_id,book_id) VALUES (?,?)",
                     (session["user_id"], book_id), fetch=False)
            flash("Borrow request submitted. The library admin will review it.", "success")
    return redirect(url_for("book_detail", book_id=book_id))

@app.route("/my-borrowings")
@login_required
def my_borrowings():
    borrowings = query_db("""SELECT br.*, b.title, b.author FROM borrowings br
        JOIN books b ON b.id=br.book_id WHERE br.user_id=?
        ORDER BY br.requested_at DESC""", (session["user_id"],))
    return render_template("my_borrowings.html", borrowings=borrowings)

@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    stats = {
        "books": query_db("SELECT COUNT(*) AS n FROM books")[0]["n"],
        "members": query_db("SELECT COUNT(*) AS n FROM users WHERE role='member'")[0]["n"],
        "pending": query_db("SELECT COUNT(*) AS n FROM borrowings WHERE status='Pending'")[0]["n"],
        "borrowed": query_db("SELECT COUNT(*) AS n FROM borrowings WHERE status='Borrowed'")[0]["n"],
    }
    borrowings = query_db("""SELECT br.*, u.name AS member_name, b.title AS book_title
        FROM borrowings br JOIN users u ON u.id=br.user_id JOIN books b ON b.id=br.book_id
        ORDER BY br.requested_at DESC LIMIT 30""")
    return render_template("admin.html", stats=stats, borrowings=borrowings)

@app.route("/admin/books", methods=["GET", "POST"])
@login_required
@admin_required
def admin_books():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "General").strip() or "General"
        isbn = request.form.get("isbn", "").strip()
        description = request.form.get("description", "").strip()
        try:
            copies = max(1, int(request.form.get("copies", "1") or 1))
        except ValueError:
            copies = 1
        if not title or not author:
            flash("Title and author are required.", "warning")
        else:
            query_db("""INSERT INTO books (title,author,category,isbn,description,total_copies,available_copies)
                VALUES (?,?,?,?,?,?,?)""",
                (title, author, category, isbn, description, copies, copies), fetch=False)
            flash("Book added to the catalog.", "success")
            return redirect(url_for("admin_books"))
    books = query_db("SELECT * FROM books ORDER BY title")
    return render_template("admin_books.html", books=books)

@app.route("/admin/books/<int:book_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_book(book_id):
    try:
        query_db("DELETE FROM books WHERE id=?", (book_id,), fetch=False)
        flash("Book removed.", "success")
    except sqlite3.Error:
        flash("Could not remove this book because of related borrowing history.", "danger")
    return redirect(url_for("admin_books"))

@app.route("/admin/borrowings/<int:borrowing_id>", methods=["POST"])
@login_required
@admin_required
def update_borrowing(borrowing_id):
    new_status = request.form.get("status")
    allowed = {"Approved", "Borrowed", "Returned", "Rejected"}
    if new_status not in allowed:
        flash("Invalid borrowing status.", "danger")
        return redirect(url_for("admin_dashboard"))
    rows = query_db("SELECT * FROM borrowings WHERE id=?", (borrowing_id,))
    if not rows:
        flash("Borrowing request not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    old_status = rows[0]["status"]
    book_id = rows[0]["book_id"]
    if new_status == "Borrowed" and old_status != "Borrowed":
        book = query_db("SELECT available_copies FROM books WHERE id=?", (book_id,))
        if not book or book[0]["available_copies"] < 1:
            flash("No available copies remain.", "warning")
            return redirect(url_for("admin_dashboard"))
        query_db("UPDATE books SET available_copies=available_copies-1 WHERE id=?", (book_id,), fetch=False)
    if old_status == "Borrowed" and new_status == "Returned":
        query_db("UPDATE books SET available_copies=MIN(total_copies, available_copies+1) WHERE id=?",
                 (book_id,), fetch=False)
    query_db("UPDATE borrowings SET status=? WHERE id=?", (new_status, borrowing_id), fetch=False)
    flash("Borrowing status updated.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/health")
def health():
    return {"status": "ok"}

@app.cli.command("init-db")
def init_db_command():
    init_db()
    print(f"SQLite database initialized at {DATABASE_PATH}")

@app.cli.command("create-admin")
def create_admin_command():
    init_db()
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "")
    if len(password) < 8:
        raise SystemExit("Set ADMIN_PASSWORD to a password of at least 8 characters.")
    email = username.lower() if "@" in username else f"{username.lower()}@library.local"
    existing = query_db("SELECT id FROM users WHERE email=?", (email,))
    if existing:
        query_db("UPDATE users SET name=?, password_hash=?, role='admin' WHERE id=?",
                 (username, generate_password_hash(password), existing[0]["id"]), fetch=False)
    else:
        query_db("INSERT INTO users (name,email,password_hash,role) VALUES (?,?,?,'admin')",
                 (username, email, generate_password_hash(password)), fetch=False)
    print(f"Admin account ready. Sign in with email: {email}")

# Initialize tables and sample catalog for local runs and Render startup.
try:
    init_db()
except Exception as exc:
    # Keep import/startup error visible in logs; health endpoint remains simple.
    print(f"Database initialization warning: {exc}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
