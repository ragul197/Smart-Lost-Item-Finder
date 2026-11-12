import os
import sqlite3
from datetime import datetime
from difflib import SequenceMatcher
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, g, abort, session
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "lost_found.db")
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret-key")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

CATEGORIES = ["Electronics", "ID Card", "Books & Notes", "Bags", "Keys", "Clothing", "Wallet/Purse", "Bottle", "Accessories", "Other"]
LOCATIONS = ["Classroom", "Library", "Laboratory", "Cafeteria", "Auditorium", "Sports Ground", "Parking Area", "Hostel", "Bus", "Other"]
STATUSES = ["Open", "Matched", "Returned", "Closed"]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        item_type TEXT NOT NULL CHECK(item_type IN ('Lost','Found')),
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        location TEXT NOT NULL,
        item_date TEXT NOT NULL,
        contact_name TEXT NOT NULL,
        contact_email TEXT NOT NULL,
        image_url TEXT,
        status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN ('Open','Matched','Returned','Closed')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type);
    CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
    CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
    CREATE INDEX IF NOT EXISTS idx_items_user ON items(user_id);
    """)
    # Safe migration for an older copy of this project database.
    columns = [row[1] for row in db.execute("PRAGMA table_info(items)").fetchall()]
    if "user_id" not in columns:
        db.execute("ALTER TABLE items ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
        db.execute("CREATE INDEX IF NOT EXISTS idx_items_user ON items(user_id)")
    db.commit()
    db.close()


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(**kwargs)
    return wrapped_view


def similarity(a, b):
    a = " ".join((a or "").lower().split())
    b = " ".join((b or "").lower().split())
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def matching_score(lost, found):
    score = 0.0
    if lost["category"].lower() == found["category"].lower():
        score += 0.30
    score += similarity(lost["title"], found["title"]) * 0.30
    score += similarity(lost["description"], found["description"]) * 0.25
    score += similarity(lost["location"], found["location"]) * 0.15
    return round(min(score, 1.0) * 100)


def find_matches(item, limit=5):
    opposite = "Found" if item["item_type"] == "Lost" else "Lost"
    candidates = get_db().execute(
        "SELECT * FROM items WHERE item_type=? AND status IN ('Open','Matched') AND id<>? ORDER BY created_at DESC",
        (opposite, item["id"])
    ).fetchall()
    scored = [(matching_score(item, candidate), candidate) for candidate in candidates]
    scored = [(score, candidate) for score, candidate in scored if score >= 25]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:limit]


@app.context_processor
def inject_globals():
    return {"current_user": session.get("username"), "categories": CATEGORIES, "locations": LOCATIONS}


@app.route("/")
def index():
    db = get_db()
    q = request.args.get("q", "").strip()
    item_type = request.args.get("type", "").strip()
    category = request.args.get("category", "").strip()
    status = request.args.get("status", "Open").strip()
    sql = "SELECT * FROM items WHERE 1=1"
    params = []
    if q:
        sql += " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    if item_type in ("Lost", "Found"):
        sql += " AND item_type=?"
        params.append(item_type)
    if category in CATEGORIES:
        sql += " AND category=?"
        params.append(category)
    if status in STATUSES:
        sql += " AND status=?"
        params.append(status)
    elif status != "All":
        status = "Open"
        sql += " AND status='Open'"
    sql += " ORDER BY created_at DESC"
    items = db.execute(sql, params).fetchall()
    stats = {
        "lost": db.execute("SELECT COUNT(*) FROM items WHERE item_type='Lost'").fetchone()[0],
        "found": db.execute("SELECT COUNT(*) FROM items WHERE item_type='Found'").fetchone()[0],
        "returned": db.execute("SELECT COUNT(*) FROM items WHERE status='Returned'").fetchone()[0],
        "open": db.execute("SELECT COUNT(*) FROM items WHERE status='Open'").fetchone()[0],
    }
    return render_template("index.html", items=items, stats=stats, q=q, selected_type=item_type,
                           selected_category=category, selected_status=status)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(username) < 2:
            flash("Username must contain at least 2 characters.", "danger")
        elif "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            flash("Enter a valid email address.", "danger")
        elif len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
        else:
            try:
                db = get_db()
                db.execute("INSERT INTO users (username,email,password_hash) VALUES (?,?,?)",
                           (username, email, generate_password_hash(password)))
                db.commit()
                flash("Account created successfully. Please sign in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("An account with this email already exists.", "danger")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("You are signed in.", "success")
            destination = request.args.get("next", "")
            if destination.startswith("/") and not destination.startswith("//"):
                return redirect(destination)
            return redirect(url_for("index"))
        flash("Incorrect email or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("index"))


@app.route("/report/<item_type>", methods=["GET", "POST"])
@login_required
def report(item_type):
    if item_type not in ("lost", "found"):
        abort(404)
    title_type = item_type.title()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()
        item_date = request.form.get("item_date", "").strip()
        image_url = request.form.get("image_url", "").strip()
        errors = []
        if len(title) < 2: errors.append("Enter an item name with at least 2 characters.")
        if category not in CATEGORIES: errors.append("Choose a valid category.")
        if len(description) < 5: errors.append("Description must contain at least 5 characters.")
        if location not in LOCATIONS: errors.append("Choose a valid location.")
        try:
            datetime.strptime(item_date, "%Y-%m-%d")
        except ValueError:
            errors.append("Choose a valid date.")
        if image_url and not image_url.startswith(("https://", "http://")):
            errors.append("Image URL must start with http:// or https://.")
        if errors:
            for error in errors: flash(error, "danger")
            return render_template("report.html", item_type=title_type, form=request.form), 400
        user = get_db().execute("SELECT username,email FROM users WHERE id=?", (session["user_id"],)).fetchone()
        db = get_db()
        cursor = db.execute("""INSERT INTO items
            (user_id,item_type,title,category,description,location,item_date,contact_name,contact_email,image_url)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (session["user_id"], title_type, title, category, description, location, item_date,
             user["username"], user["email"], image_url or None))
        db.commit()
        item_id = cursor.lastrowid
        flash(f"{title_type} item report submitted successfully.", "success")
        return redirect(url_for("detail", item_id=item_id))
    return render_template("report.html", item_type=title_type, form={})


@app.route("/item/<int:item_id>")
def detail(item_id):
    item = get_db().execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if item is None:
        abort(404)
    matches = find_matches(item)
    return render_template("detail.html", item=item, matches=matches)


@app.route("/my-reports")
@login_required
def my_reports():
    items = get_db().execute("SELECT * FROM items WHERE user_id=? ORDER BY created_at DESC", (session["user_id"],)).fetchall()
    return render_template("my_reports.html", items=items)


@app.route("/item/<int:item_id>/status", methods=["POST"])
@login_required
def update_status(item_id):
    status = request.form.get("status", "")
    if status not in STATUSES:
        abort(400)
    db = get_db()
    item = db.execute("SELECT id,user_id FROM items WHERE id=?", (item_id,)).fetchone()
    if item is None:
        abort(404)
    if item["user_id"] != session["user_id"]:
        abort(403)
    db.execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
    db.commit()
    flash("Item status updated.", "success")
    return redirect(url_for("detail", item_id=item_id))


@app.route("/item/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    db = get_db()
    item = db.execute("SELECT id,user_id FROM items WHERE id=?", (item_id,)).fetchone()
    if item is None:
        abort(404)
    if item["user_id"] != session["user_id"]:
        abort(403)
    db.execute("DELETE FROM items WHERE id=?", (item_id,))
    db.commit()
    flash("Your report has been deleted.", "success")
    return redirect(url_for("my_reports"))


@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message="You are not allowed to perform this action."), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="The page or item could not be found."), 404


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message="The request could not be processed."), 400


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1")
