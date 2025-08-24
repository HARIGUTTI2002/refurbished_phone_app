from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import json, os, csv
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("APP_SECRET_KEY", "dev-secret-change-me")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///phones.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "hari")
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get("ADMIN_PASSWORD", "hari123"))

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

class Phone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(120), nullable=False)
    model = db.Column(db.String(120), nullable=False)
    storage = db.Column(db.String(50), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    condition = db.Column(db.String(20), nullable=False)
    base_price = db.Column(db.Float, nullable=False, default=0.0) 
    stock = db.Column(db.Integer, nullable=False, default=0)
    tags = db.Column(db.String(255), nullable=True)

    price_overrides = db.Column(db.Text, nullable=False, default='{}')  # {"X": 123.0, "Y": 120.0, "Z": 130.0}
    listings = db.Column(db.Text, nullable=False, default='{}')      
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_overrides(self):
        try:
            return json.loads(self.price_overrides or "{}")
        except:
            return {}

    def get_listings(self):
        try:
            return json.loads(self.listings or "{}")
        except:
            return {}

PLATFORMS = ["X", "Y", "Z"]

def compute_listing_price(base_price, platform):
    base_price = float(base_price or 0)
    if platform == "X":   # 10% fee
        return round(base_price / 0.90, 2)
    if platform == "Y":   # 8% fee + $2
        return round((base_price + 2.0) / 0.92, 2)
    if platform == "Z":   # 12% fee
        return round(base_price / 0.88, 2)
    raise ValueError("Unknown platform")

# Condition mapping to each platform
CONDITION_MAP = {
    # internal -> mappings
    "New":    {"X": "New",          "Y": "3 stars (Excellent)", "Z": "New"},
    "Good":   {"X": "Good",         "Y": "2 stars (Good)",      "Z": "Good"},
    "Usable": {"X": "Good",         "Y": "1 star (Usable)",     "Z": "As New"},  # mock choice
    "Scrap":  {"X": "Scrap",        "Y": "1 star (Usable)",     "Z": None},      # Z doesn't accept Scrap (mock rule)
}

# Profitability: avoid listing if listing price exceeds 25% markup over base_price
MAX_MARKUP = 1.25

def is_profitable(base_price, listing_price):
    if base_price <= 0:
        return False
    return listing_price <= round(base_price * MAX_MARKUP, 2)

def validate_phone_fields(data):
    errors = []
    brand = (data.get("brand") or "").strip()
    model = (data.get("model") or "").strip()
    condition = (data.get("condition") or "").strip()
    storage = (data.get("storage") or "").strip()
    color = (data.get("color") or "").strip()
    tags = (data.get("tags") or "").strip()

    try:
        base_price = float(data.get("base_price", 0))
        if base_price < 0:
            errors.append("Base price cannot be negative.")
    except ValueError:
        errors.append("Base price must be a number.")
        base_price = 0

    try:
        stock = int(float(data.get("stock", 0)))  # allow "3.0"
        if stock < 0:
            errors.append("Stock cannot be negative.")
    except ValueError:
        errors.append("Stock must be an integer.")
        stock = 0

    if not brand:
        errors.append("Brand is required.")
    if not model:
        errors.append("Model is required.")
    if condition not in CONDITION_MAP.keys():
        errors.append("Condition must be one of: " + ", ".join(CONDITION_MAP.keys()))

    return errors, dict(brand=brand, model=model, condition=condition,
                        storage=storage, color=color, base_price=base_price,
                        stock=stock, tags=tags)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["logged_in"] = True
            session["user"] = username
            flash("Logged in successfully.", "success")
            return redirect(url_for("index"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    q = (request.args.get("q") or "").strip().lower()
    cond = (request.args.get("condition") or "").strip()
    platform = (request.args.get("platform") or "").strip()

    phones = Phone.query.order_by(Phone.updated_at.desc()).all()
    filtered = []
    for p in phones:
        if q and (q not in p.brand.lower() and q not in p.model.lower()):
            continue
        if cond and p.condition != cond:
            continue
        if platform:
            listings = p.get_listings()
            if listings.get(platform, {}).get("status") != "listed":
                continue
        filtered.append(p)

    return render_template("index.html", phones=filtered, q=q, cond=cond, platform=platform,
                           platforms=PLATFORMS, CONDITION_MAP=CONDITION_MAP, compute_listing_price=compute_listing_price)

@app.route("/phone/new", methods=["GET", "POST"])
@login_required
def add_phone():
    if request.method == "POST":
        errors, cleaned = validate_phone_fields(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("add_edit_phone.html", phone=None, conditions=list(CONDITION_MAP.keys()))
        phone = Phone(**cleaned)
        db.session.add(phone)
        db.session.commit()
        flash("Phone added.", "success")
        return redirect(url_for("index"))
    return render_template("add_edit_phone.html", phone=None, conditions=list(CONDITION_MAP.keys()))

@app.route("/phone/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def edit_phone(pid):
    phone = Phone.query.get_or_404(pid)
    if request.method == "POST":
        errors, cleaned = validate_phone_fields(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("add_edit_phone.html", phone=phone, conditions=list(CONDITION_MAP.keys()))
        for k, v in cleaned.items():
            setattr(phone, k, v)
        db.session.commit()
        flash("Phone updated.", "success")
        return redirect(url_for("index"))
    return render_template("add_edit_phone.html", phone=phone, conditions=list(CONDITION_MAP.keys()))

@app.route("/phone/<int:pid>/delete", methods=["POST"])
@login_required
def delete_phone(pid):
    phone = Phone.query.get_or_404(pid)
    db.session.delete(phone)
    db.session.commit()
    flash("Phone deleted.", "info")
    return redirect(url_for("index"))

@app.route("/bulk-upload", methods=["GET", "POST"])
@login_required
def bulk_upload():
    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            flash("Please choose a CSV file.", "warning")
            return render_template("bulk_upload.html")
        filename = secure_filename(file.filename or "upload.csv")
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)

        added = 0
        errors_total = 0
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            expected = {"brand","model","storage","color","condition","base_price","stock","tags"}
            if set(map(str.lower, reader.fieldnames or [])) != expected:
                flash("CSV headers must be exactly: " + ", ".join(sorted(expected)), "danger")
                return render_template("bulk_upload.html")
            for row in reader:
                normalized = {k.lower(): v for k, v in row.items()}
                errors, cleaned = validate_phone_fields(normalized)
                if errors:
                    errors_total += 1
                    continue
                phone = Phone(**cleaned)
                db.session.add(phone)
                added += 1
            db.session.commit()
        flash(f"Bulk upload complete. Added {added} phone(s). Skipped {errors_total} invalid row(s).", "info")
        return redirect(url_for("index"))
    return render_template("bulk_upload.html")

@app.route("/price/<int:pid>", methods=["GET", "POST"])
@login_required
def price_override(pid):
    phone = Phone.query.get_or_404(pid)
    overrides = phone.get_overrides()
    if request.method == "POST":
        for p in PLATFORMS:
            val = request.form.get(f"override_{p}")
            if val:
                try:
                    price = float(val)
                    if price <= 0:
                        flash(f"Override for {p} must be positive.", "danger")
                        return render_template("price_override.html", phone=phone, overrides=overrides, platforms=PLATFORMS)
                    overrides[p] = round(price, 2)
                except ValueError:
                    flash(f"Invalid price for {p}.", "danger")
                    return render_template("price_override.html", phone=phone, overrides=overrides, platforms=PLATFORMS)
            else:
                if p in overrides:
                    overrides.pop(p)
        phone.price_overrides = json.dumps(overrides)
        db.session.commit()
        flash("Overrides saved.", "success")
        return redirect(url_for("index"))
    return render_template("price_override.html", phone=phone, overrides=overrides, platforms=PLATFORMS)

@app.route("/list/<int:pid>/<platform>", methods=["POST"])
@login_required
def list_phone(pid, platform):
    phone = Phone.query.get_or_404(pid)
    platform = platform.upper()
    if platform not in PLATFORMS:
        flash("Unknown platform.", "danger")
        return redirect(url_for("index"))

    listings = phone.get_listings()
    overrides = phone.get_overrides()

    if phone.stock <= 0 or ("out of stock" in (phone.tags or "").lower()):
        listings[platform] = {"status": "failed", "reason": "Out of stock."}
        phone.listings = json.dumps(listings)
        db.session.commit()
        flash(f"Listing failed on {platform}: Out of stock.", "danger")
        return redirect(url_for("index"))
    if (phone.tags or "").lower().find("discontinued") >= 0:
        listings[platform] = {"status": "failed", "reason": "Product discontinued."}
        phone.listings = json.dumps(listings)
        db.session.commit()
        flash(f"Listing failed on {platform}: Discontinued.", "danger")
        return redirect(url_for("index"))

    mapped_condition = CONDITION_MAP.get(phone.condition, {}).get(platform)
    if not mapped_condition:
        listings[platform] = {"status": "failed", "reason": f"Condition '{phone.condition}' unsupported on {platform}."}
        phone.listings = json.dumps(listings)
        db.session.commit()
        flash(f"Listing failed on {platform}: Unsupported condition.", "danger")
        return redirect(url_for("index"))

    listing_price = overrides.get(platform)
    if not listing_price:
        listing_price = compute_listing_price(phone.base_price, platform)

    if not is_profitable(phone.base_price, listing_price):
        listings[platform] = {"status": "failed", "reason": "Unprofitable due to high fees/markup."}
        phone.listings = json.dumps(listings)
        db.session.commit()
        flash(f"Listing failed on {platform}: Unprofitable.", "warning")
        return redirect(url_for("index"))

    listings[platform] = {"status": "listed", "price": listing_price, "condition_mapped": mapped_condition}
    phone.listings = json.dumps(listings)
    db.session.commit()
    flash(f"Listed on {platform} at ${listing_price} ({mapped_condition}).", "success")
    return redirect(url_for("index"))

@app.route("/auto-update-prices/<int:pid>", methods=["POST"])
@login_required
def auto_update_prices(pid):
    phone = Phone.query.get_or_404(pid)
    overrides = phone.get_overrides()
    flash("Auto prices are shown on the dashboard. Overrides remain unchanged.", "info")
    return redirect(url_for("index"))

@app.route("/export/csv")
@login_required
def export_csv():
    fn = os.path.join(app.config['UPLOAD_FOLDER'], f"inventory_export_{int(datetime.utcnow().timestamp())}.csv")
    with open(fn, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id","brand","model","storage","color","condition","base_price","stock","tags","overrides_json","listings_json"])
        for p in Phone.query.all():
            writer.writerow([p.id, p.brand, p.model, p.storage, p.color, p.condition, p.base_price, p.stock, p.tags, p.price_overrides, p.listings])
    return send_file(fn, as_attachment=True)

@app.cli.command("init-db")
def init_db():
    db.create_all()
    if not Phone.query.first():
        sample = Phone(
            brand="Apple", model="iPhone 12", storage="128GB", color="Black",
            condition="Good", base_price=400.0, stock=5, tags="refurbished"
        )
        db.session.add(sample)
        db.session.commit()
        print("Database initialized with a sample phone.")
    else:
        print("Database already initialized.")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
