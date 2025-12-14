#!/usr/bin/env python3
"""
Step 3a: Manual Lead Review with Video/Audio Customization.

Export qualified leads for manual review. You will:
1. Research creator emails
2. View their channel to decide if they're a good fit
3. Approve or disqualify each lead
4. Optionally: Change video URL, provide local audio path, or skip to process later
5. Import back with emails and decisions

This combines email collection with manual qualification in one step.
"""
import json
import os
import sys
import argparse
import shutil
from pathlib import Path
from datetime import datetime
from tabulate import tabulate
import yt_dlp

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_db, LeadStatus

# Output directory for review files
REVIEW_DIR = Path(__file__).parent.parent.parent / "review_queue"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)

# Local audio directory
LOCAL_AUDIO_DIR = Path(__file__).parent.parent.parent / "assets" / "audio_local"
LOCAL_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


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
        # Handle nested source_video data from harvester
        source_video = lead.get("source_video", {})
        video_title = lead.get("video_title") or source_video.get("title", "")
        video_id = lead.get("video_id") or source_video.get("video_id", "")
        video_url = lead.get("video_url")
        if not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        export_items.append({
            "channel_id": lead["channel_id"],
            "channel_name": lead["channel_name"],
            "creator_name": lead.get("creator_name", lead["channel_name"]),
            "video_title": video_title,
            "video_url": video_url or "",
            "video_id": video_id,
            "channel_url": f"https://youtube.com/channel/{lead['channel_id']}",
            "icp_score": lead.get("icp_score") or lead.get("final_score", 0),
            "icp_reason": lead.get("icp_reason", ""),
            "subscriber_count": lead.get("subscriber_count", "unknown"),
            # Fields for you to fill in:
            "email": lead.get("email") or "",  # ADD EMAIL HERE
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
                # Update notes directly as string to match interactive mode
                db.update_lead_by_channel(channel_id, {"notes": item["notes"]})
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


def fetch_video_metadata(video_url):
    """Fetch video title and ID from YouTube URL using yt-dlp."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return {
                'video_id': info.get('id'),
                'video_title': info.get('title'),
                'video_url': video_url
            }
    except Exception as e:
        print(f"    ⚠️ Could not fetch video metadata: {e}")
        return None


def interactive_review(status=LeadStatus.QUALIFIED):
    """
    Interactive mode: Review leads one by one in terminal.
    Supports video/audio customization before approval.
    """
    db = get_db()
    leads = list(db.get_leads_by_status(status))
    
    if not leads:
        print(f"No leads with status '{status}' pending review.")
        return
    
    print(f"\n📋 Interactive Review Mode ({status}) - {len(leads)} leads\n")
    
    # Define available commands based on status
    print("Commands:")
    if status == LeadStatus.QUALIFIED:
        print("  [a]pprove  - Approve with email")
        print("  [d]isqualify - Reject lead")
    else:
        print("  [n]ext     - Save and go to next")
    
    print("  [s]kip    - Skip to end (process later)")
    print("  [p]revious - Go to previous lead")
    print("  [v]ideo   - Change Source YouTube video URL")
    print("  [l]ocal   - Use local audio file")
    
    if status in [LeadStatus.APPROVED, LeadStatus.UPLOADED]:
        print("  [t]emplate - Change video template (video_to_generate)")
        print("  [f]inal    - Set final YouTube unlisted URL (sets status to UPLOADED)")
        
    print("  [q]uit    - Exit\n")
    
    approved = 0
    disqualified = 0
    updated = 0
    current_index = 0
    
    while current_index < len(leads):
        lead = leads[current_index]
        i = current_index + 1
        
        # Handle nested source_video data from harvester
        source_video = lead.get("source_video", {})
        video_title = lead.get("video_title") or source_video.get("title", "Unknown")
        video_id = lead.get("video_id") or source_video.get("video_id")
        video_url = lead.get("video_url")
        local_audio_path = lead.get("local_audio_path")
        # Prefer final/public URLs for display
        final_link = lead.get("final_video_url") or lead.get("youtube_url") or lead.get("branded_player_url") or ""
        if not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
        local_audio_path = lead.get("local_audio_path")
        
        print("="*60)
        print(f"[{i}/{len(leads)}] {lead.get('creator_name', lead['channel_name'])}")
        print(f"  Channel: https://youtube.com/channel/{lead['channel_id']}")
        def trunc(s, n=80):
            s = str(s)
            return (s[:n] + "...") if len(s) > n else s

        # Display main/selected video info
        print(f"  Video: {video_title}")
        if final_link:
            print(f"  Video URL: {trunc(final_link)}")
        else:
            print("  Video URL: NOT SET")

        # Show the original source video if it differs from final
        source_display = video_url or source_video.get("video_url") or source_video.get("url")
        if source_display and source_display != final_link:
            print(f"  Source URL: {trunc(source_display)}")
        if local_audio_path:
            print(f"  🎵 Local Audio: {local_audio_path}")
            
        if status in [LeadStatus.APPROVED, LeadStatus.UPLOADED]:
            print(f"  Template: {lead.get('video_to_generate', 'NOT SET')}")
            print(f"  Final URL: {lead.get('final_video_url', 'NOT SET')}")
            
        print(f"  Score: {lead.get('icp_score', lead.get('final_score', '-'))}/10")
        print(f"  Current Email: {lead.get('email', 'NOT SET')}")
        # Normalize notes display
        notes = lead.get('notes', '')
        if not notes:
            print("  Notes: -")
        else:
            if isinstance(notes, list):
                notes_str = "\n    - ".join([str(n).strip() for n in notes if n])
                print(f"  Notes:\n    - {notes_str}")
            else:
                ns = str(notes).replace('\n', ' ').strip()
                print(f"  Notes: {ns[:200]}" + ("..." if len(ns) > 200 else ""))
        print()
        
        while True:
            action = input("Action: ").lower().strip()
            
            if action == 'q':
                print("\nExiting review mode.")
                return
            
            if action == 's':
                print("  ⏭️ Skipped")
                current_index += 1
                break
            
            if action == 'p':
                if current_index > 0:
                    print("  ⏮️ Previous")
                    current_index -= 1
                    break
                else:
                    print("  ⚠️ Already at the first lead")
                    continue
            
            if action == 'v':
                new_url = input("  New Source YouTube URL: ").strip()
                if new_url:
                    print("  Fetching video metadata...")
                    metadata = fetch_video_metadata(new_url)
                    if metadata:
                        db.update_lead_by_channel(lead["channel_id"], {
                            "video_url": metadata['video_url'],
                            "video_id": metadata['video_id'],
                            "video_title": metadata['video_title'],
                            "source_video.video_id": metadata['video_id'],
                            "source_video.title": metadata['video_title'],
                            "local_audio_path": None
                        })
                        # Update local vars for display
                        video_title = metadata['video_title']
                        video_url = metadata['video_url']
                        print(f"  ✅ Source video updated: {video_title}")
                    else:
                        print("  ⚠️ Could not update video")
                continue
            
            if action == 'l':
                audio_path = input("  Local audio path (or drag file): ").strip().strip('"').strip("'")
                if audio_path and os.path.exists(audio_path):
                    filename = os.path.basename(audio_path)
                    title_from_file = os.path.splitext(filename)[0]
                    dest_path = LOCAL_AUDIO_DIR / f"{lead['channel_id']}_{filename}"
                    shutil.copy2(audio_path, dest_path)
                    
                    db.update_lead_by_channel(lead["channel_id"], {
                        "local_audio_path": str(dest_path),
                        "video_title": title_from_file,
                        "source_video.title": title_from_file,
                        "video_url": None,
                        "video_id": None
                    })
                    local_audio_path = str(dest_path)
                    video_title = title_from_file
                    print(f"  ✅ Local audio set: {filename}")
                else:
                    print("  ⚠️ File not found")
                continue

            if status in [LeadStatus.APPROVED, LeadStatus.UPLOADED]:
                if action == 't':
                    new_template = input(f"  New Template [{lead.get('video_to_generate', '')}]: ").strip()
                    if new_template:
                        db.update_lead_by_channel(lead["channel_id"], {"video_to_generate": new_template})
                        lead["video_to_generate"] = new_template
                        print(f"  ✅ Template updated to: {new_template}")
                    continue
                
                if action == 'f':
                    new_final = input(f"  Final Video URL [{lead.get('final_video_url', '')}]: ").strip()
                    if new_final:
                        db.update_lead_by_channel(lead["channel_id"], {
                            "final_video_url": new_final,
                            "status": LeadStatus.UPLOADED
                        })
                        lead["final_video_url"] = new_final
                        print(f"  ✅ Final URL set. Status -> UPLOADED")
                        updated += 1
                    continue
                
                if action == 'n':
                    print("  ✅ Saved & Next")
                    current_index += 1
                    break

            if status == LeadStatus.QUALIFIED:
                if action == 'a':
                    current_email = lead.get("email", "")
                    prompt_email = f"  Email [{current_email}]: " if current_email else "  Email: "
                    new_email = input(prompt_email).strip()
                    final_email = new_email if new_email else current_email
                    
                    if not final_email:
                        print("  ⚠️ Email required for approval")
                        continue
                    
                    # Notes handling
                    current_notes = lead.get("notes", "")
                    if isinstance(current_notes, list):
                        current_notes = " ".join([str(n) for n in current_notes])
                    
                    prompt_notes = f"  Notes [{current_notes}]: " if current_notes else "  Notes (optional): "
                    new_notes = input(prompt_notes).strip()
                    final_notes = new_notes if new_notes else current_notes
                    
                    db.approve_for_video(lead["channel_id"], final_email)
                    if final_notes != current_notes:
                         db.update_lead_by_channel(lead["channel_id"], {"notes": final_notes})

                    approved += 1
                    print(f"  ✅ Approved with email: {final_email}")
                    current_index += 1
                    break
                
                if action == 'd':
                    reason = input("  Reason: ").strip() or "Manual rejection"
                    db.disqualify_lead(lead["channel_id"], reason)
                    disqualified += 1
                    print(f"  ❌ Disqualified")
                    current_index += 1
                    break
            
            print("  Invalid action.")
    
    print("\n" + "="*50)
    print("Review Complete!")
    print(f"  ✅ Approved/Updated: {approved + updated}")
    print(f"  ❌ Disqualified: {disqualified}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual lead review before video generation")
    parser.add_argument("--export", action="store_true", help="Export qualified leads for review")
    parser.add_argument("--import", dest="import_file", metavar="FILE", help="Import reviewed leads from JSON")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive review mode")
    parser.add_argument("--status", type=str, default=LeadStatus.QUALIFIED, 
                        help=f"Status to review (default: {LeadStatus.QUALIFIED})")
    parser.add_argument("--list", action="store_true", help="List leads pending review")
    parser.add_argument("--limit", type=int, help="Limit number of leads to export")
    
    args = parser.parse_args()
    
    if args.export:
        export_for_review(limit=args.limit)
    elif args.import_file:
        import_reviews(args.import_file)
    elif args.interactive:
        interactive_review(status=args.status)
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
        print("  python 3a_review_leads.py --interactive --status approved  # Review already approved leads")
