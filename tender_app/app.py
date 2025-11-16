from flask import (
    Flask,
    render_template_string,
    request,
    redirect,
    url_for,
    flash,
    session,
)
from supabase import create_client, Client
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from email.message import EmailMessage
import smtplib
import os
import threading
import time

# Optional: if you have the scrapers package
try:
    from .scrapers.run_all import run_all_scrapers
except Exception:  # pragma: no cover
    run_all_scrapers = None

# Optional: Stripe (subscription)
try:
    import stripe
except ImportError:  # pragma: no cover
    stripe = None

# ---------------------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

if stripe and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ---------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = FLASK_SECRET_KEY

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def current_user_email() -> str | None:
    return session.get("user_email")


def login_required():
    return current_user_email() is not None


def admin_logged_in() -> bool:
    return session.get("is_admin") is True


def admin_required():
    return admin_logged_in()


def send_email(to_email: str, subject: str, body: str) -> None:
    """Best-effort email sender; safe if SMTP not configured."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and SMTP_FROM_EMAIL):
        print("[email] SMTP not configured; skipping send.")
        return

    msg = EmailMessage()
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[email] Sent to {to_email}")
    except Exception as e:  # pragma: no cover
        print(f"[email] Error: {e}")


# ---------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------
BASE_HTML = """
<!doctype html>
<html>
<head>
  <title>African Oil & Gas Tenders</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    nav a { margin-right: 12px; }
    .page { margin-top: 20px; }
    table { border-collapse: collapse; width: 100%%; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 14px; }
    th { background: #f0f0f0; }
    .flash-ok { color: green; }
    .flash-error { color: red; }
  </style>
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    {% if user_email %}
      <a href="{{ url_for('my_tenders') }}">My Tenders</a>
      <a href="{{ url_for('subscribe') }}">Subscribe</a>
      <span>Logged in as {{ user_email }}</span>
      <a href="{{ url_for('logout') }}">Logout</a>
    {% else %}
      <a href="{{ url_for('login') }}">Login</a>
      <a href="{{ url_for('register') }}">Register</a>
    {% endif %}
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for cat, msg in messages %}
          <p class="flash-{{ cat }}">{{ msg }}</p>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
  </div>
</body>
</html>
"""

HOME_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>Dashboard</h1>

<h2>Vendors (latest 10)</h2>
<ul>
  {% for v in vendors %}
    <li>{{ v.name }} — {{ v.country }}</li>
  {% endfor %}
</ul>

<h2>Tenders (latest 10)</h2>
<ul>
  {% for t in tenders %}
    <li>
      <strong>{{ t.title }}</strong>
      {% if t.vendor_name %} — <em>{{ t.vendor_name }}</em>{% endif %}
      — {{ t.country }}
      {% if t.closing_date %} — closes {{ t.closing_date }}{% endif %}
    </li>
  {% endfor %}
</ul>
{% endblock %}
"""

VENDORS_PAGE_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>Vendors</h1>

<form method="get">
  Search: <input name="q" value="{{ q }}">
  Country: <input name="country" value="{{ country }}">
  <button type="submit">Filter</button>
</form>

<table>
  <tr>
    <th>Name</th>
    <th>Country</th>
    <th>Category</th>
    <th>Email</th>
    <th>Phone</th>
  </tr>
  {% for v in vendors %}
    <tr>
      <td>{{ v.name }}</td>
      <td>{{ v.country }}</td>
      <td>{{ v.category_primary }}</td>
      <td>{{ v.email }}</td>
      <td>{{ v.phone }}</td>
    </tr>
  {% endfor %}
</table>
{% endblock %}
"""

TENDERS_PAGE_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>Tenders</h1>

<form method="get">
  Search: <input name="q" value="{{ q }}">
  Country: <input name="country" value="{{ country }}">
  <button type="submit">Filter</button>
</form>

<table>
  <tr>
    <th>Title</th>
    <th>Vendor</th>
    <th>Country</th>
    <th>Closing date</th>
    <th>Link</th>
    {% if user_email %}<th>Save</th>{% endif %}
  </tr>
  {% for t in tenders %}
    <tr>
      <td>{{ t.title }}</td>
      <td>{{ t.vendor_name }}</td>
      <td>{{ t.country }}</td>
      <td>{{ t.closing_date or "" }}</td>
      <td>
        {% if t.link %}
          <a href="{{ t.link }}" target="_blank">View</a>
        {% endif %}
      </td>
      {% if user_email %}
      <td>
        <form method="post" action="{{ url_for('save_tender', tender_id=t.id) }}">
          <button type="submit">Save</button>
        </form>
      </td>
      {% endif %}
    </tr>
  {% endfor %}
</table>
{% endblock %}
"""

AUTH_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>{{ title }}</h1>
<form method="post">
  <label>Email: <input type="email" name="email" required></label><br>
  <label>Password: <input type="password" name="password" required></label><br>
  <button type="submit">{{ button }}</button>
</form>
{% endblock %}
"""

MY_TENDERS_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>My Saved Tenders</h1>

<table>
  <tr>
    <th>Title</th>
    <th>Vendor</th>
    <th>Country</th>
    <th>Closing date</th>
    <th>Link</th>
  </tr>
  {% for t in tenders %}
    <tr>
      <td>{{ t.title }}</td>
      <td>{{ t.vendor_name }}</td>
      <td>{{ t.country }}</td>
      <td>{{ t.closing_date or "" }}</td>
      <td>
        {% if t.link %}
          <a href="{{ t.link }}" target="_blank">View</a>
        {% endif %}
      </td>
    </tr>
  {% endfor %}
</table>
{% endblock %}
"""

ADMIN_LOGIN_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>Admin Login</h1>
<form method="post">
  <label>Username: <input name="username"></label><br>
  <label>Password: <input name="password" type="password"></label><br>
  <button type="submit">Login</button>
</form>
{% endblock %}
"""

ADMIN_DASH_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>Admin Dashboard</h1>

<p><a href="{{ url_for('admin_logout') }}">Logout admin</a></p>

<h2>Add Vendor</h2>
<form method="post" action="{{ url_for('admin_add_vendor') }}">
  <label>Name: <input name="name" required></label><br>
  <label>Country: <input name="country" required></label><br>
  <label>Primary category: <input name="category_primary"></label><br>
  <label>Email: <input name="email"></label><br>
  <label>Phone: <input name="phone"></label><br>
  <button type="submit">Save Vendor</button>
</form>

<hr>

<h2>Add Tender</h2>
<form method="post" action="{{ url_for('admin_add_tender') }}">
  <label>Title: <input name="title" required></label><br>
  <label>Country: <input name="country" required></label><br>
  <label>Operator: <input name="operator" required></label><br>

  <label>Vendor:
    <select name="vendor_id" required>
      <option value="">-- Select vendor --</option>
      {% for v in all_vendors %}
        <option value="{{ v.id }}">{{ v.name }} ({{ v.country }})</option>
      {% endfor %}
    </select>
  </label><br>

  <label>Source: <input name="source" value="Manual"></label><br>
  <label>Closing date (YYYY-MM-DD): <input name="closing_date"></label><br>
  <label>Link: <input name="link"></label><br>
  <label>Description:<br>
    <textarea name="description" rows="4" cols="60"></textarea>
  </label><br>
  <button type="submit">Save Tender</button>
</form>

<hr>

<h2>Shortcuts</h2>
<p><a href="{{ url_for('admin_list_users') }}">View all users</a></p>
<p><a href="{{ url_for('admin_list_saved_tenders') }}">View saved tenders</a></p>

{% endblock %}
"""

ADMIN_USERS_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>Registered Users</h1>
<table>
  <tr><th>ID</th><th>Email</th><th>Created</th></tr>
  {% for u in users %}
    <tr><td>{{ u.id }}</td><td>{{ u.email }}</td><td>{{ u.created_at }}</td></tr>
  {% endfor %}
</table>
{% endblock %}
"""

ADMIN_SAVED_TENDERS_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>Saved Tenders</h1>
<table>
  <tr><th>User</th><th>Tender</th><th>Vendor</th><th>Country</th></tr>
  {% for row in rows %}
    <tr>
      <td>{{ row.user_email }}</td>
      <td>{{ row.tender_title }}</td>
      <td>{{ row.vendor_name }}</td>
      <td>{{ row.country }}</td>
    </tr>
  {% endfor %}
</table>
{% endblock %}
"""

SUBSCRIBE_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h1>Subscribe</h1>
{% if not stripe_enabled %}
<p>Stripe is not configured.</p>
{% else %}
<form method="post">
  <p>Subscribe to full tender access.</p>
  <button type="submit">Go to Checkout</button>
</form>
{% endif %}
{% endblock %}
"""

# ---------------------------------------------------------------------
# Context processor to inject base.html
# ---------------------------------------------------------------------


@app.context_processor
def inject_base():
    return {
        "user_email": current_user_email(),
    }


@app.route("/_base_template")
def _base_template():
    # For IDEs; not used in routing
    return render_template_string(BASE_HTML)


app.jinja_env.globals["BASE_HTML"] = BASE_HTML
app.jinja_loader.mapping = {"base.html": BASE_HTML}

# ---------------------------------------------------------------------
# Routes – public
# ---------------------------------------------------------------------


@app.route("/")
def home():
    # Latest 10 vendors
    vres = supabase.table("vendors").select("id, name, country").order(
        "id", desc=True
    ).limit(10).execute()
    vendors = vres.data or []

    # Latest 10 tenders
    tres = supabase.table("tenders").select(
        "id, title, country, closing_date, vendor_id"
    ).order("id", desc=True).limit(10).execute()
    tenders = tres.data or []

    # Map vendor_id -> name
    vmap = {}
    if tenders:
        v_ids = {t["vendor_id"] for t in tenders if t.get("vendor_id")}
        if v_ids:
            v2 = (
                supabase.table("vendors")
                .select("id, name")
                .in_("id", list(v_ids))
                .execute()
            )
            vmap = {v["id"]: v["name"] for v in (v2.data or [])}

    for t in tenders:
        vid = t.get("vendor_id")
        t["vendor_name"] = vmap.get(vid, "")

    return render_template_string(HOME_TEMPLATE, vendors=vendors, tenders=tenders)


@app.route("/vendors")
def vendors_page():
    q = request.args.get("q", "").strip()
    country = request.args.get("country", "").strip()

    query = supabase.table("vendors").select("*")
    if country:
        query = query.eq("country", country)
    if q:
        like = f"%{q}%"
        query = query.ilike("name", like)

    res = query.order("name").limit(200).execute()
    vendors = res.data or []

    return render_template_string(
        VENDORS_PAGE_TEMPLATE,
        vendors=vendors,
        q=q,
        country=country,
    )


@app.route("/tenders")
def tenders_page():
    q = request.args.get("q", "").strip()
    country = request.args.get("country", "").strip()

    query = supabase.table("tenders").select("*")

    if country:
        query = query.eq("country", country)
    if q:
        like = f"%{q}%"
        query = query.ilike("title", like)

    tres = query.order("id", desc=True).limit(200).execute()
    tenders = tres.data or []

    # Attach vendor_name
    vmap = {}
    v_ids = {t["vendor_id"] for t in tenders if t.get("vendor_id")}
    if v_ids:
        vres = (
            supabase.table("vendors")
            .select("id, name")
            .in_("id", list(v_ids))
            .execute()
        )
        vmap = {v["id"]: v["name"] for v in (vres.data or [])}

    for t in tenders:
        vid = t.get("vendor_id")
        t["vendor_name"] = vmap.get(vid, "")

    return render_template_string(
        TENDERS_PAGE_TEMPLATE,
        tenders=tenders,
        q=q,
        country=country,
    )


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not email or not password:
            flash("Email and password required", "error")
            return redirect(url_for("register"))

        pw_hash = generate_password_hash(password)

        try:
            supabase.table("app_users").insert(
                {"email": email, "password_hash": pw_hash}
            ).execute()
        except Exception as e:  # pragma: no cover
            print("[register] error", e)
            flash("Registration failed (maybe email already used).", "error")
            return redirect(url_for("register"))

        flash("Registration successful. Please log in.", "ok")
        return redirect(url_for("login"))

    return render_template_string(
        AUTH_TEMPLATE, title="Register", button="Register"
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        res = supabase.table("app_users").select("*").eq("email", email).limit(
            1
        ).execute()
        user = (res.data or [None])[0]

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials", "error")
            return redirect(url_for("login"))

        session["user_email"] = email
        flash("Logged in", "ok")
        return redirect(url_for("home"))

    return render_template_string(
        AUTH_TEMPLATE, title="Login", button="Login"
    )


@app.route("/logout")
def logout():
    session.pop("user_email", None)
    flash("Logged out", "ok")
    return redirect(url_for("home"))


# ---------------------------------------------------------------------
# Save tenders for user
# ---------------------------------------------------------------------


@app.route("/my-tenders")
def my_tenders():
    if not login_required():
        flash("Please log in", "error")
        return redirect(url_for("login"))

    email = current_user_email()

    sres = (
        supabase.table("user_saved_tenders")
        .select("tender_id")
        .eq("user_email", email)
        .execute()
    )
    saved_rows = sres.data or []
    tender_ids = [r["tender_id"] for r in saved_rows]

    if not tender_ids:
        return render_template_string(MY_TENDERS_TEMPLATE, tenders=[])

    tres = (
        supabase.table("tenders")
        .select("*")
        .in_("id", tender_ids)
        .execute()
    )
    tenders = tres.data or []

    v_ids = {t["vendor_id"] for t in tenders if t.get("vendor_id")}
    vmap = {}
    if v_ids:
        vres = (
            supabase.table("vendors")
            .select("id, name")
            .in_("id", list(v_ids))
            .execute()
        )
        vmap = {v["id"]: v["name"] for v in (vres.data or [])}

    for t in tenders:
        vid = t.get("vendor_id")
        t["vendor_name"] = vmap.get(vid, "")

    return render_template_string(MY_TENDERS_TEMPLATE, tenders=tenders)


@app.route("/save-tender/<int:tender_id>", methods=["POST"])
def save_tender(tender_id: int):
    if not login_required():
        flash("Please log in", "error")
        return redirect(url_for("login"))

    email = current_user_email()

    supabase.table("user_saved_tenders").insert(
        {"user_email": email, "tender_id": tender_id}
    ).execute()
    flash("Tender saved", "ok")
    return redirect(url_for("tenders_page"))


# ---------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Admin login successful", "ok")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials", "error")
        return redirect(url_for("admin_login"))

    return render_template_string(ADMIN_LOGIN_TEMPLATE)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Admin logged out", "ok")
    return redirect(url_for("home"))


@app.route("/admin")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("admin_login"))

    vres = (
        supabase.table("vendors")
        .select("id, name, country")
        .order("name")
        .execute()
    )
    all_vendors = vres.data or []

    return render_template_string(
        ADMIN_DASH_TEMPLATE,
        all_vendors=all_vendors,
    )


@app.route("/admin/add_vendor", methods=["POST"])
def admin_add_vendor():
    if not admin_required():
        return redirect(url_for("admin_login"))

    data = {
        "name": request.form.get("name"),
        "country": request.form.get("country"),
        "category_primary": request.form.get("category_primary"),
        "email": request.form.get("email"),
        "phone": request.form.get("phone"),
        "source": "Manual",
    }

    supabase.table("vendors").insert(data).execute()
    flash("Vendor added", "ok")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/add_tender", methods=["POST"])
def admin_add_tender():
    if not admin_required():
        return redirect(url_for("admin_login"))

    vendor_id_raw = request.form.get("vendor_id") or None
    vendor_id = int(vendor_id_raw) if vendor_id_raw else None

    data = {
        "title": request.form.get("title"),
        "country": request.form.get("country"),
        "operator": request.form.get("operator"),
        "source": request.form.get("source", "Manual"),  # internal only
        "closing_date": request.form.get("closing_date") or None,
        "link": request.form.get("link"),
        "description": request.form.get("description"),
        "vendor_id": vendor_id,
    }

    supabase.table("tenders").insert(data).execute()
    flash("Tender added", "ok")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users")
def admin_list_users():
    if not admin_required():
        return redirect(url_for("admin_login"))

    res = supabase.table("app_users").select("id, email, created_at").order(
        "id"
    ).execute()
    users = res.data or []

    return render_template_string(ADMIN_USERS_TEMPLATE, users=users)


@app.route("/admin/saved-tenders")
def admin_list_saved_tenders():
    if not admin_required():
        return redirect(url_for("admin_login"))

    # Get all saved records
    sres = supabase.table("user_saved_tenders").select("*").execute()
    rows = sres.data or []

    if not rows:
        return render_template_string(
            ADMIN_SAVED_TENDERS_TEMPLATE, rows=[]
        )

    tender_ids = {r["tender_id"] for r in rows}
    tres = (
        supabase.table("tenders")
        .select("id, title, vendor_id, country")
        .in_("id", list(tender_ids))
        .execute()
    )
    tenders = tres.data or []
    tmap = {t["id"]: t for t in tenders}

    vendor_ids = {t["vendor_id"] for t in tenders if t.get("vendor_id")}
    vmap = {}
    if vendor_ids:
        vres = (
            supabase.table("vendors")
            .select("id, name")
            .in_("id", list(vendor_ids))
            .execute()
        )
        vmap = {v["id"]: v["name"] for v in (vres.data or [])}

    enriched = []
    for r in rows:
        t = tmap.get(r["tender_id"], {})
        enriched.append(
            {
                "user_email": r["user_email"],
                "tender_title": t.get("title", ""),
                "vendor_name": vmap.get(t.get("vendor_id"), ""),
                "country": t.get("country", ""),
            }
        )

    return render_template_string(
        ADMIN_SAVED_TENDERS_TEMPLATE, rows=enriched
    )


# ---------------------------------------------------------------------
# Stripe subscription (optional)
# ---------------------------------------------------------------------


@app.route("/subscribe", methods=["GET", "POST"])
def subscribe():
    if not login_required():
        flash("Please log in first", "error")
        return redirect(url_for("login"))

    stripe_enabled = bool(stripe and STRIPE_SECRET_KEY and STRIPE_PRICE_ID)

    if request.method == "POST" and stripe_enabled:
        email = current_user_email()
        try:
            checkout = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
                customer_email=email,
                success_url=url_for("home", _external=True)
                + "?checkout=success",
                cancel_url=url_for("subscribe", _external=True),
            )
            return redirect(checkout.url)
        except Exception as e:  # pragma: no cover
            print("[stripe] error", e)
            flash("Could not start checkout. Please try again later.", "error")

    return render_template_string(
        SUBSCRIBE_TEMPLATE, stripe_enabled=stripe_enabled
    )


# ---------------------------------------------------------------------
# Background scraping loop (optional)
# ---------------------------------------------------------------------


def auto_scrape_loop():
    """Optional background loop to run all scrapers every 30 minutes."""
    if not run_all_scrapers:
        print("[auto-scrape] scrapers not available; skipping.")
        return

    while True:
        try:
            print("[auto-scrape] Running all scrapers...")
            inserted = run_all_scrapers(supabase)
            print(f"[auto-scrape] Inserted {inserted} tender rows.")
        except Exception as e:  # pragma: no cover
            print(f"[auto-scrape] Error: {e}")
        time.sleep(30 * 60)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
if __name__ == "__main__":
    print("Running Flask app on http://127.0.0.1:5000")
    # If you want auto-scrape, uncomment below:
    # t = threading.Thread(target=auto_scrape_loop, daemon=True)
    # t.start()
    app.run(debug=True)
