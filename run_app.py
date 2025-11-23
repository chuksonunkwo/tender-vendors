# run_app.py - Simple script to run the app with environment loaded
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('secret.env')

# Now import and run the app
from tender_app.app import app

if __name__ == '__main__':
    print("Starting Flask development server on http://127.0.0.1:5000...")
    print(f"SUPABASE_URL loaded: {bool(os.getenv('SUPABASE_URL'))}")
    print(f"SUPABASE_ANON_KEY loaded: {bool(os.getenv('SUPABASE_ANON_KEY'))}")
    app.run(debug=True, port=5000)
