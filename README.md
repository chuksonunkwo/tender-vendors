# tender-vendors

A minimal Flask application that scrapes public tender listings, stores results in Supabase, and provides a simple UI for vendors and saved tenders. This repository contains an example development app and scraper stubs so developers can run and extend it locally.

**Quick Start**

- **Requirements:** Python 3.10+ (virtualenv recommended), Git.
- **Local env file:** copy `./.env.example` to `.env` or use `secrets.env` and fill in your keys. Do NOT commit secrets.

**Setup (Windows / PowerShell)**

```powershell
# from project root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Environment variables**

- `SUPABASE_URL` and `SUPABASE_ANON_KEY` — required for Supabase features.
- `FLASK_SECRET_KEY` — Flask session secret (development only).
- `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET` — optional for Stripe payments.
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` — optional for email notifications.

Place values in `secrets.env` (local only) or export them into your shell before starting the app.

**Run (development)**

```powershell
# load local secrets into environment (example)
Get-Content .\secrets.env | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object { $kv = $_ -split '=', 2; Set-Item -Path Env:$($kv[0].Trim()) -Value $kv[1] }
python -m tender_app.app
```

For a stable local run on Windows use Waitress:

```powershell
.\.venv\Scripts\waitress-serve --port=5000 tender_app.app:app
```

**Project structure**

- `tender_app/app.py` — main Flask application and routes
- `tender_app/scrapers/` — scraper modules and `run_all` orchestration
- `.env.example` — sanitized env placeholders (do not commit real secrets)

**Notes & Troubleshooting**

- If GitHub push-protection blocks a push, remove secrets from committed files and re-push.
- Stripe and SMTP integrations require valid credentials — otherwise the app will log authentication errors when those features are exercised.
- Scrapers may hit network errors; add retry/backoff logic for production usage.

**Contributing**

Open a PR for changes. Keep commits small, and never include real credentials in commits.

**License**

No license file is included. Add one if you plan to publish this code.
# tender_app

Minimal Flask app that optionally connects to Supabase.

Quick start (Windows PowerShell):

```powershell
# create venv (if you want to do this manually)
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# run the app
.\.venv\Scripts\python tender_app\app.py
```

Environment variables expected (see `.env.example`): `SUPABASE_URL`, `SUPABASE_KEY`.
