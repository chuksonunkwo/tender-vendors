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
from .scrapers.run_all import run_all_scrapers
from email.message import EmailMessage
import smtplib
import stripe
import os
import threading
import time

# -------------------------------------------------
# Load environment variables
# -------------------------------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in environment")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Stripe config
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Flask / admin config
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

# Email (SMTP) config – optional
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)

# -------------------------------------------------
# Minimal styling
# -------------------------------------------------
BASE_STYLE = """
<style>
  body {
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin: 0;
    padding: 0;
    background: #f5f5f7;
  }
  nav {
    background: #111827;
    color: #f9fafb;
    padding: 10px 16px;
    font-size: 14px;
  }
  nav a {
    color: #e5e7eb;
    text-decoration: none;
    margin-right: 12px;
  }
  nav a:hover {
    text-decoration: underline;
  }
  .page {
    max-width: 960px;
    margin: 24px auto;
    padding: 24px;
    background: #ffffff;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.1);
  }
  h1 {
    margin-top: 0;
    font-size: 24px;
  }
  h2 {
    margin-top: 24px;
    font-size: 18px;
  }
  form {
    margin-bottom: 16px;
  }
  input, select, textarea, button {
    font: inherit;
    padding: 6px 8px;
    margin-top: 4px;
  }
  input, select, textarea {
    border: 1px solid #d1d5db;
    border-radius: 4px;
  }
  button {
    background: #111827;
    color: #f9fafb;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  button:hover {
    background: #1f2937;
  }
  ul {
    padding-left: 20px;
  }
  li {
    margin-bottom: 8px;
  }
  .message-ok {
    color: #15803d;
  }
  .message-error {
    color: #b91c1c;
  }
  table {
    border-collapse: collapse;
    width: 100%;
  }
  th, td {
    padding: 8px;
    border: 1px solid #e5e7eb;
    text-align: left;
  }
  th {
    background: #f3f4f6;
  }
</style>
"""

# -------------------------------------------------
# Templates
# -------------------------------------------------
HOME_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Tender & Vendor App</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    {% if current_user_email %}
      <p>Logged in as: <strong>{{ current_user_email }}</strong>
         (<a href="{{ url_for('logout_user') }}">Logout</a>)</p>
    {% endif %}

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
      <li>{{ t.title }} — {{ t.country }} — {{ t.source }}</li>
    {% endfor %}
    </ul>
  </div>
</body>
</html>
"""

VENDORS_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Vendors</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    <h1>Vendors</h1>

    <form method="get">
      <label>Search:
        <input name="q" value="{{ q or '' }}">
      </label>
      <label>Country:
        <select name="country">
          <option value="">All</option>
          <option value="Nigeria" {% if country=='Nigeria' %}selected{% endif %}>Nigeria</option>
          <option value="Angola" {% if country=='Angola' %}selected{% endif %}>Angola</option>
        </select>
      </label>
      <button type="submit">Filter</button>
    </form>

    <ul>
    {% for v in vendors %}
      <li>
        <strong>
          <a href="{{ url_for('vendor_detail', vendor_id=v.id) }}">
            {{ v.name }}
          </a>
        </strong>
        — {{ v.country }}
        {% if v.category_primary %} ({{ v.category_primary }}){% endif %}
      </li>
    {% endfor %}
    </ul>

    {% if not vendors %}
      <p>No vendors found.</p>
    {% endif %}
  </div>
</body>
</html>
"""

VENDOR_DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Vendor: {{ vendor.name }}</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    <h1>Vendor: {{ vendor.name }}</h1>

    <h2>Details</h2>
    <p><strong>Country:</strong> {{ vendor.country or 'N/A' }}</p>
    <p><strong>Primary category:</strong> {{ vendor.category_primary or 'N/A' }}</p>
    <p><strong>Email:</strong> {{ vendor.email or 'N/A' }}</p>
    <p><strong>Phone:</strong> {{ vendor.phone or 'N/A' }}</p>
    <p><strong>Source:</strong> {{ vendor.source or 'N/A' }}</p>

    <h2>Tenders from this vendor</h2>
    {% if tenders %}
      <ul>
      {% for t in tenders %}
        <li>
          <strong>{{ t.title }}</strong> — {{ t.country }} — {{ t.source }}
          {% if t.closing_date %} (Closes: {{ t.closing_date }}){% endif %}
          {% if t.link %}
            <br>Link: <a href="{{ t.link }}" target="_blank">{{ t.link }}</a>
          {% endif %}
          {% if t.description %}
            <br>Description: {{ t.description }}
          {% endif %}
        </li>
      {% endfor %}
      </ul>
    {% else %}
      <p>No tenders currently linked to this vendor.</p>
    {% endif %}

    <p><a href="{{ url_for('vendors_page') }}">&larr; Back to vendors</a></p>
  </div>
</body>
</html>
"""

TENDERS_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Tenders</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    {% if current_user_email %}
      <p>Logged in as <strong>{{ current_user_email }}</strong>
         (<a href="{{ url_for('logout_user') }}">Logout</a>)</p>
    {% else %}
      <p><strong>You are not logged in.</strong> Only paid subscribers can save tenders.
         <a href="{{ url_for('login_user') }}">Login</a> or
         <a href="{{ url_for('register_user') }}">Register</a>.
      </p>
    {% endif %}

    <h1>Tenders</h1>

    <form method="get">
      <label>Search:
        <input name="q" value="{{ q or '' }}">
      </label>

      <label>Country:
        <select name="country">
          <option value="">All</option>
          <option value="Nigeria" {% if country=='Nigeria' %}selected{% endif %}>Nigeria</option>
          <option value="Angola" {% if country=='Angola' %}selected{% endif %}>Angola</option>
        </select>
      </label>

      <label>Operator:
        <input name="operator" value="{{ operator_filter or '' }}">
      </label>

      <label>Closing from:
        <input type="date" name="closing_from" value="{{ closing_from or '' }}">
      </label>

      <label>Closing to:
        <input type="date" name="closing_to" value="{{ closing_to or '' }}">
      </label>

      <button type="submit">Filter</button>
      <a href="{{ url_for('tenders_page') }}">Reset</a>
    </form>

    <ul>
    {% for t in tenders %}
      <li>
        <strong>{{ t.title }}</strong> — {{ t.country }} — {{ t.source }}
        {% if t.closing_date %} (Closes: {{ t.closing_date }}){% endif %}

        {% if current_user_email %}
          {% if t.link %}
            <br>Link: <a href="{{ t.link }}" target="_blank">{{ t.link }}</a>
          {% endif %}
          {% if t.description %}
            <br>Description: {{ t.description }}
          {% endif %}
          <br>
          {% if t.id in saved_ids %}
            <strong>★ Saved</strong>
            (<a href="{{ url_for('unsave_tender', tender_id=t.id) }}">Remove</a>)
          {% else %}
            <a href="{{ url_for('save_tender', tender_id=t.id) }}">★ Save this tender (Premium)</a>
          {% endif %}
        {% else %}
          <br><em>Login to see full link, description, and save tenders.</em>
        {% endif %}
      </li>
    {% endfor %}
    </ul>

    {% if not tenders %}
      <p>No tenders found.</p>
    {% endif %}
  </div>
</body>
</html>
"""

MY_TENDERS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>My Saved Tenders</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    {% if current_user_email %}
      <p>Logged in as <strong>{{ current_user_email }}</strong>
         (<a href="{{ url_for('logout_user') }}">Logout</a>)</p>
    {% endif %}

    <h1>My Saved Tenders</h1>

    <ul>
    {% for t in tenders %}
      <li>
        <strong>{{ t.title }}</strong> — {{ t.country }} — {{ t.source }}
        {% if t.closing_date %} (Closes: {{ t.closing_date }}){% endif %}
        {% if t.link %}
          <br>Link: <a href="{{ t.link }}" target="_blank">{{ t.link }}</a>
        {% endif %}
        {% if t.description %}
          <br>Description: {{ t.description }}
        {% endif %}
        <br>
        <a href="{{ url_for('unsave_tender', tender_id=t.id) }}">Remove from saved</a>
      </li>
    {% endfor %}
    </ul>

    {% if not tenders %}
      <p>You have not saved any tenders yet.</p>
    {% endif %}
  </div>
</body>
</html>
"""

MY_SUBSCRIPTION_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>My Subscription</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    <h1>My Subscription</h1>

    <p>Logged in as <strong>{{ email }}</strong></p>

    {% if not db_sub %}
      <p>You do not have an active subscription.</p>
      <p><a href="{{ url_for('subscribe') }}">Subscribe now</a> to unlock saving tenders and alerts.</p>
    {% else %}
      <h2>Status</h2>
      <p>
        Stripe status:
        <strong>{{ status or 'unknown' }}</strong>
        {% if current_period_end %}
          (current period ends: {{ current_period_end }})
        {% endif %}
      </p>

      <h2>Billing</h2>
      <p>You can update card details or cancel via the billing portal.</p>
      <form method="get" action="{{ url_for('billing_portal') }}">
        <button type="submit">Open billing portal</button>
      </form>
    {% endif %}
  </div>
</body>
</html>
"""

REGISTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Register</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    <h1>Register</h1>
    <form method="post">
      <label>Email: <input name="email" type="email" required></label><br>
      <label>Password: <input name="password" type="password" required></label><br>
      <button type="submit">Create account</button>
    </form>
  </div>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Login</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    <h1>User Login</h1>
    <form method="post">
      <label>Email: <input name="email" type="email" required></label><br>
      <label>Password: <input name="password" type="password" required></label><br>
      <button type="submit">Login</button>
    </form>
  </div>
</body>
</html>
"""

ADMIN_LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Admin Login</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    <h1>Admin Login</h1>
    <form method="post">
      <label>Username: <input name="username"></label><br>
      <label>Password: <input type="password" name="password"></label><br>
      <button type="submit">Login</button>
    </form>
  </div>
</body>
</html>
"""

ADMIN_DASH_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Admin Dashboard</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('vendors_page') }}">Vendors</a>
    <a href="{{ url_for('tenders_page') }}">Tenders</a>
    <a href="{{ url_for('my_tenders') }}">My Tenders</a>
    <a href="{{ url_for('my_subscription') }}">My Subscription</a>
    <a href="{{ url_for('subscribe') }}">Subscribe</a>
    <a href="{{ url_for('login_user') }}">Login</a>
    <a href="{{ url_for('register_user') }}">Register</a>
    <a href="{{ url_for('admin_login') }}">Admin</a>
    <a href="{{ url_for('admin_logout') }}">Logout</a>
  </nav>

  <div class="page">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <p class="message-{{ cat }}">{{ msg }}</p>
      {% endfor %}
    {% endwith %}

    <h1>Admin Dashboard</h1>

    <h2>Run Scrapers</h2>
    <form method="post" action="{{ url_for('admin_run_scrapers') }}">
      <button type="submit">Run scrapers now</button>
    </form>

    <hr>

    <h2>Add Vendor</h2>
    <form method="post" action="{{ url_for('admin_add_vendor') }}">
      <label>Name: <input name="name" required></label><br>
      <label>Country:
        <select name="country">
          <option value="Nigeria">Nigeria</option>
          <option value="Angola">Angola</option>
        </select>
      </label><br>
      <label>Category (primary): <input name="category_primary"></label><br>
      <label>Email: <input name="email"></label><br>
      <label>Phone: <input name="phone"></label><br>
      <button type="submit">Save Vendor</button>
    </form>

    <h2>Add Tender</h2>
    <form method="post" action="{{ url_for('admin_add_tender') }}">
      <label>Title: <input name="title" required></label><br>
      <label>Country:
        <select name="country">
          <option value="Nigeria">Nigeria</option>
          <option value="Angola">Angola</option>
        </select>
      </label><br>
      <label>Operator: <input name="operator"></label><br>
      <label>Source: <input name="source" value="Manual" required></label><br>
      <label>Closing date (YYYY-MM-DD): <input name="closing_date"></label><br>
      <label>Link: <input name="link"></label><br>
      <label>Description:<br>
        <textarea name="description" rows="4" cols="40"></textarea>
      </label><br>
      <button type="submit">Save Tender</button>
    </form>

    <hr>

    <h2>Registered Users</h2>
    <p><a href="{{ url_for('admin_list_users') }}">View all users</a></p>

    <h2>Subscriptions</h2>
    <p><a href="{{ url_for('admin_list_subscriptions') }}">View subscriptions</a></p>

    <h2>Saved Tenders</h2>
    <p><a href="{{ url_for('admin_saved_tenders') }}">View saved tenders</a></p>
  </div>
</body>
</html>
"""

ADMIN_USERS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Registered Users</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('admin_dashboard') }}">Admin Dashboard</a>
  </nav>

  <div class="page">
    <h1>Registered Users</h1>

    <table>
      <tr>
        <th>ID</th>
        <th>Email</th>
        <th>Paid?</th>
        <th>Created At</th>
      </tr>
      {% for u in users %}
      <tr>
        <td>{{ u.id }}</td>
        <td>{{ u.email }}</td>
        <td>{% if u.is_paid %}Yes{% else %}No{% endif %}</td>
        <td>{{ u.created_at }}</td>
      </tr>
      {% endfor %}
    </table>

    {% if not users %}
      <p>No users yet.</p>
    {% endif %}
  </div>
</body>
</html>
"""

ADMIN_SUBSCRIPTIONS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Subscriptions</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('admin_dashboard') }}">Admin Dashboard</a>
  </nav>

  <div class="page">
    <h1>Subscriptions</h1>

    <table>
      <tr>
        <th>ID</th>
        <th>User Email</th>
        <th>Stripe Customer</th>
        <th>Stripe Subscription</th>
        <th>Active?</th>
        <th>Created At</th>
      </tr>
      {% for s in subs %}
      <tr>
        <td>{{ s.id }}</td>
        <td>{{ s.user_email }}</td>
        <td>{{ s.stripe_customer_id or '-' }}</td>
        <td>{{ s.stripe_subscription_id or '-' }}</td>
        <td>{% if s.is_active %}Yes{% else %}No{% endif %}</td>
        <td>{{ s.created_at }}</td>
      </tr>
      {% endfor %}
    </table>

    {% if not subs %}
      <p>No subscriptions yet.</p>
    {% endif %}
  </div>
</body>
</html>
"""

ADMIN_SAVED_TENDERS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Saved Tenders</title>
  {{ base_style|safe }}
</head>
<body>
  <nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('admin_dashboard') }}">Admin Dashboard</a>
  </nav>

  <div class="page">
    <h1>Saved Tenders</h1>

    <table>
      <tr>
        <th>ID</th>
        <th>User Email</th>
        <th>Tender ID</th>
        <th>Saved At</th>
      </tr>
      {% for r in rows %}
      <tr>
        <td>{{ r.id }}</td>
        <td>{{ r.user_email }}</td>
        <td>{{ r.tender_id }}</td>
        <td>{{ r.saved_at }}</td>
      </tr>
      {% endfor %}
    </table>

    {% if not rows %}
      <p>No tenders have been saved yet.</p>
    {% endif %}
  </div>
</body>
</html>
"""

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def admin_required():
    return session.get("is_admin") is True


def get_current_user_email():
    return session.get("user_email")


def send_email(to_email, subject, body):
    """Send a simple text email. If SMTP is not configured, just log."""
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASSWORD and SMTP_FROM_EMAIL):
        print("[email] SMTP not configured; skipping email.")
        return

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM_EMAIL
        msg["To"] = to_email
        msg.set_content(body)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"[email] sent to {to_email}")
    except Exception as e:
        print(f"[email] error: {e}")


def mark_user_paid(email, customer_id, subscription_id):
    """Set is_paid = true for the user and record a subscription row."""
    if not email:
        return

    supabase.table("app_users").update({"is_paid": True}).eq("email", email).execute()

    supabase.table("subscriptions").insert(
        {
            "user_email": email,
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": subscription_id,
            "is_active": True,
        }
    ).execute()


def get_active_subscription(email):
    """Return (db_row, stripe_subscription) for the user's active subscription."""
    if not email:
        return None, None

    rows = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_email", email)
        .eq("is_active", True)
        .order("id", desc=True)
        .limit(1)
        .execute()
        .data
    )

    if not rows:
        return None, None

    db_sub = rows[0]
    stripe_sub = None

    if stripe.api_key and db_sub.get("stripe_subscription_id"):
        try:
            stripe_sub = stripe.Subscription.retrieve(db_sub["stripe_subscription_id"])
        except Exception as e:
            print(f"[stripe] error loading subscription: {e}")

    return db_sub, stripe_sub

# -------------------------------------------------
# Routes – public
# -------------------------------------------------
@app.route("/")
def home():
    vendors = (
        supabase.table("vendors")
        .select("*")
        .order("id", desc=True)
        .limit(10)
        .execute()
        .data
        or []
    )
    tenders = (
        supabase.table("tenders")
        .select("*")
        .order("id", desc=True)
        .limit(10)
        .execute()
        .data
        or []
    )
    return render_template_string(
        HOME_TEMPLATE,
        vendors=vendors,
        tenders=tenders,
        current_user_email=get_current_user_email(),
        base_style=BASE_STYLE,
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

    vendors = (
        query.order("id", desc=True)
        .limit(100)
        .execute()
        .data
        or []
    )

    return render_template_string(
        VENDORS_PAGE_TEMPLATE,
        vendors=vendors,
        q=q,
        country=country,
        base_style=BASE_STYLE,
    )


@app.route("/vendors/<int:vendor_id>")
def vendor_detail(vendor_id: int):
    rows = (
        supabase.table("vendors")
        .select("*")
        .eq("id", vendor_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        flash("Vendor not found.", "error")
        return redirect(url_for("vendors_page"))

    vendor = rows[0]

    tenders = (
        supabase.table("tenders")
        .select("*")
        .ilike("operator", f"%{vendor.get('name', '')}%")
        .order("closing_date", desc=False)
        .limit(100)
        .execute()
        .data
        or []
    )

    return render_template_string(
        VENDOR_DETAIL_TEMPLATE,
        vendor=vendor,
        tenders=tenders,
        base_style=BASE_STYLE,
    )


@app.route("/tenders")
def tenders_page():
    q = request.args.get("q", "").strip()
    country = request.args.get("country", "").strip()
    operator = request.args.get("operator", "").strip()
    closing_from = request.args.get("closing_from", "").strip()
    closing_to = request.args.get("closing_to", "").strip()

    query = supabase.table("tenders").select("*")

    if country:
        query = query.eq("country", country)

    if q:
        like = f"%{q}%"
        query = query.ilike("title", like)

    if operator:
        like_op = f"%{operator}%"
        query = query.ilike("operator", like_op)

    if closing_from:
        query = query.gte("closing_date", closing_from)

    if closing_to:
        query = query.lte("closing_date", closing_to)

    if closing_from or closing_to:
        query = query.order("closing_date", desc=False)
    else:
        query = query.order("id", desc=True)

    tenders = (
        query
        .limit(100)
        .execute()
        .data
        or []
    )

    user_email = get_current_user_email()
    saved_ids = set()
    if user_email:
        rows = (
            supabase.table("user_saved_tenders")
            .select("tender_id")
            .eq("user_email", user_email)
            .execute()
            .data
            or []
        )
        saved_ids = {row["tender_id"] for row in rows}

    return render_template_string(
        TENDERS_PAGE_TEMPLATE,
        tenders=tenders,
        q=q,
        country=country,
        operator_filter=operator,
        closing_from=closing_from,
        closing_to=closing_to,
        current_user_email=user_email,
        saved_ids=saved_ids,
        base_style=BASE_STYLE,
    )


@app.route("/tenders/save/<int:tender_id>")
def save_tender(tender_id):
    user_email = get_current_user_email()
    if not user_email:
        flash("You must be logged in to save tenders.", "error")
        return redirect(url_for("login_user"))

    user_rows = (
        supabase.table("app_users")
        .select("is_paid")
        .eq("email", user_email)
        .limit(1)
        .execute()
        .data
    )
    is_paid = bool(user_rows and user_rows[0].get("is_paid"))
    if not is_paid:
        flash("You need an active subscription to save tenders.", "error")
        return redirect(url_for("subscribe"))

    existing = (
        supabase.table("user_saved_tenders")
        .select("id")
        .eq("user_email", user_email)
        .eq("tender_id", tender_id)
        .limit(1)
        .execute()
        .data
    )
    if existing:
        flash("Tender already saved.", "ok")
        return redirect(url_for("tenders_page"))

    supabase.table("user_saved_tenders").insert(
        {"user_email": user_email, "tender_id": tender_id}
    ).execute()

    tender_rows = (
        supabase.table("tenders")
        .select("*")
        .eq("id", tender_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if tender_rows:
        t = tender_rows[0]
        subject = f"Saved tender: {t.get('title', 'Tender')}"
        body_lines = [
            "You just saved this tender:",
            "",
            f"Title: {t.get('title')}",
            f"Country: {t.get('country')}",
            f"Source: {t.get('source')}",
        ]
        if t.get("closing_date"):
            body_lines.append(f"Closing date: {t.get('closing_date')}")
        if t.get("link"):
            body_lines.append(f"Link: {t.get('link')}")
        if t.get("description"):
            body_lines.append("")
            body_lines.append("Description:")
            body_lines.append(t.get("description"))

        body = "\n".join(body_lines)
        send_email(user_email, subject, body)

    flash("Tender saved. If email is configured, details were sent to you.", "ok")
    return redirect(url_for("tenders_page"))


@app.route("/tenders/unsave/<int:tender_id>")
def unsave_tender(tender_id):
    user_email = get_current_user_email()
    if not user_email:
        flash("You must be logged in to modify saved tenders.", "error")
        return redirect(url_for("login_user"))

    supabase.table("user_saved_tenders").delete().eq("user_email", user_email).eq(
        "tender_id", tender_id
    ).execute()
    flash("Tender removed from your saved list.", "ok")

    return redirect(request.referrer or url_for("tenders_page"))


@app.route("/my-tenders")
def my_tenders():
    user_email = get_current_user_email()
    if not user_email:
        flash("You must be logged in to see saved tenders.", "error")
        return redirect(url_for("login_user"))

    rows = (
        supabase.table("user_saved_tenders")
        .select("tender_id")
        .eq("user_email", user_email)
        .execute()
        .data
        or []
    )
    tender_ids = [row["tender_id"] for row in rows]

    if not tender_ids:
        tenders = []
    else:
        tenders = (
            supabase.table("tenders")
            .select("*")
            .in_("id", tender_ids)
            .order("id", desc=True)
            .execute()
            .data
            or []
        )

    return render_template_string(
        MY_TENDERS_TEMPLATE,
        tenders=tenders,
        current_user_email=user_email,
        base_style=BASE_STYLE,
    )


@app.route("/my-subscription")
def my_subscription():
    email = get_current_user_email()
    if not email:
        flash("You must be logged in to see subscription details.", "error")
        return redirect(url_for("login_user"))

    db_sub, stripe_sub = get_active_subscription(email)

    status = None
    current_period_end = None
    if stripe_sub:
        status = stripe_sub.get("status")
        cpe = stripe_sub.get("current_period_end")
        if cpe:
            current_period_end = time.strftime("%Y-%m-%d", time.gmtime(cpe))

    return render_template_string(
        MY_SUBSCRIPTION_TEMPLATE,
        base_style=BASE_STYLE,
        email=email,
        db_sub=db_sub,
        status=status,
        current_period_end=current_period_end,
    )

# -------------------------------------------------
# User auth (email/password)
# -------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register_user():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "error")
            return redirect(url_for("register_user"))

        existing = (
            supabase.table("app_users")
            .select("id")
            .eq("email", email)
            .limit(1)
            .execute()
            .data
        )
        if existing:
            flash("Email already registered.", "error")
            return redirect(url_for("register_user"))

        pw_hash = generate_password_hash(password)
        supabase.table("app_users").insert(
            {"email": email, "password_hash": pw_hash}
        ).execute()

        flash("Registration successful. You can now log in.", "ok")
        return redirect(url_for("login_user"))

    return render_template_string(REGISTER_TEMPLATE, base_style=BASE_STYLE)


@app.route("/login", methods=["GET", "POST"])
def login_user():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user_rows = (
            supabase.table("app_users")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
            .data
        )
        if not user_rows:
            flash("Invalid email or password.", "error")
            return redirect(url_for("login_user"))

        user = user_rows[0]
        if not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login_user"))

        session["user_email"] = email
        flash("Login successful.", "ok")
        return redirect(url_for("home"))

    return render_template_string(LOGIN_TEMPLATE, base_style=BASE_STYLE)


@app.route("/logout")
def logout_user():
    session.pop("user_email", None)
    flash("Logged out.", "ok")
    return redirect(url_for("home"))

# -------------------------------------------------
# Stripe subscription routes
# -------------------------------------------------
@app.route("/subscribe")
def subscribe():
    user_email = get_current_user_email()
    if not user_email:
        flash("You must be logged in to subscribe.", "error")
        return redirect(url_for("login_user"))

    if not stripe.api_key or not STRIPE_PRICE_ID:
        flash("Stripe is not configured yet.", "error")
        return redirect(url_for("home"))

    try:
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            customer_email=user_email,
            success_url=url_for("subscribe_success", _external=True),
            cancel_url=url_for("subscribe_cancel", _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        print(f"[stripe] error: {e}")
        flash("Could not start checkout. Please try again later.", "error")
        return redirect(url_for("home"))


@app.route("/subscribe/success")
def subscribe_success():
    return render_template_string(
        """
        <!DOCTYPE html>
        <html>
        <head>
          <title>Subscription Successful</title>
          {{ base_style|safe }}
        </head>
        <body>
          <nav>
            <a href="{{ url_for('home') }}">Home</a>
            <a href="{{ url_for('tenders_page') }}">Tenders</a>
            <a href="{{ url_for('vendors_page') }}">Vendors</a>
            <a href="{{ url_for('my_tenders') }}">My Tenders</a>
            <a href="{{ url_for('my_subscription') }}">My Subscription</a>
          </nav>
          <div class="page">
            <h1>Subscription Successful</h1>
            <p>Thank you. Your payment was successful.</p>
            <p>You can now continue browsing and saving tenders.</p>
          </div>
        </body>
        </html>
        """,
        base_style=BASE_STYLE,
    )


@app.route("/subscribe/cancel")
def subscribe_cancel():
    return render_template_string(
        """
        <!DOCTYPE html>
        <html>
        <head>
          <title>Subscription Cancelled</title>
          {{ base_style|safe }}
        </head>
        <body>
          <nav>
            <a href="{{ url_for('home') }}">Home</a>
            <a href="{{ url_for('tenders_page') }}">Tenders</a>
            <a href="{{ url_for('vendors_page') }}">Vendors</a>
            <a href="{{ url_for('my_tenders') }}">My Tenders</a>
            <a href="{{ url_for('my_subscription') }}">My Subscription</a>
          </nav>
          <div class="page">
            <h1>Subscription Cancelled</h1>
            <p>You cancelled the payment. No charge was made.</p>
          </div>
        </body>
        </html>
        """,
        base_style=BASE_STYLE,
    )


@app.route("/billing-portal")
def billing_portal():
    email = get_current_user_email()
    if not email:
        flash("You must be logged in to manage billing.", "error")
        return redirect(url_for("login_user"))

    db_sub, _ = get_active_subscription(email)
    customer_id = db_sub.get("stripe_customer_id") if db_sub else None

    if not (stripe.api_key and customer_id):
        flash("No active subscription to manage.", "error")
        return redirect(url_for("my_subscription"))

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=url_for("my_subscription", _external=True),
        )
        return redirect(portal_session.url, code=303)
    except Exception as e:
        print(f"[stripe] error creating billing portal session: {e}")
        flash("Could not open billing portal. Please try again later.", "error")
        return redirect(url_for("my_subscription"))


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    if not STRIPE_WEBHOOK_SECRET:
        return "Webhook secret not set", 400

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        email = session_obj.get("customer_email")
        customer_id = session_obj.get("customer")
        subscription_id = session_obj.get("subscription")
        print(f"[stripe] checkout completed for {email}")
        mark_user_paid(email, customer_id, subscription_id)

    return "OK", 200

# -------------------------------------------------
# Admin auth + views
# -------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username", "")
        pw = request.form.get("password", "")
        if user == ADMIN_USERNAME and pw == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Admin login successful", "ok")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid admin credentials", "error")
    return render_template_string(ADMIN_LOGIN_TEMPLATE, base_style=BASE_STYLE)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Admin logged out", "ok")
    return redirect(url_for("home"))


@app.route("/admin")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("admin_login"))
    return render_template_string(ADMIN_DASH_TEMPLATE, base_style=BASE_STYLE)


@app.route("/admin/users")
def admin_list_users():
    if not admin_required():
        return redirect(url_for("admin_login"))

    users = (
        supabase.table("app_users")
        .select("*")
        .order("id", desc=True)
        .execute()
        .data
        or []
    )
    return render_template_string(
        ADMIN_USERS_TEMPLATE,
        users=users,
        base_style=BASE_STYLE,
    )


@app.route("/admin/subscriptions")
def admin_list_subscriptions():
    if not admin_required():
        return redirect(url_for("admin_login"))

    subs = (
        supabase.table("subscriptions")
        .select("*")
        .order("id", desc=True)
        .execute()
        .data
        or []
    )
    return render_template_string(
        ADMIN_SUBSCRIPTIONS_TEMPLATE,
        subs=subs,
        base_style=BASE_STYLE,
    )


@app.route("/admin/saved-tenders")
def admin_saved_tenders():
    if not admin_required():
        return redirect(url_for("admin_login"))

    rows = (
        supabase.table("user_saved_tenders")
        .select("*")
        .order("id", desc=True)
        .limit(500)
        .execute()
        .data
        or []
    )
    return render_template_string(
        ADMIN_SAVED_TENDERS_TEMPLATE,
        rows=rows,
        base_style=BASE_STYLE,
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

    data = {
        "title": request.form.get("title"),
        "country": request.form.get("country"),
        "operator": request.form.get("operator"),
        "source": request.form.get("source"),
        "closing_date": request.form.get("closing_date") or None,
        "link": request.form.get("link"),
        "description": request.form.get("description"),
    }
    supabase.table("tenders").insert(data).execute()
    flash("Tender added", "ok")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/run_scrapers", methods=["POST"])
def admin_run_scrapers():
    if not admin_required():
        return redirect(url_for("admin_login"))

    inserted = run_all_scrapers(supabase)
    flash(f"Scrapers finished. Inserted {inserted} new tenders.", "ok")
    return redirect(url_for("admin_dashboard"))

# -------------------------------------------------
# Background auto-scrape loop (optional)
# -------------------------------------------------
def auto_scrape_loop():
    """Background loop that runs all scrapers every 30 minutes."""
    while True:
        try:
            print("[auto-scrape] Running all scrapers...")
            inserted = run_all_scrapers(supabase)
            print(f"[auto-scrape] Inserted {inserted} tender rows.")
        except Exception as e:
            print(f"[auto-scrape] Error: {e}")
        time.sleep(30 * 60)

# -------------------------------------------------
# Main
# -------------------------------------------------
if __name__ == "__main__":
    print("Running Flask app on http://127.0.0.1:5000")

    # Background auto-scrape disabled for now.
    # If you want it, uncomment the two lines below.
    # t = threading.Thread(target=auto_scrape_loop, daemon=True)
    # t.start()

    app.run(debug=True)
