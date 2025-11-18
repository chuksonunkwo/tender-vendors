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
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>TenderVendors – African Oil &amp; Gas Tenders</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <style>
    :root {
      --bg: #0b1020;
      --bg-soft: #0f172a;
      --bg-card: #111827;
      --bg-card-soft: #020617;
      --border-subtle: rgba(148, 163, 184, 0.2);
      --accent: #4f46e5;
      --accent-soft: rgba(79, 70, 229, 0.12);
      --accent-strong: #6366f1;
      --accent-stronger: #a855f7;
      --accent-soft-2: rgba(56, 189, 248, 0.2);
      --text-main: #e5e7eb;
      --text-soft: #9ca3af;
      --text-softer: #6b7280;
      --danger: #ef4444;
      --success: #22c55e;
      --warning: #f97316;
      --radius-lg: 18px;
      --radius-full: 999px;
      --shadow-soft: 0 22px 40px rgba(15, 23, 42, 0.8);
      --shadow-card: 0 18px 32px rgba(15, 23, 42, 0.6);
      --transition-fast: 150ms ease-out;
      --transition-med: 200ms ease-out;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text",
                   "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #111827 0%%, #020617 45%%, #000 100%%);
      color: var(--text-main);
      min-height: 100vh;
    }

    a {
      color: inherit;
      text-decoration: none;
    }

    .shell {
      max-width: 1180px;
      margin: 0 auto;
      padding: 20px 20px 40px;
    }

    /* ------------------------------------------------------------------
       Top navigation
       ------------------------------------------------------------------ */
    .nav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 18px;
      margin-bottom: 22px;
      border-radius: var(--radius-lg);
      background: linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(15, 23, 42, 0.94));
      border: 1px solid rgba(148, 163, 184, 0.25);
      box-shadow: var(--shadow-soft);
      backdrop-filter: blur(16px);
    }

    .nav-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .logo-pill {
      width: 34px;
      height: 34px;
      border-radius: 10px;
      background: radial-gradient(circle at 20%% 0, #38bdf8 0%%, #4f46e5 40%%, #a855f7 100%%);
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: 700;
      font-size: 17px;
      box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.8), 0 16px 30px rgba(15, 23, 42, 0.9);
    }

    .brand-title {
      font-weight: 700;
      font-size: 18px;
    }

    .brand-sub {
      font-size: 12px;
      color: var(--text-soft);
      margin-top: 2px;
    }

    .nav-center {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px;
      border-radius: 999px;
      background: rgba(15, 23, 42, 0.85);
      border: 1px solid rgba(148, 163, 184, 0.35);
    }

    .nav-tab {
      padding: 7px 15px;
      border-radius: 999px;
      font-size: 13px;
      color: var(--text-soft);
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background var(--transition-med), color var(--transition-med),
                  transform var(--transition-fast), box-shadow var(--transition-fast);
    }
    .nav-tab span.badge {
      padding: 2px 7px;
      border-radius: 999px;
      font-size: 11px;
      background: rgba(148, 163, 184, 0.08);
      color: var(--text-soft);
    }
    .nav-tab.active {
      background: radial-gradient(circle at top left, #4f46e5 0%%, #0f172a 55%%);
      color: #e5e7eb;
      box-shadow: 0 10px 20px rgba(15, 23, 42, 0.8);
      transform: translateY(-1px);
    }
    .nav-tab:hover {
      background: rgba(31, 41, 55, 0.95);
      color: #e5e7eb;
    }

    .nav-right {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .pill {
      padding: 7px 13px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid rgba(148, 163, 184, 0.4);
      color: var(--text-soft);
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(15, 23, 42, 0.9);
    }

    .pill-dot {
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: radial-gradient(circle at center, #22c55e 0%%, #15803d 60%%);
      box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.3);
    }

    .primary-btn {
      border-radius: 999px;
      border: none;
      font-size: 13px;
      padding: 8px 16px;
      font-weight: 600;
      color: white;
      cursor: pointer;
      background: linear-gradient(135deg, #6366f1, #a855f7);
      box-shadow: 0 12px 24px rgba(56, 189, 248, 0.15);
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: transform var(--transition-fast), box-shadow var(--transition-fast),
                  background var(--transition-med);
    }
    .primary-btn span.icon {
      font-size: 14px;
    }
    .primary-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 14px 32px rgba(37, 99, 235, 0.35);
    }

    /* ------------------------------------------------------------------
       Layout + cards
       ------------------------------------------------------------------ */
    .page {
      margin-top: 16px;
    }

    .page-grid {
      display: grid;
      grid-template-columns: minmax(0, 3.2fr) minmax(0, 2.3fr);
      gap: 18px;
    }

    .card {
      background: radial-gradient(circle at top left, rgba(15, 23, 42, 0.98), rgba(15, 23, 42, 0.96));
      border-radius: var(--radius-lg);
      padding: 18px 18px 18px;
      border: 1px solid var(--border-subtle);
      box-shadow: var(--shadow-card);
    }

    .card-soft {
      background: linear-gradient(145deg, rgba(15, 23, 42, 0.98), rgba(2, 6, 23, 0.96));
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    }

    .card-title {
      font-size: 16px;
      font-weight: 600;
    }

    .card-sub {
      font-size: 13px;
      color: var(--text-soft);
      margin-top: 2px;
    }

    .badge-soft {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 11px;
      background: rgba(56, 189, 248, 0.08);
      color: #7dd3fc;
      border: 1px solid rgba(56, 189, 248, 0.4);
    }

    .stat-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 10px;
    }

    .stat-card {
      border-radius: 16px;
      padding: 10px 11px;
      background: radial-gradient(circle at top, rgba(15, 23, 42, 0.96), rgba(15, 23, 42, 0.96));
      border: 1px solid rgba(148, 163, 184, 0.35);
      position: relative;
      overflow: hidden;
    }
    .stat-label {
      font-size: 11px;
      color: var(--text-soft);
      margin-bottom: 5px;
    }
    .stat-value {
      font-size: 18px;
      font-weight: 700;
    }
    .stat-meta {
      margin-top: 2px;
      font-size: 11px;
      color: var(--text-softer);
    }

    .pill-tag {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 2px 10px;
      font-size: 11px;
      border: 1px solid rgba(148, 163, 184, 0.4);
      color: var(--text-soft);
      background: rgba(15, 23, 42, 0.9);
    }

    .tenders-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 6px;
    }

    .tender-card {
      border-radius: 14px;
      padding: 12px 13px;
      background: radial-gradient(circle at top left, rgba(15, 23, 42, 0.98), rgba(15, 23, 42, 0.96));
      border: 1px solid rgba(30, 64, 175, 0.6);
      display: grid;
      grid-template-columns: minmax(0, 3.3fr) minmax(0, 1.4fr);
      column-gap: 12px;
      row-gap: 6px;
      transition: border-color var(--transition-fast), transform var(--transition-fast),
                  box-shadow var(--transition-fast), background var(--transition-med);
    }

    .tender-card:hover {
      transform: translateY(-1px);
      border-color: rgba(96, 165, 250, 0.9);
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.85);
      background: radial-gradient(circle at top left, rgba(30, 64, 175, 0.6), rgba(15, 23, 42, 0.98));
    }

    .tender-title-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 3px;
    }

    .tender-title {
      font-size: 15px;
      font-weight: 600;
    }

    .tender-chip {
      font-size: 11px;
      padding: 3px 9px;
      border-radius: 999px;
      background: rgba(22, 163, 74, 0.12);
      color: #4ade80;
      border: 1px solid rgba(34, 197, 94, 0.4);
    }

    .tender-meta {
      font-size: 12px;
      color: var(--text-soft);
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .tender-meta span {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }

    .tender-tags {
      margin-top: 5px;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .tag-pill {
      font-size: 11px;
      padding: 3px 9px;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.12);
      color: var(--text-soft);
      border: 1px solid rgba(148, 163, 184, 0.24);
    }

    .tender-actions {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      justify-content: space-between;
      gap: 6px;
      font-size: 12px;
    }

    .ghost-btn {
      border-radius: 999px;
      border: 1px solid rgba(148, 163, 184, 0.5);
      padding: 6px 11px;
      font-size: 12px;
      background: rgba(15, 23, 42, 0.9);
      color: var(--text-main);
      display: inline-flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      transition: background var(--transition-fast), border-color var(--transition-fast),
                  transform var(--transition-fast);
    }
    .ghost-btn:hover {
      background: rgba(30, 64, 175, 0.95);
      border-color: rgba(129, 140, 248, 0.9);
      transform: translateY(-0.5px);
    }

    .muted {
      font-size: 12px;
      color: var(--text-softer);
    }

    /* Tables used by admin pages – slight facelift */
    table {
      border-collapse: collapse;
      width: 100%%;
      margin-top: 10px;
      font-size: 13px;
    }
    th, td {
      border: 1px solid rgba(55, 65, 81, 0.9);
      padding: 7px 9px;
    }
    th {
      background: radial-gradient(circle at top, rgba(15, 23, 42, 0.98), rgba(15, 23, 42, 0.97));
      color: var(--text-soft);
      font-weight: 500;
      text-align: left;
    }
    tr:nth-child(even) td {
      background: rgba(15, 23, 42, 0.7);
    }
    tr:nth-child(odd) td {
      background: rgba(15, 23, 42, 0.9);
    }

    /* Forms */
    label {
      font-size: 13px;
      color: var(--text-soft);
    }
    input[type="text"],
    input[type="email"],
    input[type="password"],
    textarea,
    select {
      margin-top: 4px;
      margin-bottom: 10px;
      width: 100%%;
      border-radius: 10px;
      border: 1px solid rgba(75, 85, 99, 0.9);
      background: rgba(15, 23, 42, 0.95);
      color: var(--text-main);
      padding: 7px 9px;
      font-size: 13px;
    }
    input:focus,
    textarea:focus,
    select:focus {
      outline: none;
      border-color: rgba(129, 140, 248, 0.9);
      box-shadow: 0 0 0 1px rgba(129, 140, 248, 0.8);
    }

    button {
      font-family: inherit;
    }

    .btn-primary-form {
      border-radius: 999px;
      border: none;
      font-size: 13px;
      padding: 8px 16px;
      font-weight: 600;
      color: white;
      cursor: pointer;
      background: linear-gradient(135deg, #4f46e5, #22c55e);
      box-shadow: 0 10px 20px rgba(22, 163, 74, 0.28);
      transition: transform var(--transition-fast), box-shadow var(--transition-fast);
    }
    .btn-primary-form:hover {
      transform: translateY(-0.5px);
      box-shadow: 0 12px 24px rgba(22, 163, 74, 0.4);
    }

    .flash-ok { color: var(--success); }
    .flash-error { color: var(--danger); }

    @media (max-width: 960px) {
      .page-grid {
        grid-template-columns: minmax(0, 1fr);
      }
      .nav {
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
      }
      .nav-center {
        width: 100%%;
        justify-content: center;
      }
      .nav-right {
        width: 100%%;
        justify-content: space-between;
      }
      .tender-card {
        grid-template-columns: minmax(0, 1fr);
      }
      .tender-actions {
        align-items: flex-start;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="nav">
      <div class="nav-left">
        <div class="logo-pill">Tv</div>
        <div>
          <div class="brand-title">TenderVendors</div>
          <div class="brand-sub">Public tender listings across African oil &amp; gas</div>
        </div>
      </div>

      <nav class="nav-center">
        <a class="nav-tab {% if request.endpoint == 'tenders_page' %}active{% endif %}"
           href="{{ url_for('tenders_page') }}">
          Browse Tenders
          <span class="badge">Live feed</span>
        </a>
        <a class="nav-tab {% if request.endpoint in ['home', 'my_tenders'] %}active{% endif %}"
           href="{{ url_for('home') }}">
          My Dashboard
        </a>
      </nav>

      <div class="nav-right">
        <div class="pill">
          <span class="pill-dot"></span>
          <span>Scraping status: <strong>Live</strong></span>
        </div>

        {% if user_email %}
          <form method="get" action="{{ url_for('logout') }}" style="margin:0;">
            <button class="primary-btn" type="submit">
              <span class="icon">⇦</span>
              Logout
            </button>
          </form>
        {% else %}
          <a href="{{ url_for('login') }}" class="primary-btn">
            <span class="icon">★</span>
            Sign in to save
          </a>
        {% endif %}
      </div>
    </header>

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
  </div>
</body>
</html>
"""

HOME_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<div class="page-grid">
  <!-- Left: main dashboard -->
  <section class="card card-soft">
    <div class="card-header">
      <div>
        <div class="card-title">Vendor Dashboard</div>
        <div class="card-sub">
          Manage your saved tenders and track opportunities across African oil &amp; gas.
        </div>
      </div>
      <span class="badge-soft">
        <span style="width:6px;height:6px;border-radius:999px;background:#22c55e;"></span>
        Live data from Supabase
      </span>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">Saved Tenders</div>
        <div class="stat-value">
          {% if user_email %}{{ saved_count or 0 }}{% else %}0{% endif %}
        </div>
        <div class="stat-meta">
          {% if user_email %}
            Tenders you&apos;ve bookmarked to watch.
          {% else %}
            Sign in to start saving tenders.
          {% endif %}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Latest Tenders</div>
        <div class="stat-value">{{ tenders|length }}</div>
        <div class="stat-meta">Fetched from your Supabase database.</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Vendors Tracked</div>
        <div class="stat-value">{{ vendors|length }}</div>
        <div class="stat-meta">Companies in your directory.</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Closing Soon</div>
        <div class="stat-value">
          {{ tenders|selectattr("closing_date")|list|length }}
        </div>
        <div class="stat-meta">With a published closing date.</div>
      </div>
    </div>

    <div style="margin-top:18px;">
      <div class="card-header" style="margin-bottom:6px;">
        <div>
          <div class="card-title" style="font-size:15px;">My Saved Tenders</div>
          <div class="card-sub">
            Start browsing tenders and save the ones you&apos;re interested in.
          </div>
        </div>
        <a href="{{ url_for('tenders_page') }}" class="ghost-btn">
          Browse tenders
        </a>
      </div>

      {% if user_email %}
        {% if dashboard_tenders %}
          <div class="tenders-list">
            {% for t in dashboard_tenders %}
              <article class="tender-card">
                <div>
                  <div class="tender-title-row">
                    <div class="tender-title">{{ t.title }}</div>
                    <span class="tender-chip">Saved</span>
                  </div>
                  <div class="tender-meta">
                    <span>Vendor: <strong>{{ t.vendor_name or "Unknown" }}</strong></span>
                    <span>Country: {{ t.country or "—" }}</span>
                    {% if t.closing_date %}
                      <span>Closes: {{ t.closing_date }}</span>
                    {% endif %}
                  </div>
                  {% if t.description %}
                    <p class="muted" style="margin-top:5px;">
                      {{ t.description[:140] }}{% if t.description|length > 140 %}…{% endif %}
                    </p>
                  {% endif %}
                </div>
                <div class="tender-actions">
                  <div class="muted">
                    {% if t.link %}
                      <a href="{{ t.link }}" target="_blank" class="ghost-btn"
                         style="padding-inline:10px;">
                        View Tender
                      </a>
                    {% endif %}
                  </div>
                  <div class="muted">
                    Saved as {{ user_email }}
                  </div>
                </div>
              </article>
            {% endfor %}
          </div>
        {% else %}
          <div class="card" style="margin-top:4px; background:rgba(15,23,42,0.85);">
            <p class="muted">You haven&apos;t saved any tenders yet.</p>
          </div>
        {% endif %}
      {% else %}
        <div class="card" style="margin-top:4px; background:rgba(15,23,42,0.85);">
          <p class="muted">
            Create a free account to save tenders and track them on this dashboard.
          </p>
        </div>
      {% endif %}
    </div>
  </section>

  <!-- Right: quick feed -->
  <aside class="card">
    <div class="card-header">
      <div>
        <div class="card-title">Latest Tenders</div>
        <div class="card-sub">A quick snapshot of new opportunities.</div>
      </div>
      <a href="{{ url_for('tenders_page') }}" class="ghost-btn">View all</a>
    </div>

    <div class="tenders-list">
      {% for t in tenders %}
        <article class="tender-card">
          <div>
            <div class="tender-title-row">
              <div class="tender-title">{{ t.title }}</div>
            </div>
            <div class="tender-meta">
              <span>{{ t.vendor_name or "Vendor TBD" }}</span>
              <span>• {{ t.country or "N/A" }}</span>
              {% if t.closing_date %}
                <span>• Closes {{ t.closing_date }}</span>
              {% endif %}
            </div>
          </div>
          <div class="tender-actions">
            {% if t.link %}
              <a href="{{ t.link }}" target="_blank" class="ghost-btn">Open</a>
            {% endif %}
            <span class="muted">ID #{{ t.id }}</span>
          </div>
        </article>
      {% endfor %}
    </div>
  </aside>
</div>
{% endblock %}
"""

TENDERS_PAGE_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<section class="card card-soft">
  <div class="card-header">
    <div>
      <div class="card-title">Discover Public Tender Opportunities</div>
      <div class="card-sub">
        Filter and browse published tenders. Save the ones that match your business.
      </div>
    </div>
    <form method="get" style="display:flex; gap:8px; align-items:center;">
      <input type="text" name="q" placeholder="Search by title, operator or keyword…"
             value="{{ q }}" style="flex:1; min-width:220px;">
      <input type="text" name="country" placeholder="Country"
             value="{{ country }}" style="width:130px;">
      <button class="ghost-btn" type="submit">Apply filters</button>
    </form>
  </div>

  <div class="muted" style="margin-bottom:8px;">
    Showing {{ tenders|length }} tenders{% if q or country %} (filtered){% endif %}.
  </div>

  <div class="tenders-list">
    {% for t in tenders %}
      <article class="tender-card">
        <div>
          <div class="tender-title-row">
            <div class="tender-title">{{ t.title }}</div>
            {% if t.closing_date %}
              <span class="tender-chip">
                Closes {{ t.closing_date }}
              </span>
            {% endif %}
          </div>

          <div class="tender-meta">
            <span>Vendor: <strong>{{ t.vendor_name or "Unknown" }}</strong></span>
            <span>Country: {{ t.country or "—" }}</span>
          </div>

          <div class="tender-tags">
            {% if t.operator %}
              <span class="tag-pill">{{ t.operator }}</span>
            {% endif %}
            {% if t.category %}
              <span class="tag-pill">{{ t.category }}</span>
            {% endif %}
            {% if t.source %}
              <span class="tag-pill">Source: {{ t.source }}</span>
            {% endif %}
          </div>
        </div>

        <div class="tender-actions">
          <div style="display:flex; gap:6px;">
            {% if t.link %}
              <a href="{{ t.link }}" target="_blank" class="ghost-btn">View Tender</a>
            {% endif %}
            {% if user_email %}
              <form method="post" action="{{ url_for('save_tender', tender_id=t.id) }}">
                <button type="submit" class="ghost-btn">
                  <span>♡</span>
                  Save
                </button>
              </form>
            {% endif %}
          </div>
          <div class="muted">ID #{{ t.id }}</div>
        </div>
      </article>
    {% endfor %}
  </div>
</section>
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
<section class="card card-soft">
  <div class="card-header">
    <div>
      <div class="card-title">My Saved Tenders</div>
      <div class="card-sub">
        All tenders you&apos;ve bookmarked under {{ user_email }}.
      </div>
    </div>
    <a href="{{ url_for('tenders_page') }}" class="ghost-btn">Browse more</a>
  </div>

  {% if tenders %}
    <div class="tenders-list">
      {% for t in tenders %}
        <article class="tender-card">
          <div>
            <div class="tender-title-row">
              <div class="tender-title">{{ t.title }}</div>
              <span class="tender-chip">Saved</span>
            </div>
            <div class="tender-meta">
              <span>{{ t.vendor_name or "Unknown vendor" }}</span>
              <span>• {{ t.country or "N/A" }}</span>
              {% if t.closing_date %}
                <span>• Closes {{ t.closing_date }}</span>
              {% endif %}
            </div>
            {% if t.description %}
              <p class="muted" style="margin-top:6px;">
                {{ t.description[:160] }}{% if t.description|length > 160 %}…{% endif %}
              </p>
            {% endif %}
          </div>
          <div class="tender-actions">
            {% if t.link %}
              <a href="{{ t.link }}" target="_blank" class="ghost-btn">Open Tender</a>
            {% endif %}
            <span class="muted">ID #{{ t.id }}</span>
          </div>
        </article>
      {% endfor %}
    </div>
  {% else %}
    <p class="muted">You haven&apos;t saved any tenders yet.</p>
  {% endif %}
</section>
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
    return {"user_email": current_user_email()}


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
