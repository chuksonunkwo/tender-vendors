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

# Optional scrapers package
try:
    from .scrapers.run_all import run_all_scrapers
except Exception:  # pragma: no cover
    run_all_scrapers = None

# Optional Stripe
try:
    import stripe
except ImportError:  # pragma: no cover
    stripe = None


# ---------------------------------------------------------------------
# Environment / Supabase
# ---------------------------------------------------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in environment")

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


def login_required() -> bool:
    return current_user_email() is not None


def admin_logged_in() -> bool:
    return session.get("is_admin") is True


def admin_required() -> bool:
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
# Global context (nav)
# ---------------------------------------------------------------------
@app.context_processor
def inject_base():
    return {
        "user_email": current_user_email(),
    }


# ---------------------------------------------------------------------
# Templates (children extend templates/base.html)
# ---------------------------------------------------------------------

HOME_TEMPLATE = """
{% extends "base.html" %}
{% block title %}{% endblock %}
{% block content %}

<div class="row g-3 mb-3 align-items-start">
  <div class="col-12 col-md-7">
    <div class="tv-page-title mb-1">Discover Public Tender Opportunities</div>
    <div class="tv-page-subtitle">
      Browse the latest oil &amp; gas tenders across Africa and save the ones that matter to you.
    </div>
  </div>
  <div class="col-12 col-md-5 text-md-end small text-muted mt-2 mt-md-0">
    {% if user_email %}
      <div>Signed in as <strong>{{ user_email }}</strong></div>
      <div class="text-success">● Logged in</div>
    {% else %}
      <div class="mb-1">You are browsing as a guest.</div>
      <a href="{{ url_for('register') }}" class="btn btn-primary btn-sm">Create free account</a>
    {% endif %}
  </div>
</div>

<div class="row g-3 mb-4">
  <div class="col-6 col-md-3">
    <div class="card tv-stat-card">
      <div class="card-body py-3">
        <div class="tv-stat-label">Active Tenders</div>
        <div class="tv-stat-value">{{ active_tenders }}</div>
      </div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="card tv-stat-card">
      <div class="card-body py-3">
        <div class="tv-stat-label">Vendors</div>
        <div class="tv-stat-value">{{ vendor_count }}</div>
      </div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="card tv-stat-card">
      <div class="card-body py-3">
        <div class="tv-stat-label">Saved Tenders</div>
        <div class="tv-stat-value">{{ saved_count_display }}</div>
      </div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="card tv-stat-card">
      <div class="card-body py-3">
        <div class="tv-stat-label">Your Status</div>
        <div class="tv-stat-value small fw-semibold">{{ user_status }}</div>
      </div>
    </div>
  </div>
</div>

<div class="d-flex justify-content-between align-items-center mb-2">
  <div class="fw-semibold">Latest Tenders</div>
  <a href="{{ url_for('tenders_page') }}" class="small">Browse all &rarr;</a>
</div>

<div class="table-responsive">
  <table class="table table-sm align-middle mb-0">
    <thead class="table-light">
      <tr>
        <th>Title</th>
        <th>Country</th>
        <th>Closing date</th>
        <th style="width: 120px;">Link</th>
      </tr>
    </thead>
    <tbody>
      {% for t in latest_tenders %}
      <tr>
        <td class="small fw-semibold" style="max-width: 420px;">
          {{ t.title }}
        </td>
        <td class="small">{{ t.country }}</td>
        <td class="small">{{ t.closing_date or "" }}</td>
        <td class="small">
          {% if t.link %}
          <a href="{{ t.link }}" target="_blank"
             class="btn btn-outline-secondary btn-xs btn-sm">View</a>
          {% endif %}
        </td>
      </tr>
      {% else %}
      <tr>
        <td colspan="4" class="text-muted small py-4 text-center">
          No tenders have been loaded yet.
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% endblock %}
"""

TENDERS_PAGE_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · Browse{% endblock %}
{% block content %}

<div class="d-flex justify-content-between align-items-start mb-3">
  <div>
    <div class="tv-page-title">Browse Tenders</div>
    <div class="tv-page-subtitle">
      Filter by country or keywords and save opportunities to your watchlist.
    </div>
  </div>
  {% if user_email %}
  <div class="text-end small text-muted">
    Signed in as<br><strong>{{ user_email }}</strong>
  </div>
  {% endif %}
</div>

<form method="get" class="row gy-2 gx-2 align-items-end mb-3">
  <div class="col-12 col-md-5">
    <label class="form-label small text-muted mb-1">Search by title, operator, or keywords</label>
    <input name="q" class="form-control form-control-sm" value="{{ q }}"
           placeholder="e.g. drilling, offshore, Nigeria">
  </div>
  <div class="col-6 col-md-3">
    <label class="form-label small text-muted mb-1">Country</label>
    <input name="country" class="form-control form-control-sm" value="{{ country }}"
           placeholder="e.g. Nigeria">
  </div>
  <div class="col-4 col-md-2">
    <button type="submit" class="btn btn-primary btn-sm w-100 mt-3 mt-md-0">
      Apply filters
    </button>
  </div>
  <div class="col-12 col-md-2 text-md-end small text-muted">
    Showing <strong>{{ tenders|length }}</strong> tenders
  </div>
</form>

<div class="table-responsive">
  <table class="table table-sm align-middle mb-0">
    <thead class="table-light">
      <tr>
        <th>Title</th>
        <th>Vendor</th>
        <th>Country</th>
        <th>Closing date</th>
        <th style="width: 140px;">Actions</th>
      </tr>
    </thead>
    <tbody>
      {% for t in tenders %}
      <tr>
        <td style="max-width: 420px;">
          <div class="fw-semibold small">{{ t.title }}</div>
        </td>
        <td class="small text-muted">{{ t.vendor_name or "" }}</td>
        <td class="small">{{ t.country }}</td>
        <td class="small">{{ t.closing_date or "" }}</td>
        <td class="small">
          {% if t.link %}
          <a href="{{ t.link }}" target="_blank"
             class="btn btn-outline-secondary btn-xs btn-sm me-1">View</a>
          {% endif %}
          {% if user_email %}
          <form method="post" action="{{ url_for('save_tender', tender_id=t.id) }}"
                style="display:inline;">
            <button type="submit" class="btn btn-outline-primary btn-xs btn-sm">
              Save
            </button>
          </form>
          {% endif %}
        </td>
      </tr>
      {% else %}
      <tr>
        <td colspan="5" class="text-muted small py-4 text-center">
          No tenders match your filters yet.
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% endblock %}
"""

TENDER_DETAIL_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · Tender{% endblock %}
{% block content %}

<div class="mb-3">
  <div class="tv-page-title">{{ tender.title }}</div>
  <div class="tv-page-subtitle">
    {{ tender.country or "—" }}
    {% if tender.operator %} · Operator: {{ tender.operator }}{% endif %}
    {% if tender.vendor_name %} · Vendor: {{ tender.vendor_name }}{% endif %}
  </div>
</div>

<div class="row g-3 mb-3">
  <div class="col-12 col-md-8">
    <div class="card mb-3">
      <div class="card-header py-2">
        <strong>Overview</strong>
      </div>
      <div class="card-body">
        {% if tender.description %}
          <p class="small mb-0" style="white-space: pre-wrap;">
            {{ tender.description }}
          </p>
        {% else %}
          <p class="small text-muted mb-0">
            No description has been captured for this tender yet.
          </p>
        {% endif %}
      </div>
    </div>

    <div class="card">
      <div class="card-header py-2">
        <strong>Key Details</strong>
      </div>
      <div class="card-body small">
        <dl class="row mb-0">
          <dt class="col-4 col-md-3">Country</dt>
          <dd class="col-8 col-md-9">{{ tender.country or "—" }}</dd>

          <dt class="col-4 col-md-3">Operator</dt>
          <dd class="col-8 col-md-9">{{ tender.operator or "—" }}</dd>

          <dt class="col-4 col-md-3">Vendor</dt>
          <dd class="col-8 col-md-9">{{ tender.vendor_name or "—" }}</dd>

          <dt class="col-4 col-md-3">Source</dt>
          <dd class="col-8 col-md-9">{{ tender.source or "—" }}</dd>

          <dt class="col-4 col-md-3">Closing date</dt>
          <dd class="col-8 col-md-9">{{ tender.closing_date or "—" }}</dd>

          <dt class="col-4 col-md-3">Link</dt>
          <dd class="col-8 col-md-9">
            {% if tender.link %}
              <a href="{{ tender.link }}" target="_blank">Open official notice</a>
            {% else %}
              <span class="text-muted">No external link available</span>
            {% endif %}
          </dd>
        </dl>
      </div>
    </div>
  </div>

  <div class="col-12 col-md-4">
    <div class="card mb-3">
      <div class="card-header py-2">
        <strong>Actions</strong>
      </div>
      <div class="card-body small">
        {% if tender.link %}
        <a href="{{ tender.link }}" target="_blank"
           class="btn btn-outline-secondary btn-sm w-100 mb-2">
          Open official notice
        </a>
        {% endif %}

        {% if user_email %}
        <form method="post"
              action="{{ url_for('save_tender', tender_id=tender.id) }}">
          <button type="submit" class="btn btn-primary btn-sm w-100">
            Save to my tenders
          </button>
        </form>
        {% else %}
        <p class="text-muted mb-2">
          Login to save this tender to your watchlist.
        </p>
        <a href="{{ url_for('login') }}" class="btn btn-primary btn-sm w-100 mb-1">
          Login
        </a>
        <a href="{{ url_for('register') }}" class="btn btn-outline-secondary btn-sm w-100">
          Register
        </a>
        {% endif %}
      </div>
    </div>

    <a href="{{ url_for('tenders_page') }}" class="small">&larr; Back to all tenders</a>
  </div>
</div>

{% endblock %}
"""

VENDORS_PAGE_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · Vendors{% endblock %}
{% block content %}

<div class="mb-3">
  <div class="tv-page-title">Vendors</div>
  <div class="tv-page-subtitle">
    Browse registered suppliers and service companies supporting African oil &amp; gas.
  </div>
</div>

<form method="get" class="row gy-2 gx-2 align-items-end mb-3">
  <div class="col-12 col-md-5">
    <label class="form-label small text-muted mb-1">Search by vendor name</label>
    <input name="q" class="form-control form-control-sm" value="{{ q }}"
           placeholder="e.g. Chevron, NNPC">
  </div>
  <div class="col-6 col-md-3">
    <label class="form-label small text-muted mb-1">Country</label>
    <input name="country" class="form-control form-control-sm" value="{{ country }}"
           placeholder="e.g. Nigeria">
  </div>
  <div class="col-4 col-md-2">
    <button type="submit" class="btn btn-primary btn-sm w-100 mt-3 mt-md-0">
      Apply filters
    </button>
  </div>
  <div class="col-12 col-md-2 text-md-end small text-muted">
    {{ vendors|length }} vendors
  </div>
</form>

<div class="table-responsive">
  <table class="table table-sm align-middle mb-0">
    <thead class="table-light">
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
        <td class="small fw-semibold">{{ v.name }}</td>
        <td class="small">{{ v.country }}</td>
        <td class="small text-muted">{{ v.category_primary }}</td>
        <td class="small">
          {% if v.email %}
          <a href="mailto:{{ v.email }}">{{ v.email }}</a>
          {% endif %}
        </td>
        <td class="small">{{ v.phone }}</td>
      </tr>
      {% else %}
      <tr>
        <td colspan="5" class="text-muted small py-4 text-center">
          No vendors found yet.
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% endblock %}
"""

AUTH_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · {{ title }}{% endblock %}
{% block content %}

<div class="row justify-content-center">
  <div class="col-12 col-md-5">
    <div class="mb-3">
      <div class="tv-page-title">{{ title }}</div>
      <div class="tv-page-subtitle">
        {% if title == 'Login' %}
          Access your saved tenders and personalised feed.
        {% else %}
          Create a free account to save tenders and receive updates.
        {% endif %}
      </div>
    </div>

    <form method="post" class="needs-validation" novalidate>
      <div class="mb-3">
        <label class="form-label small text-muted">Email</label>
        <input type="email" name="email" class="form-control" required>
      </div>
      <div class="mb-3">
        <label class="form-label small text-muted">Password</label>
        <input type="password" name="password" class="form-control" required>
      </div>
      <button type="submit" class="btn btn-primary w-100">{{ button }}</button>
    </form>
  </div>
</div>

{% endblock %}
"""

MY_TENDERS_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · My Tenders{% endblock %}
{% block content %}

<div class="mb-3 d-flex justify-content-between align-items-center">
  <div>
    <div class="tv-page-title">My Saved Tenders</div>
    <div class="tv-page-subtitle">
      Track the tenders you care about in one place.
    </div>
  </div>
</div>

{% if tenders %}
<div class="table-responsive">
  <table class="table table-sm align-middle mb-0">
    <thead class="table-light">
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
        <td class="small fw-semibold">{{ t.title }}</td>
        <td class="small text-muted">{{ t.vendor_name }}</td>
        <td class="small">{{ t.country }}</td>
        <td class="small">{{ t.closing_date or "" }}</td>
        <td class="small">
          <a href="{{ url_for('tender_detail', tender_id=t.id) }}"
   class="btn btn-outline-secondary btn-xs btn-sm me-1">
  View
</a>
{% if t.link %}
  <a href="{{ t.link }}" target="_blank"
     class="btn btn-link btn-sm p-0 align-baseline small">
    Official
  </a>
{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% else %}
<div class="text-center py-5">
  <div class="mb-2" style="font-size:42px;">♡</div>
  <p class="mb-1 fw-semibold">No saved tenders yet</p>
  <p class="text-muted small mb-3">
    Browse tenders and click <strong>Save</strong> to build your watchlist.
  </p>
  <a href="{{ url_for('tenders_page') }}" class="btn btn-primary btn-sm">
    Browse tenders
  </a>
</div>
{% endif %}

{% endblock %}
"""

ADMIN_LOGIN_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · Admin Login{% endblock %}
{% block content %}

<div class="row justify-content-center">
  <div class="col-12 col-md-5">
    <div class="mb-3">
      <div class="tv-page-title">Admin Login</div>
      <div class="tv-page-subtitle">
        Restricted access for platform administrators.
      </div>
    </div>

    <form method="post">
      <div class="mb-3">
        <label class="form-label small text-muted">Username</label>
        <input name="username" class="form-control" required>
      </div>
      <div class="mb-3">
        <label class="form-label small text-muted">Password</label>
        <input type="password" name="password" class="form-control" required>
      </div>
      <button type="submit" class="btn btn-primary w-100">Login</button>
    </form>
  </div>
</div>

{% endblock %}
"""

ADMIN_DASH_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · Admin{% endblock %}
{% block content %}

<div class="mb-3 d-flex justify-content-between align-items-center">
  <div>
    <div class="tv-page-title">Admin Dashboard</div>
    <div class="tv-page-subtitle">
      Manage vendors, tenders and user activity.
    </div>
  </div>
  <div class="small">
    <a href="{{ url_for('admin_logout') }}" class="text-danger">Logout admin</a>
  </div>
</div>

<div class="row g-3">
  <div class="col-12 col-lg-6">
    <div class="card">
      <div class="card-header py-2">
        <strong>Add Vendor</strong>
      </div>
      <div class="card-body">
        <form method="post" action="{{ url_for('admin_add_vendor') }}">
          <div class="mb-2">
            <label class="form-label small text-muted">Name</label>
            <input name="name" class="form-control form-control-sm" required>
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Country</label>
            <input name="country" class="form-control form-control-sm" required>
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Primary category</label>
            <input name="category_primary" class="form-control form-control-sm">
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Email</label>
            <input name="email" class="form-control form-control-sm">
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Phone</label>
            <input name="phone" class="form-control form-control-sm">
          </div>
          <button type="submit" class="btn btn-primary btn-sm mt-1">Save Vendor</button>
        </form>
      </div>
    </div>
  </div>

  <div class="col-12 col-lg-6">
    <div class="card">
      <div class="card-header py-2">
        <strong>Add Tender</strong>
      </div>
      <div class="card-body">
        <form method="post" action="{{ url_for('admin_add_tender') }}">
          <div class="mb-2">
            <label class="form-label small text-muted">Title</label>
            <input name="title" class="form-control form-control-sm" required>
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Country</label>
            <input name="country" class="form-control form-control-sm" required>
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Operator</label>
            <input name="operator" class="form-control form-control-sm" required>
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Vendor</label>
            <select name="vendor_id" class="form-select form-select-sm" required>
              <option value="">-- Select vendor --</option>
              {% for v in all_vendors %}
              <option value="{{ v.id }}">{{ v.name }} ({{ v.country }})</option>
              {% endfor %}
            </select>
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Source</label>
            <input name="source" class="form-control form-control-sm" value="Manual">
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Closing date (YYYY-MM-DD)</label>
            <input name="closing_date" class="form-control form-control-sm">
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Link</label>
            <input name="link" class="form-control form-control-sm">
          </div>
          <div class="mb-2">
            <label class="form-label small text-muted">Description</label>
            <textarea name="description" rows="3"
                      class="form-control form-control-sm"></textarea>
          </div>
          <button type="submit" class="btn btn-primary btn-sm mt-1">Save Tender</button>
        </form>
      </div>
    </div>
  </div>
</div>

<hr class="my-4">

<div class="d-flex flex-wrap gap-2">
  <a href="{{ url_for('admin_list_users') }}" class="btn btn-outline-secondary btn-sm">
    View users
  </a>
  <a href="{{ url_for('admin_list_saved_tenders') }}" class="btn btn-outline-secondary btn-sm">
    View saved tenders
  </a>
</div>

{% endblock %}
"""

ADMIN_USERS_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · Admin · Users{% endblock %}
{% block content %}

<div class="mb-3">
  <div class="tv-page-title">Registered Users</div>
  <div class="tv-page-subtitle">Overview of accounts created on the platform.</div>
</div>

<div class="table-responsive">
  <table class="table table-sm align-middle mb-0">
    <thead class="table-light">
      <tr>
        <th>ID</th>
        <th>Email</th>
        <th>Created</th>
      </tr>
    </thead>
    <tbody>
      {% for u in users %}
      <tr>
        <td class="small">{{ u.id }}</td>
        <td class="small">{{ u.email }}</td>
        <td class="small text-muted">{{ u.created_at }}</td>
      </tr>
      {% else %}
      <tr>
        <td colspan="3" class="small text-muted py-4 text-center">No users yet.</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% endblock %}
"""

ADMIN_SAVED_TENDERS_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · Admin · Saved Tenders{% endblock %}
{% block content %}

<div class="mb-3">
  <div class="tv-page-title">Saved Tenders</div>
  <div class="tv-page-subtitle">Which tenders users are tracking.</div>
</div>

<div class="table-responsive">
  <table class="table table-sm align-middle mb-0">
    <thead class="table-light">
      <tr>
        <th>User</th>
        <th>Tender</th>
        <th>Vendor</th>
        <th>Country</th>
      </tr>
    </thead>
    <tbody>
      {% for row in rows %}
      <tr>
        <td class="small">{{ row.user_email }}</td>
        <td class="small fw-semibold">{{ row.tender_title }}</td>
        <td class="small text-muted">{{ row.vendor_name }}</td>
        <td class="small">{{ row.country }}</td>
      </tr>
      {% else %}
      <tr>
        <td colspan="4" class="small text-muted py-4 text-center">
          No saved tenders yet.
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% endblock %}
"""

SUBSCRIBE_TEMPLATE = """
{% extends "base.html" %}
{% block title %} · Subscribe{% endblock %}
{% block content %}

<div class="row justify-content-center">
  <div class="col-12 col-md-6">
    <div class="mb-3">
      <div class="tv-page-title">Subscribe</div>
      <div class="tv-page-subtitle">
        Unlock advanced tender filters and unlimited saved tenders.
      </div>
    </div>

    {% if not stripe_enabled %}
      <div class="alert alert-warning small">
        Stripe is not configured for this environment.
      </div>
    {% else %}
      <form method="post">
        <p class="small mb-3">
          Continue to secure checkout to start your subscription.
        </p>
        <button type="submit" class="btn btn-primary w-100">Go to Checkout</button>
      </form>
    {% endif %}
  </div>
</div>

{% endblock %}
"""


# ---------------------------------------------------------------------
# Routes – public
# ---------------------------------------------------------------------
@app.route("/")
def home():
    # Active tenders (simple approximate count)
    tres = supabase.table("tenders").select("id").limit(1000).execute()
    active_tenders = len(tres.data or [])

    # Vendor count
    vres = supabase.table("vendors").select("id").limit(1000).execute()
    vendor_count = len(vres.data or [])

    # Saved tenders for logged-in user
    email = current_user_email()
    if email:
        sres = (
            supabase.table("user_saved_tenders")
            .select("id")
            .eq("user_email", email)
            .limit(1000)
            .execute()
        )
        saved_count = len(sres.data or [])
        saved_count_display = saved_count
        user_status = "Logged in"
    else:
        saved_count = 0
        saved_count_display = "–"
        user_status = "Guest"

    # Latest tenders
    latest = (
        supabase.table("tenders")
        .select("id, title, country, closing_date, link")
        .order("id", desc=True)
        .limit(10)
        .execute()
    )
    latest_tenders = latest.data or []

    return render_template_string(
        HOME_TEMPLATE,
        active_tenders=active_tenders,
        vendor_count=vendor_count,
        saved_count_display=saved_count_display,
        user_status=user_status,
        latest_tenders=latest_tenders,
    )


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


@app.route("/tender/<int:tender_id>")
def tender_detail(tender_id: int):
    # Fetch tender
    res = (
        supabase.table("tenders")
        .select("*")
        .eq("id", tender_id)
        .limit(1)
        .execute()
    )
    data = res.data or []
    if not data:
        flash("Tender not found.", "error")
        return redirect(url_for("tenders_page"))

    tender = data[0]

    # Attach vendor name if available
    vendor_name = ""
    vid = tender.get("vendor_id")
    if vid:
        vres = (
            supabase.table("vendors")
            .select("id, name")
            .eq("id", vid)
            .limit(1)
            .execute()
        )
        vdata = vres.data or []
        if vdata:
            vendor_name = vdata[0]["name"]

    tender["vendor_name"] = vendor_name

    return render_template_string(TENDER_DETAIL_TEMPLATE, tender=tender)


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

    return render_template_string(
        AUTH_TEMPLATE, title="Login", button="Login"
    )


@app.route("/logout")
def logout():
    session.pop("user_email", None)
    flash("Logged out", "ok")
    return redirect(url_for("home"))


# ---------------------------------------------------------------------
# User saved tenders
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

    try:
        supabase.table("user_saved_tenders").insert(
            {"user_email": email, "tender_id": tender_id}
        ).execute()
        flash("Tender saved", "ok")
    except Exception as e:  # pragma: no cover
        print("[save_tender] error", e)
        flash("Could not save tender.", "error")

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
    # If you want auto-scrape locally, uncomment:
    # t = threading.Thread(target=auto_scrape_loop, daemon=True)
    # t.start()
    app.run(debug=True)
