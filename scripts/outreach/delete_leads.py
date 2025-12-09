#!/usr/bin/env python3
"""One-time script to delete all harvested and qualified leads from MongoDB."""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

def main():
    """Delete all harvested and qualified leads."""
    mongodb_uri = os.environ.get("MONGODB_URI")
    if not mongodb_uri:
        print("ERROR: MONGODB_URI environment variable not set")
        print("Make sure you have a .env file with MONGODB_URI=mongodb+srv://...")
        sys.exit(1)
    
    client = MongoClient(mongodb_uri)
    db = client.eulaiq_outreach
    
    # Count before deletion
    harvested_count = db.leads.count_documents({"status": "harvested"})
    qualified_count = db.leads.count_documents({"status": "qualified"})
    
    print("=" * 50)
    print("LEAD DELETION SUMMARY")
    print("=" * 50)
    print(f"\nBefore deletion:")
    print(f"  Harvested leads: {harvested_count}")
    print(f"  Qualified leads: {qualified_count}")
    print(f"  Total to delete: {harvested_count + qualified_count}")
    
    if harvested_count + qualified_count == 0:
        print("\nNo leads to delete.")
        client.close()
        return
    
    # Confirm deletion
    confirm = input("\nAre you sure you want to delete these leads? (yes/no): ")
    if confirm.lower() != "yes":
        print("Cancelled.")
        client.close()
        return
    
    # Delete harvested and qualified leads
    result = db.leads.delete_many({"status": {"$in": ["harvested", "qualified"]}})
    print(f"\n✓ Deleted {result.deleted_count} leads")
    
    # Show remaining
    remaining = db.leads.count_documents({})
    approved_count = db.leads.count_documents({"status": "approved"})
    disqualified_count = db.leads.count_documents({"status": "disqualified"})
    
    print(f"\nRemaining leads: {remaining}")
    print(f"  Approved: {approved_count}")
    print(f"  Disqualified: {disqualified_count}")
    print("=" * 50)
    
    client.close()

if __name__ == "__main__":
    main()
