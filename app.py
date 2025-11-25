import os
import sqlite3
import hashlib
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask import send_from_directory

app = Flask(__name__)
app.secret_key = "super_secret_ims_key"
app.permanent_session_lifetime = timedelta(days=30)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
print("USING DATABASE:", os.path.abspath("database.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'staff',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT,
            price REAL DEFAULT 0.0,
            qty INTEGER DEFAULT 0,
            reorder_level INTEGER DEFAULT 5,
            description TEXT,
            supplier_id INTEGER,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(supplier_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            change INTEGER NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(item_id) REFERENCES items(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            type TEXT,
            quantity INTEGER,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(item_id) REFERENCES items(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in cur.fetchall()}

    if "role" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'staff'")

    if "created_at" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        cur.execute("UPDATE users SET created_at = COALESCE(created_at, datetime('now'))")


    cur.execute("PRAGMA table_info(items)")
    cols = {row[1] for row in cur.fetchall()}
    if "supplier_id" not in cols:
        cur.execute("ALTER TABLE items ADD COLUMN supplier_id INTEGER")
    if "price" not in cols:
        cur.execute("ALTER TABLE items ADD COLUMN price REAL DEFAULT 0.0")
    if "reorder_level" not in cols:
        cur.execute("ALTER TABLE items ADD COLUMN reorder_level INTEGER DEFAULT 5")
    if "description" not in cols:
        cur.execute("ALTER TABLE items ADD COLUMN description TEXT")

    cur.execute("PRAGMA table_info(users)")
    ucols = {row[1] for row in cur.fetchall()}
    if "role" not in ucols:
        cur.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'staff'")

    cur.execute("SELECT id, password_hash, role FROM users WHERE username=?", ("admin",))
    row = cur.fetchone()
    if not row:
        h = generate_password_hash("admin123", method="pbkdf2:sha256", salt_length=8)
        cur.execute(
            "INSERT INTO users(username, password_hash, role) VALUES(?, ?, ?)",
            ("admin", h, "admin"),
        )
    else:
        try:
            ok = check_password_hash(row["password_hash"], "admin123")
        except Exception:
            ok = False
        if not ok:
            h = generate_password_hash("admin123", method="pbkdf2:sha256", salt_length=8)
            cur.execute("UPDATE users SET password_hash=? WHERE id=?", (h, row["id"]))
        cur.execute("UPDATE users SET role='admin' WHERE username='admin'")
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper

def log_action(user_id, action):
    db = get_db()
    db.execute("INSERT INTO activity_log (user_id, action) VALUES (?, ?)", (user_id, action))
    db.commit()

@app.before_request
def ensure_db():
    if not os.path.exists(DB_PATH):
        open(DB_PATH, "a").close()
        init_db()

@app.before_request
def session_timeout():
    if "user_id" in session:
        now = datetime.utcnow()
        last = session.get("last_active", now)
        session["last_active"] = now.isoformat()

        # 30-minute inactivity logout
        max_idle = timedelta(minutes=30)

        if isinstance(last, str):
            last = datetime.fromisoformat(last)

        if now - last > max_idle:
            session.clear()
            return redirect(url_for("login"))


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash, role FROM users WHERE username=?", (username,))
        user = cur.fetchone()
        conn.close()
        valid = False
        if user:
            try:
                valid = check_password_hash(user["password_hash"], password)
            except Exception:
                valid = False
            if not valid:
                valid = (user["password_hash"] == hashlib.sha256(password.encode()).hexdigest())
        if valid:
            session.clear()
            remember = request.form.get("remember")
            session.permanent = True if remember else False
            session["user_id"] = user["id"]
            session["username"] = username
            session["role"] = user["role"]
            session["last_active"] = datetime.utcnow().isoformat()
            session["remember"] = True if remember else False
            try:
                log_action(user["id"], "Logged in")
            except Exception:
                pass
            return redirect(url_for("dashboard"))
        error = "Invalid username or password"

    return render_template("login.html", error=error)



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    total_items = db.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
    total_qty = db.execute("SELECT SUM(qty) AS s FROM items").fetchone()["s"] or 0
    total_moves = db.execute("SELECT COUNT(*) AS c FROM stock_transactions").fetchone()["c"]
    low_stock = db.execute(
        "SELECT name, qty FROM items WHERE qty <= reorder_level"
    ).fetchall()
    extra_stats = None
    if session.get('role') == 'admin':
        extra_stats = db.execute("SELECT COUNT(*) AS users_count FROM users").fetchone()["users_count"]
    return render_template('dashboard.html', total_items=total_items, total_qty=total_qty, total_moves=total_moves, low_stock=low_stock, extra_stats=extra_stats)

@app.route("/items", methods=["GET"]) 
@login_required
def items():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, sku, price, qty FROM items ORDER BY id DESC")
    items = cur.fetchall()
    conn.close()
    return render_template("items.html", items=items)

@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"]) 
@admin_required
def edit_item(item_id):
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        sku = request.form.get("sku", "").strip()
        price = request.form.get("price", "0").strip()
        qty = request.form.get("qty", "0").strip()
        reorder = request.form.get("reorder_level", "5").strip()
        try:
            price_val = float(price)
            qty_val = int(qty)
            reorder_val = int(reorder)
        except Exception:
            return redirect(url_for("items"))
        db.execute(
            "UPDATE items SET name=?, sku=?, price=?, qty=?, reorder_level=? WHERE id=?",
            (name, sku, price_val, qty_val, reorder_val, item_id)
        )
        db.commit()
        log_action(session["user_id"], f"Updated item {item_id}")
        return redirect(url_for("items"))
    item = db.execute(
        "SELECT id, name, sku, price, qty, reorder_level FROM items WHERE id=?",
        (item_id,)
    ).fetchone()
    return render_template("edit_item.html", item=item)

@app.route("/items/create", methods=["POST"]) 
@login_required
def items_create():
    name = request.form.get("name", "").strip()
    sku = request.form.get("sku", "").strip()
    price = request.form.get("price", "0").strip()
    qty = request.form.get("qty", "0").strip()
    supplier_id = request.form.get("supplier_id")
    try:
        price_val = float(price) if price else 0.0
        qty_val = int(qty) if qty else 0
    except Exception:
        return redirect(url_for("items"))
    conn = get_db()
    cur = conn.cursor()
    if supplier_id:
        try:
            supplier_id_val = int(supplier_id)
        except Exception:
            supplier_id_val = None
    else:
        supplier_id_val = None
    cur.execute(
        "INSERT INTO items(name, sku, price, qty, supplier_id) VALUES(?, ?, ?, ?, ?)",
        (name, sku, price_val, qty_val, supplier_id_val),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("items"))

 

@app.route("/items/<int:item_id>/delete", methods=["POST"]) 
@admin_required
def items_delete(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    log_action(session["user_id"], f"Deleted item {item_id}")
    return redirect(url_for("items"))

@app.route("/stock", methods=["GET", "POST"]) 
@login_required
def stock():
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        item_id = request.form.get("item_id")
        change = request.form.get("change")
        note = request.form.get("note", "").strip()
        try:
            item_id_val = int(item_id)
            change_val = int(change)
        except Exception:
            item_id_val = None
            change_val = None
        if item_id_val and change_val:
            cur.execute("SELECT qty FROM items WHERE id=?", (item_id_val,))
            row = cur.fetchone()
            if row:
                new_qty = row["qty"] + change_val
                if new_qty < 0:
                    new_qty = 0
                cur.execute("UPDATE items SET qty=? WHERE id=?", (new_qty, item_id_val))
                cur.execute(
                    "INSERT INTO movements(item_id, change, note, created_at) VALUES(?, ?, ?, ?)",
                    (item_id_val, change_val, note, datetime.utcnow().isoformat()),
                )
                cur.execute(
                    "INSERT INTO stock_transactions(item_id, type, quantity) VALUES(?, ?, ?)",
                    (item_id_val, "IN" if change_val >= 0 else "OUT", abs(change_val)),
                )
                conn.commit()
    cur.execute("SELECT id, name, qty FROM items ORDER BY name ASC")
    items = cur.fetchall()
    cur.execute(
        "SELECT m.id, i.name AS item_name, m.change, m.note, m.created_at FROM movements m JOIN items i ON i.id = m.item_id ORDER BY m.id DESC LIMIT 50"
    )
    movements = cur.fetchall()
    conn.close()
    return render_template("stock.html", items=items, movements=movements)

@app.route('/suppliers')
def suppliers_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('suppliers.html')

@app.route('/api/suppliers', methods=['GET', 'POST'])
def api_suppliers():
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'GET':
        cur.execute('SELECT * FROM suppliers')
        rows = cur.fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    else:
        data = request.get_json(silent=True) or {}
        name = data.get('name', '').strip()
        contact = data.get('contact', '').strip()
        if not name:
            conn.close()
            return jsonify({"error":"name required"}), 400
        cur.execute('INSERT INTO suppliers (name, contact) VALUES (?, ?)', (name, contact))
        conn.commit()
        conn.close()
        return jsonify({"status":"ok"})

@app.route('/api/suppliers/<int:sid>', methods=['DELETE'])
def api_supplier_delete(sid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM suppliers WHERE supplier_id=?', (sid,))
    conn.commit()
    conn.close()
    return jsonify({"status":"deleted"})

@app.route('/api/items', methods=['GET'])
def api_get_items_full():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT i.id, i.name, i.description, i.qty AS quantity,
               i.reorder_level, i.price, i.supplier_id,
               s.name AS supplier_name, s.contact AS supplier_contact
        FROM items i LEFT JOIN suppliers s ON i.supplier_id = s.supplier_id
        ORDER BY i.id DESC
    ''')
    rows = cur.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/items', methods=['POST'])
def api_add_item():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    quantity = data.get('quantity')
    reorder_level = data.get('reorder_level')
    price = data.get('price')
    supplier_id = data.get('supplier_id')
    if not name:
        return jsonify({"error": "name required"}), 400
    try:
        qty_val = int(quantity or 0)
        reorder_val = int(reorder_level or 5)
        price_val = float(price or 0.0)
        supplier_val = int(supplier_id) if supplier_id is not None else None
    except Exception:
        return jsonify({"error": "invalid payload"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO items(name, description, qty, reorder_level, price, supplier_id) VALUES(?, ?, ?, ?, ?, ?)",
        (name, description, qty_val, reorder_val, price_val, supplier_val)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/items/<int:item_id>', methods=['DELETE'])
@admin_required
def api_delete_item(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM items WHERE id=?', (item_id,))
    conn.commit()
    conn.close()
    log_action(session["user_id"], f"Deleted item {item_id}")
    return jsonify({"status": "deleted"})

@app.route('/export_report')
def export_report():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT i.name,
               COALESCE(SUM(CASE WHEN st.type='IN' THEN st.quantity END),0) AS total_in,
               COALESCE(SUM(CASE WHEN st.type='OUT' THEN st.quantity END),0) AS total_out
        FROM items i
        LEFT JOIN stock_transactions st ON i.id = st.item_id
        GROUP BY i.name
        ORDER BY i.name
    ''')
    rows = cur.fetchall()
    conn.close()
    out_dir = os.path.join(app.root_path, 'static', 'reports')
    os.makedirs(out_dir, exist_ok=True)
    file_path = os.path.join(out_dir, 'cedwahn_stock_report.pdf')
    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4
    margin = 40
    y = height - margin
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width/2, y, "Cedwahn IMS - Stock Movement Report")
    y -= 30
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Item")
    c.drawString(margin+250, y, "Total IN")
    c.drawString(margin+340, y, "Total OUT")
    y -= 18
    c.setFont("Helvetica", 10)
    for row in rows:
        if y < 80:
            c.showPage()
            y = height - margin
            c.setFont("Helvetica", 10)
        name = (row['name'] or '')[:40]
        c.drawString(margin, y, name)
        c.drawRightString(margin+320, y, str(int(row['total_in'] or 0)))
        c.drawRightString(margin+420, y, str(int(row['total_out'] or 0)))
        y -= 16
    c.save()
    return jsonify({"status":"ok","path": url_for('static', filename='reports/cedwahn_stock_report.pdf')})

@app.route("/reports") 
@login_required
def reports():
    item_id = request.args.get("item_id")
    start = request.args.get("start")
    end = request.args.get("end")
    conn = get_db()
    cur = conn.cursor()
    base = "SELECT m.id, i.name AS item_name, m.change, m.note, m.created_at FROM movements m JOIN items i ON i.id = m.item_id"
    conditions = []
    params = []
    if item_id:
        try:
            item_id_val = int(item_id)
            conditions.append("i.id = ?")
            params.append(item_id_val)
        except Exception:
            pass
    if start:
        conditions.append("m.created_at >= ?")
        params.append(start)
    if end:
        conditions.append("m.created_at <= ?")
        params.append(end)
    if conditions:
        base += " WHERE " + " AND ".join(conditions)
    base += " ORDER BY m.created_at DESC"
    cur.execute(base, tuple(params))
    movements = cur.fetchall()
    cur.execute("SELECT id, name FROM items ORDER BY name ASC")
    items = cur.fetchall()
    conn.close()
    return render_template("reports.html", items=items, movements=movements)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user_id = session['user_id']

    # Fetch user info
    user = db.execute("SELECT id, username FROM users WHERE id=?", (user_id,)).fetchone()


    success = None
    error = None

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm = request.form.get('confirm_password')

        if new_password or confirm:
            if new_password != confirm:
                error = "Passwords do not match."
            else:
                hashed = generate_password_hash(new_password)
                db.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed, user_id))
                db.commit()
                success = "Password updated successfully."

    return render_template('settings.html', user=user, success=success, error=error)


@app.route('/reset_db')
@admin_required
def reset_db():
    db = get_db()
    db.execute("DELETE FROM items")
    db.execute("DELETE FROM suppliers")
    db.execute("DELETE FROM stock_transactions")
    db.execute("DELETE FROM sqlite_sequence WHERE name IN('items','suppliers','stock_transactions')")
    db.commit()
    log_action(session["user_id"], "Reset database")

    return redirect(url_for('settings'))

@app.route('/users')
@admin_required
def users_page():
    db = get_db()
    users = db.execute("SELECT id, username, role, created_at FROM users").fetchall()
    return render_template("users.html", users=users)

@app.route('/users/create', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get("username")
    password = request.form.get("password")
    role = request.form.get("role", "staff")
    if not username or not password:
        return redirect(url_for("users_page"))
    hashed = generate_password_hash(password)
    db = get_db()
    db.execute("INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)", (username, hashed, role))
    db.commit()
    log_action(session["user_id"], f"Created user {username} ({role})")
    return redirect(url_for("users_page"))

@app.route('/users/<int:uid>/delete', methods=['POST'])
@admin_required
def delete_user(uid):
    if uid == session["user_id"]:
        return redirect(url_for("users_page"))
    db = get_db()
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    log_action(session["user_id"], f"Deleted user {uid}")
    return redirect(url_for("users_page"))

@app.route('/logs')
@admin_required
def logs_page():
    db = get_db()
    logs = db.execute(
        """
        SELECT a.action, a.timestamp, u.username
        FROM activity_log a
        JOIN users u ON u.id = a.user_id
        ORDER BY a.id DESC
        """
    ).fetchall()
    return render_template("logs.html", logs=logs)

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = "staff"
        if not username or not password:
            error = "All fields are required."
        else:
            db = get_db()
            existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if existing:
                error = "Username already exists."
            else:
                hashed = generate_password_hash(password)
                db.execute("INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)", (username, hashed, role))
                db.commit()
                return redirect(url_for("login"))
    return render_template("register.html", error=error)

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
