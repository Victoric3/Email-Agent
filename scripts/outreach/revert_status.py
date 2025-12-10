
import sys
from pathlib import Path

# Add parent directory to path to import db_client
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_client import get_db, LeadStatus

def revert_status():
    db = get_db()
    result = db.leads.update_many(
        {"status": "asset_generating"},
        {"$set": {"status": "approved"}}
    )
    print(f"Reverted {result.modified_count} leads from 'asset_generating' to 'approved'.")

if __name__ == "__main__":
    revert_status()
