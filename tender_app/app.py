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

# Optional: background scrapers
try:
    from .scrapers.run_all import run_all_scrapers
except Exception:
    run_all_scrapers = None

# Optional: Stripe (subscription)
try:
    import stripe
except ImportError:
    stripe = None

# ---------------------------------------------------------------------
# Environment & Supabase
# ---------------------------------------------------------------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in .env / secrets.env")

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

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = FLASK_SECRET_KEY

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def current_user_email() -> str | None:
    return session.get("user_email")


def login_required() -> bool:
    return current_user_email() is not None


def admin_logged_in() -> bool:
    return session.get("is_admin") is True


def admin_required() -> bool:
    return admin_logged_in()


def send_email(to_email: str, subject: str, body: str) -> None:
    """Best-effort email sender; safe if SMTP is not configured."""
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
    except Exception as e:
        print(f"[email] Error sending mail: {e}")


# ---------------------------------------------------------------------
# Templates (child pages – all extend templates/base.html)
# ---------------------------------------------------------------------

HOME_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section">
  <div class="tv-section-header">
    <div>
      <h1 class="tv-title">Discover Public Tender Opportunities</h1>
      <p class="tv-subtitle">
        Browse the latest oil &amp; gas tenders across Africa and save the ones that matter to you.
      </p>
    </div>
  </div>

  <div class="tv-grid tv-grid-4">
    <div class="tv-stat-card">
      <p class="tv-stat-label">Active Tenders</p>
      <p class="tv-stat-value">{{ tenders|length }}</p>
    </div>
    <div class="tv-stat-card">
      <p class="tv-stat-label">Vendors</p>
      <p class="tv-stat-value">{{ vendors|length }}</p>
    </div>
    <div class="tv-stat-card">
      <p class="tv-stat-label">Saved Tenders</p>
      <p class="tv-stat-value">–</p>
    </div>
    <div class="tv-stat-card">
      <p class="tv-stat-label">Your Status</p>
      <p class="tv-stat-value">
        {% if user_email %}Logged in{% else %}Guest{% endif %}
      </p>
    </div>
  </div>

  <div class="tv-split">
    <div class="tv-split-left">
      <h2 class="tv-section-title">Latest Tenders</h2>
      {% if tenders %}
        <div class="tenders-list">
          {% for t in tenders %}
            <article class="tender-card">
              <header class="tender-card-header">
                <div>
                  <h3>{{ t.title }}</h3>
                  <p class="tender-meta">
                    {{ t.country or "—" }}
                    {% if t.vendor_name %}&middot; {{ t.vendor_name }}{% endif %}
                    {% if t.closing_date %}&middot; Closes {{ t.closing_date }}{% endif %}
                  </p>
                </div>
                {% if t.link %}
                  <a href="{{ t.link }}" target="_blank" class="btn-sm-outline">View</a>
                {% endif %}
              </header>
              {% if t.description %}
                <p class="tender-desc">{{ t.description[:220] }}{% if t.description|length > 220 %}…{% endif %}</p>
              {% endif %}
            </article>
          {% endfor %}
        </div>
      {% else %}
        <p class="muted">No tenders available yet.</p>
      {% endif %}
      <a href="{{ url_for('tenders_page') }}" class="btn-link">Browse all tenders →</a>
    </div>

    <aside class="tv-split-right">
      <h2 class="tv-section-title">Latest Vendors</h2>
      <ul class="tv-list">
        {% for v in vendors %}
          <li>
            <div class="tv-list-title">{{ v.name }}</div>
            <div class="tv-list-meta">{{ v.country or "—" }}</div>
          </li>
        {% else %}
          <li class="muted">No vendors loaded yet.</li>
        {% endfor %}
      </ul>
      <a href="{{ url_for('vendors_page') }}" class="btn-link">View all vendors →</a>
    </aside>
  </div>
</section>
{% endblock %}
"""

VENDORS_PAGE_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section">
  <div class="tv-section-header">
    <div>
      <h1 class="tv-title">Vendors</h1>
      <p class="tv-subtitle">Browse registered suppliers and service companies.</p>
    </div>
    <form method="get" class="tv-form-inline">
      <input name="q" value="{{ q }}" placeholder="Search vendors…" class="tv-input">
      <input name="country" value="{{ country }}" placeholder="Country" class="tv-input-sm">
      <button type="submit" class="btn-primary">Filter</button>
    </form>
  </div>

  <table class="tv-table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Country</th>
        <th>Category</th>
        <th>Email</th>
        <th>Phone</th>
      </tr>
    </thead>
    <tbody>
      {% for v in vendors %}
        <tr>
          <td>{{ v.name }}</td>
          <td>{{ v.country }}</td>
          <td>{{ v.category_primary }}</td>
          <td>{{ v.email }}</td>
          <td>{{ v.phone }}</td>
        </tr>
      {% else %}
        <tr><td colspan="5" class="muted">No vendors found.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
"""

TENDERS_PAGE_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section">
  <div class="tv-section-header">
    <div>
      <h1 class="tv-title">Browse Tenders</h1>
      <p class="tv-subtitle">Filter by country or keywords and save interesting opportunities.</p>
    </div>
    <form method="get" class="tv-form-inline">
      <input name="q" value="{{ q }}" placeholder="Search tenders…" class="tv-input">
      <input name="country" value="{{ country }}" placeholder="Country" class="tv-input-sm">
      <button type="submit" class="btn-primary">Filter</button>
    </form>
  </div>

  <table class="tv-table">
    <thead>
      <tr>
        <th>Title</th>
        <th>Vendor</th>
        <th>Country</th>
        <th>Closing date</th>
        <th>Link</th>
        {% if user_email %}<th>Save</th>{% endif %}
      </tr>
    </thead>
    <tbody>
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
              <button type="submit" class="btn-sm-outline">Save</button>
            </form>
          </td>
          {% endif %}
        </tr>
      {% else %}
        <tr><td colspan="6" class="muted">No tenders found.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
"""

AUTH_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section tv-auth">
  <div class="tv-auth-card">
    <h1 class="tv-title">{{ title }}</h1>
    <form method="post" class="tv-form-vertical">
      <label>Email
        <input type="email" name="email" required class="tv-input">
      </label>
      <label>Password
        <input type="password" name="password" required class="tv-input">
      </label>
      <button type="submit" class="btn-primary">{{ button }}</button>
    </form>
  </div>
</section>
{% endblock %}
"""

MY_TENDERS_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section">
  <div class="tv-section-header">
    <div>
      <h1 class="tv-title">My Saved Tenders</h1>
      <p class="tv-subtitle">Track the tenders you have saved for follow-up.</p>
    </div>
  </div>

  <table class="tv-table">
    <thead>
      <tr>
        <th>Title</th>
        <th>Vendor</th>
        <th>Country</th>
        <th>Closing date</th>
        <th>Link</th>
      </tr>
    </thead>
    <tbody>
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
      {% else %}
        <tr><td colspan="5" class="muted">You have not saved any tenders yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
"""

ADMIN_LOGIN_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section tv-auth">
  <div class="tv-auth-card">
    <h1 class="tv-title">Admin Login</h1>
    <form method="post" class="tv-form-vertical">
      <label>Username
        <input name="username" class="tv-input">
      </label>
      <label>Password
        <input name="password" type="password" class="tv-input">
      </label>
      <button type="submit" class="btn-primary">Login</button>
    </form>
  </div>
</section>
{% endblock %}
"""

ADMIN_DASH_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section">
  <div class="tv-section-header">
    <div>
      <h1 class="tv-title">Admin Dashboard</h1>
      <p class="tv-subtitle">Manage vendors, tenders and users.</p>
    </div>
    <a href="{{ url_for('admin_logout') }}" class="btn-sm-outline">Logout admin</a>
  </div>

  <div class="tv-grid tv-grid-2">
    <div class="tv-card">
      <h2 class="tv-section-title">Add Vendor</h2>
      <form method="post" action="{{ url_for('admin_add_vendor') }}" class="tv-form-vertical">
        <label>Name <input name="name" required class="tv-input"></label>
        <label>Country <input name="country" required class="tv-input"></label>
        <label>Primary category <input name="category_primary" class="tv-input"></label>
        <label>Email <input name="email" class="tv-input"></label>
        <label>Phone <input name="phone" class="tv-input"></label>
        <button type="submit" class="btn-primary">Save Vendor</button>
      </form>
    </div>

    <div class="tv-card">
      <h2 class="tv-section-title">Add Tender</h2>
      <form method="post" action="{{ url_for('admin_add_tender') }}" class="tv-form-vertical">
        <label>Title <input name="title" required class="tv-input"></label>
        <label>Country <input name="country" required class="tv-input"></label>
        <label>Operator <input name="operator" required class="tv-input"></label>
        <label>Vendor
          <select name="vendor_id" class="tv-input">
            <option value="">-- Select vendor --</option>
            {% for v in all_vendors %}
              <option value="{{ v.id }}">{{ v.name }} ({{ v.country }})</option>
            {% endfor %}
          </select>
        </label>
        <label>Source <input name="source" value="Manual" class="tv-input"></label>
        <label>Closing date (YYYY-MM-DD) <input name="closing_date" class="tv-input"></label>
        <label>Link <input name="link" class="tv-input"></label>
        <label>Description
          <textarea name="description" rows="4" class="tv-input"></textarea>
        </label>
        <button type="submit" class="btn-primary">Save Tender</button>
      </form>
    </div>
  </div>

  <div class="tv-links-row">
    <a href="{{ url_for('admin_list_users') }}" class="btn-link">View all users →</a>
    <a href="{{ url_for('admin_list_saved_tenders') }}" class="btn-link">View saved tenders →</a>
  </div>
</section>
{% endblock %}
"""

ADMIN_USERS_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section">
  <div class="tv-section-header">
    <h1 class="tv-title">Registered Users</h1>
  </div>
  <table class="tv-table">
    <thead>
      <tr><th>ID</th><th>Email</th><th>Created</th></tr>
    </thead>
    <tbody>
      {% for u in users %}
        <tr>
          <td>{{ u.id }}</td>
          <td>{{ u.email }}</td>
          <td>{{ u.created_at }}</td>
        </tr>
      {% else %}
        <tr><td colspan="3" class="muted">No users found.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
"""

ADMIN_SAVED_TENDERS_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section">
  <div class="tv-section-header">
    <h1 class="tv-title">Saved Tenders</h1>
  </div>
  <table class="tv-table">
    <thead>
      <tr><th>User</th><th>Tender</th><th>Vendor</th><th>Country</th></tr>
    </thead>
    <tbody>
      {% for row in rows %}
        <tr>
          <td>{{ row.user_email }}</td>
          <td>{{ row.tender_title }}</td>
          <td>{{ row.vendor_name }}</td>
          <td>{{ row.country }}</td>
        </tr>
      {% else %}
        <tr><td colspan="4" class="muted">No saved tenders yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
"""

SUBSCRIBE_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="tv-section tv-auth">
  <div class="tv-auth-card">
    <h1 class="tv-title">Subscribe</h1>
    {% if not stripe_enabled %}
      <p class="tv-subtitle">Stripe is not configured. Subscription checkout is disabled.</p>
    {% else %}
      <p class="tv-subtitle">Subscribe to unlock full access to all tenders.</p>
      <form method="post">
        <button type="submit" class="btn-primary">Go to Checkout</button>
      </form>
    {% endif %}
  </div>
</section>
{% endblock %}
"""

# ---------------------------------------------------------------------
# Context processor
# ---------------------------------------------------------------------


@app.context_processor
def inject_user():
    return {"user_email": current_user_email()}


# ---------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------


@app.route("/")
def home():
    # Latest vendors
    vres = (
        supabase.table("vendors")
        .select("id, name, country")
        .order("id", desc=True)
        .limit(10)
        .execute()
    )
    vendors = vres.data or []

    # Latest tenders
    tres = (
        supabase.table("tenders")
        .select("id, title, country, closing_date, vendor_id, description, link")
        .order("id", desc=True)
        .limit(10)
        .execute()
    )
    tenders = tres.data or []

    # Map vendor_id → name
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


@app.route("/tenders", methods=["GET", "POST"])
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
        except Exception as e:
            print("[register] error", e)
            flash("Registration failed (maybe email already used).", "error")
            return redirect(url_for("register"))

        flash("Registration successful. Please log in.", "ok")
        return redirect(url_for("login"))

    return render_template_string(AUTH_TEMPLATE, title="Register", button="Register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        res = (
            supabase.table("app_users")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        user = (res.data or [None])[0]

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials", "error")
            return redirect(url_for("login"))

        session["user_email"] = email
        flash("Logged in", "ok")
        return redirect(url_for("home"))

    return render_template_string(AUTH_TEMPLATE, title="Login", button="Login")


@app.route("/logout")
def logout():
    session.pop("user_email", None)
    flash("Logged out", "ok")
    return redirect(url_for("home"))


# ---------------------------------------------------------------------
# Saved tenders
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
# Admin routes
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

    return render_template_string(ADMIN_DASH_TEMPLATE, all_vendors=all_vendors)


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
        "source": request.form.get("source", "Manual"),
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

    res = (
        supabase.table("app_users")
        .select("id, email, created_at")
        .order("id")
        .execute()
    )
    users = res.data or []

    return render_template_string(ADMIN_USERS_TEMPLATE, users=users)


@app.route("/admin/saved-tenders")
def admin_list_saved_tenders():
    if not admin_required():
        return redirect(url_for("admin_login"))

    sres = supabase.table("user_saved_tenders").select("*").execute()
    rows = sres.data or []

    if not rows:
        return render_template_string(ADMIN_SAVED_TENDERS_TEMPLATE, rows=[])

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

    return render_template_string(ADMIN_SAVED_TENDERS_TEMPLATE, rows=enriched)


# ---------------------------------------------------------------------
# Subscription (Stripe – optional)
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
                success_url=url_for("home", _external=True) + "?checkout=success",
                cancel_url=url_for("subscribe", _external=True),
            )
            return redirect(checkout.url)
        except Exception as e:
            print("[stripe] error", e)
            flash("Could not start checkout. Please try again later.", "error")

    return render_template_string(
        SUBSCRIBE_TEMPLATE,
        stripe_enabled=stripe_enabled,
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
        except Exception as e:
            print(f"[auto-scrape] Error: {e}")
        time.sleep(30 * 60)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

if __name__ == "__main__":
    print("Running Flask app on http://127.0.0.1:5000")
    # If you want auto-scrape locally, uncomment:
    # t = threading.Thread(target=auto_scrape_loop, daemon=True)
    # t.start()
    app.run(debug=True)
