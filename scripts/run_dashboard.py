"""Run the OMNI Retail API + dashboard.

Usage:
    python scripts/run_dashboard.py
    -> http://127.0.0.1:8000  (dashboard)
    -> http://127.0.0.1:8000/docs  (interactive API docs)

Run scripts/seed_db.py first if omni_retail.db doesn't exist yet.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("omni_retail.api.app:app", host="127.0.0.1", port=8000, reload=True)
