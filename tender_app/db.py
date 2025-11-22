# tender_app/db.py

import os
from typing import Optional

from supabase import create_client, Client  # make sure supabase-py is installed
from dotenv import load_dotenv

# Load .env from project root for CLI runs (run_all, etc.)
load_dotenv()

_supabase: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Return a singleton Supabase client.

    Tries SERVICE_ROLE first (good for upserts); falls back to ANON for dev.
    """
    global _supabase
    if _supabase is not None:
        return _supabase

    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set in environment or .env")

    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
    )
    if not key:
        raise RuntimeError(
            "Neither SUPABASE_SERVICE_ROLE_KEY nor SUPABASE_ANON_KEY is set."
        )

    _supabase = create_client(url, key)
    return _supabase
