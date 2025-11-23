import os
import datetime as dt
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort,
)
from werkzeug.security import generate_password_hash, check_password_hash

from .db import get_supabase_client
import stripe


# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------
app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# Stripe (optional – used by /subscribe)
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
app.config["STRIPE_PRICE_ID"] = os.environ.get("STRIPE_PRICE_ID")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def get_current_user():
    """Return the logged-in user record from Supabase, or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None

    supabase = get_supabase_client()
    resp = (
        supabase.table("app_users")
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )
    return resp.data


def is_user_subscribed(user: dict | None) -> bool:
    """
    Decide if a user has an active subscription.

    Your SQL migration added `is_paid boolean not null default false`
    on `public.app_users`, so we use that as the subscription flag.
    """
    if not user:
        return False
    return bool(user.get("is_paid"))


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)

    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            abort(403)
        return f(*args, **kwargs)

    return wrapper


def subscription_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Admin bypass: can see everything regardless of subscription
        if session.get("is_admin"):
            return f(*args, **kwargs)

        user = get_current_user()
        if not user:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login", next=request.path))

        if not is_user_subscribed(user):
            flash("This page is only available to subscribers.", "warning")
            return redirect(url_for("subscribe"))

        return f(*args, **kwargs)

    return wrapper


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    user = get_current_user()
    return render_template("index.html", user=user)


# ---------------- Auth ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    supabase = get_supabase_client()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()

        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(url_for("register"))

        existing = (
            supabase.table("app_users")
            .select("id")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if existing.data:
            flash("An account with that email already exists.", "warning")
            return redirect(url_for("login"))

        hashed = generate_password_hash(password)

        resp = (
            supabase.table("app_users")
            .insert(
                {
                    "email": email,
                    "password_hash": hashed,
                    "created_at": dt.datetime.utcnow().isoformat(),
                    # is_paid will default to false in the DB
                }
            )
            .execute()
        )
        user = resp.data[0]
        session["user_id"] = user["id"]
        session["is_admin"] = False

        flash("Registration successful. You are now logged in.", "success")
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    supabase = get_supabase_client()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        resp = (
            supabase.table("app_users")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if not resp.data:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

        user = resp.data[0]
        if not check_password_hash(user.get("password_hash", ""), password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        # you don't currently have an is_admin column on app_users
        session["is_admin"] = False

        flash("Logged in successfully.", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ---------------- Tenders (10 free, rest gated via subscription) ----------------
@app.route("/tenders", endpoint="tenders_page")
def tenders_page():
    supabase = get_supabase_client()
    user = get_current_user()
    subscribed = is_user_subscribed(user)

    # Admin can always see full tender list (no 10-tender limit)
    if session.get("is_admin"):
        subscribed = True

    page = request.args.get("page", default=1, type=int)
    if page < 1:
        page = 1

    FREE_LIMIT = 10
    SUBSCRIBED_PAGE_SIZE = 20

    if not subscribed:
        # Free users: force page 1, fetch 11 to detect "has_more"
        page = 1
        resp = (
            supabase.table("tenders")
            .select("*")
            .order("closing_date", desc=False)
            .range(0, FREE_LIMIT)  # 0..10 inclusive (11 rows)
            .execute()
        )
        rows = resp.data or []
        visible_tenders = rows[:FREE_LIMIT]
        has_more = len(rows) > FREE_LIMIT

        return render_template(
            "tenders.html",
            tenders=visible_tenders,
            user=user,
            is_subscribed=subscribed,
            has_more=has_more,
            current_page=page,
            show_pagination=False,
        )

    # Subscribed users: normal pagination
    start = (page - 1) * SUBSCRIBED_PAGE_SIZE
    end = start + SUBSCRIBED_PAGE_SIZE - 1

    resp = (
        supabase.table("tenders")
        .select("*")
        .order("closing_date", desc=False)
        .range(start, end)
        .execute()
    )
    visible_tenders = resp.data or []
    has_more = len(visible_tenders) == SUBSCRIBED_PAGE_SIZE

    return render_template(
        "tenders.html",
        tenders=visible_tenders,
        user=user,
        is_subscribed=subscribed,
        has_more=has_more,
        current_page=page,
        show_pagination=True,
    )


# ---------------- Vendors (subscribers only) ----------------
@app.route("/vendors", endpoint="vendors_page")
@subscription_required
def vendors_page():
    supabase = get_supabase_client()
    user = get_current_user()

    resp = (
        supabase.table("vendors")
        .select("*")
        .order("name", desc=False)
        .execute()
    )
    vendors_data = resp.data or []

    return render_template("vendors.html", vendors=vendors_data, user=user)


@app.route("/vendor/<int:vendor_id>")
@subscription_required
def vendor_detail(vendor_id: int):
    """
    Show details for a single vendor and its tenders.
    Only visible to subscribed users.
    """
    supabase = get_supabase_client()
    user = get_current_user()

    # Get vendor info
    vendor_resp = (
        supabase.table("vendors")
        .select("*")
        .eq("id", vendor_id)
        .single()
        .execute()
    )
    vendor = vendor_resp.data
    if not vendor:
        flash("Vendor not found.", "warning")
        return redirect(url_for("vendors_page"))

    # Get this vendor's tenders
    tenders_resp = (
        supabase.table("tenders")
        .select("*")
        .eq("vendor_id", vendor_id)
        .order("closing_date", desc=False)
        .execute()
    )
    tenders = tenders_resp.data or []

    return render_template(
        "vendor_detail.html",
        vendor=vendor,
        tenders=tenders,
        user=user,
    )


# ---------------- Saved tenders (per user, via user_email) ----------------
@app.route("/my-tenders")
@login_required
def my_tenders():
    supabase = get_supabase_client()
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    # user_saved_tenders uses user_email, not user_id
    user_email = user["email"]

    # 1) Get the saved tender_ids for this email
    saved_resp = (
        supabase.table("user_saved_tenders")
        .select("tender_id")
        .eq("user_email", user_email)
        .execute()
    )
    saved_rows = saved_resp.data or []

    tender_ids = [row["tender_id"] for row in saved_rows if row.get("tender_id")]

    # 2) Fetch the corresponding tenders
    tenders = []
    if tender_ids:
        tenders_resp = (
            supabase.table("tenders")
            .select("*")
            .in_("id", tender_ids)
            .execute()
        )
        tenders = tenders_resp.data or []

    return render_template(
        "my_tenders.html",
        tenders=tenders,
        user=user,
    )


# ---------------- Subscription (Stripe shell) ----------------
@app.route("/subscribe")
@login_required
def subscribe():
    """
    Start a Stripe Checkout session for the current user.

    If Stripe is not configured, just show a message.
    """
    user = get_current_user()
    if not stripe.api_key or not app.config.get("STRIPE_PRICE_ID"):
        flash(
            "Subscription is not configured yet. Please contact support.",
            "warning",
        )
        return redirect(url_for("tenders_page"))

    price_id = app.config["STRIPE_PRICE_ID"]
    success_url = url_for("subscribe_success", _external=True)
    cancel_url = url_for("subscribe_cancel", _external=True)

    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        customer_email=user.get("email"),
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
    )

    return redirect(checkout_session.url, code=303)


@app.route("/subscribe/success")
@login_required
def subscribe_success():
    flash("Thank you for subscribing! Your access will be updated shortly.", "success")
    return redirect(url_for("tenders_page"))


@app.route("/subscribe/cancel")
@login_required
def subscribe_cancel():
    flash("Subscription checkout was cancelled.", "info")
    return redirect(url_for("tenders_page"))


# ---------------- Admin ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        admin_user = os.environ.get("ADMIN_USERNAME")
        admin_pass = os.environ.get("ADMIN_PASSWORD")

        if username == admin_user and password == admin_pass:
            session["is_admin"] = True
            flash("Admin login successful.", "success")
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials.", "danger")
        return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session["is_admin"] = False
    flash("Admin logged out.", "info")
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    supabase = get_supabase_client()
    tenders_resp = (
        supabase.table("tenders")
        .select("*")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    vendors_resp = (
        supabase.table("vendors")
        .select("*")
        .order("name", desc=False)
        .limit(20)
        .execute()
    )
    return render_template(
        "admin_dashboard.html",
        tenders=tenders_resp.data or [],
        vendors=vendors_resp.data or [],
    )


@app.route("/admin/add-vendor", methods=["GET", "POST"])
@admin_required
def admin_add_vendor():
    supabase = get_supabase_client()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        country = request.form.get("country", "").strip()
        website = request.form.get("website", "").strip()

        if not name or not country:
            flash("Vendor name and country are required.", "danger")
            return redirect(url_for("admin_add_vendor"))

        supabase.table("vendors").insert(
            {
                "name": name,
                "country": country,
                "website": website or None,
                "source": "Manual",
                "status": "active",
                "created_at": dt.datetime.utcnow().isoformat(),
            }
        ).execute()

        flash("Vendor added.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_add_vendor.html")


@app.route("/admin/add-tender", methods=["GET", "POST"])
@admin_required
def admin_add_tender():
    supabase = get_supabase_client()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        country = request.form.get("country", "").strip()
        operator = request.form.get("operator", "").strip()
        closing_date = request.form.get("closing_date", "").strip()
        link = request.form.get("link", "").strip()

        if not title:
            flash("Tender title is required.", "danger")
            return redirect(url_for("admin_add_tender"))

        payload = {
            "title": title,
            "country": country or None,
            "operator": operator or None,
            "link": link or None,
            "created_at": dt.datetime.utcnow().isoformat(),
            "source": "Manual",
            "is_active": True,
        }
        if closing_date:
            payload["closing_date"] = closing_date

        supabase.table("tenders").insert(payload).execute()

        flash("Tender added.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_add_tender.html")


@app.route("/admin/sync-vendors-from-tenders", methods=["POST"])
@admin_required
def admin_sync_vendors_from_tenders():
    """
    Create/update vendors based on distinct operators found in tenders,
    and set tenders.vendor_id for matching vendors.

    Steps:
    - Fetch all tenders (id, operator, country).
    - For each distinct (operator, country):
        * Ensure there is a vendors row.
    - For each tender with an operator:
        * Set vendor_id to the matching vendors.id (if found).
    """
    supabase = get_supabase_client()

    # 1) Fetch all tenders fields we care about
    resp = (
        supabase.table("tenders")
        .select("id, operator, country")
        .execute()
    )
    tender_rows = resp.data or []

    # Build unique (name, country) set from tenders
    vendor_keys: set[tuple[str, str]] = set()
    for row in tender_rows:
        name = (row.get("operator") or "").strip()
        country = (row.get("country") or "").strip()
        if not name:
            continue
        if not country:
            country = "Unknown"
        vendor_keys.add((name, country))

    # 2) Ensure each key exists in vendors
    inserted = 0
    vendor_map: dict[tuple[str, str], int] = {}

    for name, country in vendor_keys:
        # Check existing
        existing = (
            supabase.table("vendors")
            .select("id")
            .eq("name", name)
            .eq("country", country)
            .limit(1)
            .execute()
        )

        if existing.data:
            vendor_id = existing.data[0]["id"]
        else:
            # Insert new vendor
            payload = {
                "name": name,
                "country": country,
                "source": "From tenders",
                "status": "active",
            }
            ins = supabase.table("vendors").insert(payload).execute()
            vendor_id = ins.data[0]["id"]
            inserted += 1

        vendor_map[(name, country)] = vendor_id

    # 3) Update tenders.vendor_id based on operator+country
    updated = 0
    for row in tender_rows:
        tender_id = row["id"]
        name = (row.get("operator") or "").strip()
        country = (row.get("country") or "").strip() or "Unknown"
        if not name:
            continue

        key = (name, country)
        vendor_id = vendor_map.get(key)
        if not vendor_id:
            continue

        supabase.table("tenders").update(
            {"vendor_id": vendor_id}
        ).eq("id", tender_id).execute()
        updated += 1

    flash(
        f"Vendor sync complete. Inserted {inserted} vendors, updated vendor_id on {updated} tenders.",
        "success",
    )
    return redirect(url_for("admin_dashboard"))
