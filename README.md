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
