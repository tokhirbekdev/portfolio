import os
import sqlite3
import uuid
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, abort,
)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
DB_PATH = os.path.join(BASE_DIR, "portfolio.db")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "o'zgartiring-bu-kalitni")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB gacha rasm

# Admin paroli. Albatta o'zgartiring: ADMIN_PASSWORD muhit o'zgaruvchisi yoki pastdagi qiymat.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

DEFAULTS = {
    "name": "Tokhirbek Oripov",
    "title": "Python Developer & Computer Systems Master's Student",
    "tagline": "I build practical applications with Python.",
    "about": (
        "I'm a Computer Systems Master's student who enjoys building "
        "practical applications with Python. I like working with databases, "
        "backend development, and creating software that can solve real-world problems."
    ),
    "skills": (
        "Python, Flask, SQLite3, Tkinter, Matplotlib, "
        "HTML/CSS, Git, REST APIs"
    ),
    "email": "your-email@example.com",
    "github": "https://github.com/tokhirbekdev",
    "linkedin": "https://www.linkedin.com/in/your-username",
    "photo": "./static/uploads/39ffb93621344adfba44285e88aaf169.png",
}


# ---------- Ma'lumotlar bazasi ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            tech TEXT,
            link TEXT,
            image TEXT
        );
        CREATE TABLE IF NOT EXISTS gallery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image TEXT NOT NULL,
            caption TEXT
        );
        """
    )
    for k, v in DEFAULTS.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    if not db.execute("SELECT 1 FROM settings WHERE key = 'seeded'").fetchone():
        db.execute(
            "INSERT INTO projects (title, description, tech, link, image) VALUES (?,?,?,?,?)",
            (
                "Delivery Management System",
                "Yetkazib berish jarayonlarini boshqarish uchun desktop dastur: "
                "ma'lumotlar bazasi va hisobot grafiklari bilan.",
                "Python, Tkinter, SQLite3, Matplotlib",
                "https://github.com/your-username/delivery-management-system",
                "",
            ),
        )
        db.execute("INSERT INTO settings (key, value) VALUES ('seeded', '1')")
    db.commit()
    db.close()


def get_settings():
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    data = dict(DEFAULTS)
    data.update({r["key"]: r["value"] for r in rows})
    return data


# ---------- Rasm yuklash yordamchilari ----------
def save_image(file_storage):
    """Rasmni saqlaydi va fayl nomini qaytaradi (yoki None)."""
    if not file_storage or not file_storage.filename:
        return None
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        flash("Faqat png, jpg, jpeg, gif yoki webp rasmlar mumkin.", "error")
        return None
    name = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(UPLOAD_DIR, name))
    return name


def delete_image(name):
    if not name:
        return
    path = os.path.join(UPLOAD_DIR, os.path.basename(name))
    if os.path.isfile(path):
        os.remove(path)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.template_filter("split_csv")
def split_csv(value):
    return [x.strip() for x in (value or "").split(",") if x.strip()]


@app.template_filter("initials")
def initials(name):
    parts = (name or "").split()[:2]
    return "".join(p[0] for p in parts).upper() or "?"


# ---------- Sahifalar ----------
@app.route("/")
def home():
    db = get_db()
    return render_template(
        "index.html",
        s=get_settings(),
        projects=db.execute("SELECT * FROM projects ORDER BY id DESC").fetchall(),
        gallery=db.execute("SELECT * FROM gallery ORDER BY id DESC").fetchall(),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Parol noto'g'ri.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
@login_required
def admin():
    db = get_db()
    return render_template(
        "admin.html",
        s=get_settings(),
        projects=db.execute("SELECT * FROM projects ORDER BY id DESC").fetchall(),
        gallery=db.execute("SELECT * FROM gallery ORDER BY id DESC").fetchall(),
    )


@app.route("/admin/profile", methods=["POST"])
@login_required
def update_profile():
    db = get_db()
    current = get_settings()
    for key in ("name", "title", "tagline", "about", "skills", "email", "github", "linkedin"):
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, request.form.get(key, "").strip()),
        )
    if request.form.get("remove_photo"):
        delete_image(current["photo"])
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('photo', '')")
    new_photo = save_image(request.files.get("photo"))
    if new_photo:
        delete_image(current["photo"])
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('photo', ?)", (new_photo,))
    db.commit()
    flash("Profil saqlandi.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/project/add", methods=["POST"])
@login_required
def add_project():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Loyiha nomi kerak.", "error")
        return redirect(url_for("admin"))
    image = save_image(request.files.get("image")) or ""
    db = get_db()
    db.execute(
        "INSERT INTO projects (title, description, tech, link, image) VALUES (?,?,?,?,?)",
        (
            title,
            request.form.get("description", "").strip(),
            request.form.get("tech", "").strip(),
            request.form.get("link", "").strip(),
            image,
        ),
    )
    db.commit()
    flash("Loyiha qo'shildi.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/project/<int:pid>/delete", methods=["POST"])
@login_required
def delete_project(pid):
    db = get_db()
    row = db.execute("SELECT image FROM projects WHERE id = ?", (pid,)).fetchone()
    if row is None:
        abort(404)
    delete_image(row["image"])
    db.execute("DELETE FROM projects WHERE id = ?", (pid,))
    db.commit()
    flash("Loyiha o'chirildi.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/gallery/add", methods=["POST"])
@login_required
def add_gallery():
    caption = request.form.get("caption", "").strip()
    db = get_db()
    added = 0
    for f in request.files.getlist("images"):
        name = save_image(f)
        if name:
            db.execute("INSERT INTO gallery (image, caption) VALUES (?, ?)", (name, caption))
            added += 1
    db.commit()
    if added:
        flash(f"{added} ta rasm qo'shildi.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/gallery/<int:gid>/delete", methods=["POST"])
@login_required
def delete_gallery(gid):
    db = get_db()
    row = db.execute("SELECT image FROM gallery WHERE id = ?", (gid,)).fetchone()
    if row is None:
        abort(404)
    delete_image(row["image"])
    db.execute("DELETE FROM gallery WHERE id = ?", (gid,))
    db.commit()
    flash("Rasm o'chirildi.", "ok")
    return redirect(url_for("admin"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
