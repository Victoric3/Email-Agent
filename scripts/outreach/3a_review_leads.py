#!/usr/bin/env python3
"""
Step 3a: Manual Lead Review.

Export qualified leads for manual review. You will:
1. Research creator emails
2. View their channel to decide if they're a good fit
3. Approve or disqualify each lead
4. Import back with emails and decisions

This combines email collection with manual qualification in one step.
"""
import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_db, LeadStatus

# Output directory for review files
REVIEW_DIR = Path(__file__).parent.parent.parent / "review_queue"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def export_for_review(limit=None):
    """
    Export qualified leads to JSON for manual review.
    Creates a file with lead info you'll fill in.
    """
    db = get_db()
    
    # Get leads that passed LLM qualification
    leads = db.get_leads_by_status(LeadStatus.QUALIFIED)
    
    if not leads:
        print("No qualified leads pending review.")
        return None
    
    if limit:
        leads = leads[:limit]
    
    # Build export data
    export_items = []
    for lead in leads:
        export_items.append({
            "channel_id": lead["channel_id"],
            "channel_name": lead["channel_name"],
            "creator_name": lead.get("creator_name", lead["channel_name"]),
            "video_title": lead.get("video_title", ""),
            "video_url": lead.get("video_url", ""),
            "video_id": lead.get("video_id", ""),
            "channel_url": f"https://youtube.com/channel/{lead['channel_id']}",
            "icp_score": lead.get("icp_score", 0),
            "icp_reason": lead.get("icp_reason", ""),
            "subscriber_count": lead.get("subscriber_count", "unknown"),
            # Fields for you to fill in:
            "email": lead.get("email", ""),  # ADD EMAIL HERE
            "decision": "",  # "approve" or "disqualify"
            "disqualify_reason": "",  # Why rejected (optional)
            "notes": ""  # Any notes
        })
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"review_queue_{timestamp}.json"
    filepath = REVIEW_DIR / filename
    
    export_data = {
        "exported_at": timestamp,
        "count": len(export_items),
        "instructions": {
            "email": "Add creator's email address",
            "decision": "Set to 'approve' or 'disqualify'",
            "disqualify_reason": "If disqualifying, explain why",
            "notes": "Any additional notes"
        },
        "leads": export_items
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Exported {len(export_items)} leads for review")
    print(f"📁 File: {filepath}")
    print("\n📝 Instructions:")
    print("  1. Open the JSON file")
    print("  2. For each lead:")
    print("     - Visit channel_url to evaluate the creator")
    print("     - Find their email (About page, socials, etc.)")
    print("     - Set 'email' field with their email")
    print("     - Set 'decision' to 'approve' or 'disqualify'")
    print("  3. Run: python 3a_review_leads.py --import <filename>")
    
    return filepath


def import_reviews(filepath):
    """
    Import reviewed leads from JSON file.
    Updates database with emails and approval decisions.
    """
    db = get_db()
    
    # Handle relative paths
    if not os.path.isabs(filepath):
        filepath = REVIEW_DIR / filepath
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    leads = data.get("leads", [])
    
    approved = 0
    disqualified = 0
    skipped = 0
    missing_email = 0
    
    for item in leads:
        channel_id = item["channel_id"]
        decision = item.get("decision", "").lower().strip()
        email = item.get("email", "").strip()
        
        if not decision:
            skipped += 1
            continue
        
        if decision == "approve":
            if not email:
                print(f"⚠️ {item['creator_name']}: Approved but no email - skipping")
                missing_email += 1
                continue
            
            db.approve_for_video(channel_id, email)
            if item.get("notes"):
                db.add_note(channel_id, item["notes"])
            approved += 1
            print(f"✅ Approved: {item['creator_name']} ({email})")
            
        elif decision == "disqualify":
            reason = item.get("disqualify_reason", "Manual review rejection")
            db.disqualify_lead(channel_id, reason)
            disqualified += 1
            print(f"❌ Disqualified: {item['creator_name']} - {reason}")
        
        else:
            print(f"⚠️ Unknown decision '{decision}' for {item['creator_name']} - skipping")
            skipped += 1
    
    print("\n" + "="*50)
    print("Import Summary:")
    print(f"  ✅ Approved: {approved}")
    print(f"  ❌ Disqualified: {disqualified}")
    print(f"  ⚠️ Skipped: {skipped}")
    if missing_email:
        print(f"  📧 Missing email: {missing_email}")
    
    # Show next steps
    if approved > 0:
        print("\n📌 Next Step:")
        print("  Run: python 3b_generate_videos.py")
        print("  This will generate 2 video options for each approved lead.")


def show_pending_review():
    """Show leads currently pending manual review."""
    db = get_db()
    leads = db.get_leads_by_status(LeadStatus.QUALIFIED)
    
    if not leads:
        print("No leads pending review.")
        return
    
    table_data = []
    for lead in leads:
        table_data.append([
            lead["channel_id"][:12] + "...",
            lead.get("creator_name", lead["channel_name"])[:20],
            lead.get("icp_score", "-"),
            lead.get("email", "-")[:25] if lead.get("email") else "NEEDED",
            lead.get("video_title", "")[:30] + "..."
        ])
    
    headers = ["Channel ID", "Creator", "Score", "Email", "Video"]
    print(tabulate(table_data, headers=headers, tablefmt="simple"))
    print(f"\nTotal: {len(leads)} leads pending review")


def interactive_review():
    """
    Interactive mode: Review leads one by one in terminal.
    Quick mode for when you don't want to edit JSON.
    """
    db = get_db()
    leads = db.get_leads_by_status(LeadStatus.QUALIFIED)
    
    if not leads:
        print("No leads pending review.")
        return
    
    print(f"\n📋 Interactive Review Mode - {len(leads)} leads\n")
    print("Commands: [a]pprove, [d]isqualify, [s]kip, [q]uit\n")
    
    approved = 0
    disqualified = 0
    
    for i, lead in enumerate(leads, 1):
        print("="*60)
        print(f"[{i}/{len(leads)}] {lead.get('creator_name', lead['channel_name'])}")
        print(f"  Channel: https://youtube.com/channel/{lead['channel_id']}")
        print(f"  Video: {lead.get('video_title', 'N/A')}")
        print(f"  URL: {lead.get('video_url', 'N/A')}")
        print(f"  Score: {lead.get('icp_score', '-')}/22")
        print(f"  Reason: {lead.get('icp_reason', 'N/A')}")
        print(f"  Current Email: {lead.get('email', 'NOT SET')}")
        print()
        
        while True:
            action = input("Action [a/d/s/q]: ").lower().strip()
            
            if action == 'q':
                print("\nExiting review mode.")
                print(f"  Approved: {approved}, Disqualified: {disqualified}")
                return
            
            if action == 's':
                print("  ⏭️ Skipped")
                break
            
            if action == 'a':
                email = input("  Email: ").strip()
                if not email:
                    print("  ⚠️ Email required for approval")
                    continue
                db.approve_for_video(lead["channel_id"], email)
                approved += 1
                print(f"  ✅ Approved with email: {email}")
                break
            
            if action == 'd':
                reason = input("  Reason (optional): ").strip() or "Manual review rejection"
                db.disqualify_lead(lead["channel_id"], reason)
                disqualified += 1
                print(f"  ❌ Disqualified")
                break
            
            print("  Invalid action. Use: a=approve, d=disqualify, s=skip, q=quit")
    
    print("\n" + "="*50)
    print("Review Complete!")
    print(f"  ✅ Approved: {approved}")
    print(f"  ❌ Disqualified: {disqualified}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual lead review before video generation")
    parser.add_argument("--export", action="store_true", help="Export qualified leads for review")
    parser.add_argument("--import", dest="import_file", metavar="FILE", help="Import reviewed leads from JSON")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive review mode")
    parser.add_argument("--list", action="store_true", help="List leads pending review")
    parser.add_argument("--limit", type=int, help="Limit number of leads to export")
    
    args = parser.parse_args()
    
    if args.export:
        export_for_review(limit=args.limit)
    elif args.import_file:
        import_reviews(args.import_file)
    elif args.interactive:
        interactive_review()
    elif args.list:
        show_pending_review()
    else:
        parser.print_help()
        print("\n📌 Quick Start:")
        print("  1. python 3a_review_leads.py --export")
        print("  2. Fill in the JSON file with emails and decisions")
        print("  3. python 3a_review_leads.py --import <file>")
        print("\n  Or use interactive mode:")
        print("  python 3a_review_leads.py --interactive")
