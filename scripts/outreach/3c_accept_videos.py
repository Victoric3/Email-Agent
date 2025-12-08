#!/usr/bin/env python3
"""
Step 3c: Accept/Review Generated Videos.

For each lead with 2 generated videos:
1. Show both video URLs for comparison
2. Select which one is better (A or B)
3. Option to regenerate if neither is good
4. Option to provide a custom URL
5. Option to change the source video and regenerate

After approval, leads move to upload queue.
"""
import json
import os
import sys
import argparse
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_db, LeadStatus

# Review queue directory
REVIEW_DIR = Path(__file__).parent.parent.parent / "video_review"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def export_for_review(limit=None):
    """
    Export videos pending review to JSON.
    You can fill in selections and import back.
    """
    db = get_db()
    leads = db.get_leads_for_video_review()
    
    if not leads:
        print("No videos pending review.")
        return None
    
    if limit:
        leads = leads[:limit]
    
    export_items = []
    for lead in leads:
        video_a = lead.get("video_a", {})
        video_b = lead.get("video_b", {})
        
        export_items.append({
            "channel_id": lead["channel_id"],
            "creator_name": lead.get("creator_name", lead.get("channel_name", "")),
            "video_title": lead.get("video_title", ""),
            "source_video_url": lead.get("video_url", ""),
            "email": lead.get("email", ""),
            
            # Generated videos
            "video_a_url": video_a.get("branded_player_url", ""),
            "video_b_url": video_b.get("branded_player_url", ""),
            
            # Selection fields - fill these in
            "selection": "",  # "a", "b", "custom", or "regenerate"
            "custom_url": "",  # If selection is "custom"
            "new_source_video_url": "",  # If you want to regenerate from different source
            "notes": ""
        })
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"video_review_{timestamp}.json"
    filepath = REVIEW_DIR / filename
    
    export_data = {
        "exported_at": timestamp,
        "count": len(export_items),
        "instructions": {
            "selection": "Set to 'a', 'b', 'custom', 'regenerate', or 'reject'",
            "custom_url": "If selection is 'custom', provide your own EulaIQ player URL",
            "new_source_video_url": "If 'regenerate', optionally specify a different source video",
            "notes": "Any notes about the selection"
        },
        "leads": export_items
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Exported {len(export_items)} videos for review")
    print(f"📁 File: {filepath}")
    print("\n📝 Instructions:")
    print("  1. Open both video URLs in browser")
    print("  2. Set 'selection' to 'a' or 'b' (or 'custom'/'regenerate')")
    print("  3. Run: python 3c_accept_videos.py --import <filename>")
    
    return filepath


def import_selections(filepath):
    """
    Import video selections from JSON.
    """
    db = get_db()
    
    if not os.path.isabs(filepath):
        filepath = REVIEW_DIR / filepath
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    leads = data.get("leads", [])
    
    approved = 0
    regenerate = 0
    rejected = 0
    skipped = 0
    
    for item in leads:
        channel_id = item["channel_id"]
        selection = item.get("selection", "").lower().strip()
        
        if not selection:
            skipped += 1
            continue
        
        if selection == 'a':
            db.select_video(channel_id, 'a')
            approved += 1
            print(f"✅ {item['creator_name']}: Selected Video A")
            
        elif selection == 'b':
            db.select_video(channel_id, 'b')
            approved += 1
            print(f"✅ {item['creator_name']}: Selected Video B")
            
        elif selection == 'custom':
            custom_url = item.get("custom_url", "").strip()
            if not custom_url:
                print(f"⚠️ {item['creator_name']}: 'custom' selected but no custom_url provided")
                skipped += 1
                continue
            db.set_custom_video_url(channel_id, custom_url)
            approved += 1
            print(f"✅ {item['creator_name']}: Using custom URL")
            
        elif selection == 'regenerate':
            # Mark for regeneration (back to APPROVED status)
            new_url = item.get("new_source_video_url", "").strip()
            updates = {"status": LeadStatus.APPROVED}
            if new_url:
                updates["video_url"] = new_url
                print(f"🔄 {item['creator_name']}: Marked for regeneration with new source")
            else:
                print(f"🔄 {item['creator_name']}: Marked for regeneration")
            db.update_lead_by_channel(channel_id, updates)
            regenerate += 1
            
        elif selection == 'reject':
            db.disqualify_lead(channel_id, "Rejected at video review stage")
            rejected += 1
            print(f"❌ {item['creator_name']}: Rejected")
            
        else:
            print(f"⚠️ Unknown selection '{selection}' for {item['creator_name']}")
            skipped += 1
    
    print("\n" + "="*50)
    print("Import Summary:")
    print(f"  ✅ Approved: {approved}")
    print(f"  🔄 For Regeneration: {regenerate}")
    print(f"  ❌ Rejected: {rejected}")
    print(f"  ⚠️ Skipped: {skipped}")
    
    if approved > 0:
        print("\n📌 Next Step:")
        print("  Run: python 3d_upload_youtube.py")


def show_pending_videos():
    """Show videos currently pending review."""
    db = get_db()
    leads = db.get_leads_for_video_review()
    
    if not leads:
        print("No videos pending review.")
        return
    
    table_data = []
    for lead in leads:
        video_a = lead.get("video_a", {})
        video_b = lead.get("video_b", {})
        
        table_data.append([
            lead["channel_id"][:12] + "...",
            lead.get("creator_name", "")[:15],
            lead.get("video_title", "")[:25] + "...",
            "✓" if video_a.get("branded_player_url") else "✗",
            "✓" if video_b.get("branded_player_url") else "✗"
        ])
    
    headers = ["Channel ID", "Creator", "Video Title", "A", "B"]
    print(tabulate(table_data, headers=headers, tablefmt="simple"))
    print(f"\nTotal: {len(leads)} videos pending review")


def interactive_review():
    """
    Interactive mode: Review videos one by one.
    Opens URLs in browser for comparison.
    """
    db = get_db()
    leads = db.get_leads_for_video_review()
    
    if not leads:
        print("No videos pending review.")
        return
    
    print(f"\n🎬 Interactive Video Review - {len(leads)} leads\n")
    print("Commands: [a] select A, [b] select B, [c] custom URL, [r] regenerate, [x] reject, [s] skip, [q] quit\n")
    
    approved = 0
    regenerate = 0
    rejected = 0
    
    for i, lead in enumerate(leads, 1):
        video_a = lead.get("video_a", {})
        video_b = lead.get("video_b", {})
        
        print("="*60)
        print(f"[{i}/{len(leads)}] {lead.get('creator_name', lead.get('channel_name', 'Unknown'))}")
        print(f"  Title: {lead.get('video_title', 'N/A')}")
        print(f"  Email: {lead.get('email', 'NOT SET')}")
        print()
        print(f"  Video A: {video_a.get('branded_player_url', 'N/A')}")
        print(f"  Video B: {video_b.get('branded_player_url', 'N/A')}")
        print()
        
        # Offer to open in browser
        open_browser = input("  Open videos in browser? [y/n]: ").lower().strip()
        if open_browser == 'y':
            if video_a.get('branded_player_url'):
                webbrowser.open(video_a['branded_player_url'])
            if video_b.get('branded_player_url'):
                webbrowser.open(video_b['branded_player_url'])
            print("  → Opened in browser. Review and return here.")
        
        while True:
            action = input("\n  Select [a/b/c/r/x/s/q]: ").lower().strip()
            
            if action == 'q':
                print("\nExiting review mode.")
                print(f"  Approved: {approved}, Regenerate: {regenerate}, Rejected: {rejected}")
                return
            
            if action == 's':
                print("  ⏭️ Skipped")
                break
            
            if action == 'a':
                db.select_video(lead["channel_id"], 'a')
                approved += 1
                print("  ✅ Selected Video A")
                break
            
            if action == 'b':
                db.select_video(lead["channel_id"], 'b')
                approved += 1
                print("  ✅ Selected Video B")
                break
            
            if action == 'c':
                custom_url = input("  Custom URL: ").strip()
                if custom_url:
                    db.set_custom_video_url(lead["channel_id"], custom_url)
                    approved += 1
                    print("  ✅ Using custom URL")
                    break
                else:
                    print("  ⚠️ No URL provided")
            
            if action == 'r':
                new_url = input("  New source video URL (or Enter to use same): ").strip()
                updates = {"status": LeadStatus.APPROVED}
                if new_url:
                    updates["video_url"] = new_url
                db.update_lead_by_channel(lead["channel_id"], updates)
                regenerate += 1
                print("  🔄 Marked for regeneration")
                break
            
            if action == 'x':
                reason = input("  Rejection reason (optional): ").strip() or "Rejected at video review"
                db.disqualify_lead(lead["channel_id"], reason)
                rejected += 1
                print("  ❌ Rejected")
                break
            
            print("  Invalid. Use: a, b, c=custom, r=regenerate, x=reject, s=skip, q=quit")
    
    print("\n" + "="*50)
    print("Review Complete!")
    print(f"  ✅ Approved: {approved}")
    print(f"  🔄 For Regeneration: {regenerate}")
    print(f"  ❌ Rejected: {rejected}")
    
    if approved > 0:
        print("\n📌 Next Step:")
        print("  Run: python 3d_upload_youtube.py")


def show_approved():
    """Show videos approved and ready for YouTube upload."""
    db = get_db()
    leads = db.get_leads_for_upload()
    
    if not leads:
        print("No videos ready for upload.")
        return
    
    table_data = []
    for lead in leads:
        table_data.append([
            lead["channel_id"][:12] + "...",
            lead.get("creator_name", "")[:15],
            lead.get("selected_video", "?"),
            lead.get("branded_player_url", "")[:40] + "..."
        ])
    
    headers = ["Channel ID", "Creator", "Selected", "Video URL"]
    print(tabulate(table_data, headers=headers, tablefmt="simple"))
    print(f"\nTotal: {len(leads)} videos ready for YouTube upload")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review and select generated videos")
    parser.add_argument("--export", action="store_true", help="Export videos for review")
    parser.add_argument("--import", dest="import_file", metavar="FILE", help="Import selections from JSON")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive review mode")
    parser.add_argument("--list", action="store_true", help="List videos pending review")
    parser.add_argument("--approved", action="store_true", help="List approved videos ready for upload")
    parser.add_argument("--limit", type=int, help="Limit number of videos to export")
    
    args = parser.parse_args()
    
    if args.export:
        export_for_review(limit=args.limit)
    elif args.import_file:
        import_selections(args.import_file)
    elif args.interactive:
        interactive_review()
    elif args.list:
        show_pending_videos()
    elif args.approved:
        show_approved()
    else:
        parser.print_help()
        print("\n📌 Quick Start:")
        print("  1. python 3c_accept_videos.py --list      # See pending videos")
        print("  2. python 3c_accept_videos.py --interactive  # Review one by one")
        print("\n  Or batch mode:")
        print("  1. python 3c_accept_videos.py --export")
        print("  2. Fill in selections in JSON")
        print("  3. python 3c_accept_videos.py --import <file>")
