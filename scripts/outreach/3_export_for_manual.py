#!/usr/bin/env python3
"""
Step 3 (Manual Mode): Export qualified leads for manual asset generation.

Instead of auto-generating videos, this script:
1. Exports lead details to a JSON file for manual video creation
2. Sets a placeholder URL that can be updated later
3. Advances leads to 'asset_generated' status so email drafting can proceed

Usage:
    python 3_export_for_manual.py --limit 5
    python 3_export_for_manual.py  # Process all qualified leads
"""
import json
import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_client import get_db, LeadStatus

# Output directory for manual processing queue
MANUAL_QUEUE_DIR = Path(__file__).parent.parent.parent / "manual_queue"
MANUAL_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

# Placeholder URL pattern - you'll replace [VIDEO_ID] with actual ID after generating
PLACEHOLDER_URL = "https://render.eulaiq.com/player/PENDING_[CHANNEL_ID]"


def export_for_manual(limit=None):
    """
    Export qualified leads to JSON for manual video generation.
    """
    db = get_db()
    
    # Get qualified leads
    leads = db.get_leads_by_status(LeadStatus.QUALIFIED)
    
    if not leads:
        print("No qualified leads to export.")
        return
    
    if limit:
        leads = leads[:limit]
    
    print(f"Found {len(leads)} qualified leads to export.\n")
    
    # Prepare export data
    export_items = []
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    
    for i, lead in enumerate(leads, 1):
        channel_id = lead["channel_id"]
        source_video = lead.get("source_video", {})
        
        # Extract video details
        video_url = source_video.get("url", f"https://youtube.com/watch?v={source_video.get('video_id', '')}")
        video_id = source_video.get("video_id", "")
        video_title = source_video.get("title", "Unknown Video")
        creator_name = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        channel_name = lead.get("channel_name", creator_name)
        
        print(f"[{i}/{len(leads)}] {creator_name}")
        print(f"    Video: {video_title[:50]}...")
        print(f"    URL: {video_url}")
        
        # Create export item with all details needed for manual generation
        export_item = {
            "channel_id": channel_id,
            "creator_name": creator_name,
            "channel_name": channel_name,
            "video_id": video_id,
            "video_url": video_url,
            "video_title": video_title,
            "video_description": source_video.get("description", "")[:500],
            "subscriber_count": lead.get("subscriber_count"),
            "email": lead.get("email"),
            "score": lead.get("final_score"),
            "status": "pending_generation",
            "placeholder_url": PLACEHOLDER_URL.replace("[CHANNEL_ID]", channel_id[:12]),
            "generated_url": None,  # Fill this in after generating
            "notes": ""  # Add any notes during manual processing
        }
        export_items.append(export_item)
        
        # Update lead in DB with placeholder URL
        placeholder = PLACEHOLDER_URL.replace("[CHANNEL_ID]", channel_id[:12])
        db.set_asset_generated(
            channel_id=channel_id,
            branded_url=placeholder,
            s3_url="",
            eulaiq_video_id=f"manual_{channel_id[:12]}"
        )
        print(f"    ✓ Exported (placeholder: {placeholder[:50]}...)\n")
    
    # Save to JSON file
    output_file = MANUAL_QUEUE_DIR / f"manual_queue_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "exported_at": timestamp,
            "count": len(export_items),
            "items": export_items
        }, f, indent=2, ensure_ascii=False)
    
    print("=" * 60)
    print("EXPORT COMPLETE")
    print("=" * 60)
    print(f"  Exported: {len(export_items)} leads")
    print(f"  Output file: {output_file}")
    print(f"\nNext steps:")
    print(f"  1. Open {output_file.name}")
    print(f"  2. For each item, generate video using the video_url")
    print(f"  3. Update 'generated_url' field with actual EulaIQ link")
    print(f"  4. Run: python 3_update_urls.py {output_file.name}")
    print(f"\nOr continue with placeholder URLs:")
    print(f"  python 4_draft_emails.py")


def update_urls_from_json(json_file):
    """
    Update lead URLs from a completed manual queue JSON file.
    """
    db = get_db()
    
    json_path = Path(json_file)
    if not json_path.exists():
        # Try in manual_queue directory
        json_path = MANUAL_QUEUE_DIR / json_file
    
    if not json_path.exists():
        print(f"File not found: {json_file}")
        return
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    items = data.get("items", [])
    updated = 0
    
    print(f"Processing {len(items)} items from {json_path.name}...\n")
    
    for item in items:
        channel_id = item["channel_id"]
        generated_url = item.get("generated_url")
        
        if generated_url and generated_url != item.get("placeholder_url"):
            # Update the lead with actual URL
            db.update_lead_by_channel(channel_id, {
                "asset_info.branded_url": generated_url,
                "asset_info.updated_at": datetime.datetime.utcnow()
            })
            print(f"  ✓ Updated {item['creator_name']}: {generated_url[:50]}...")
            updated += 1
        else:
            print(f"  - Skipped {item['creator_name']} (no generated_url)")
    
    print(f"\nUpdated {updated}/{len(items)} leads.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export leads for manual asset generation")
    parser.add_argument("--limit", type=int, help="Limit number of leads to export")
    parser.add_argument("--update", type=str, help="Update URLs from completed JSON file")
    args = parser.parse_args()
    
    if args.update:
        update_urls_from_json(args.update)
    else:
        export_for_manual(limit=args.limit)
