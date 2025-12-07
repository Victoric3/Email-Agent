#!/usr/bin/env python3
"""
Step 4: Draft Emails using Template Replacement.

Reads leads with generated assets from MongoDB, fills in the email template,
and saves drafts to MongoDB for review.

NO LLM NEEDED - just simple string replacement.
"""
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))  # Add scripts/ to path

from db_client import get_db, LeadStatus

# Configuration
CONTEXT_DIR = Path(__file__).parent.parent.parent / "Context"
TEMPLATE_FILE = CONTEXT_DIR / "template.txt"


def load_template():
    """Load email template."""
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Split into subject and body
        lines = content.strip().split("\n")
        subject_line = ""
        body_start = 0
        
        for i, line in enumerate(lines):
            if line.lower().startswith("subject:"):
                subject_line = line.replace("Subject:", "").replace("subject:", "").strip()
            elif line.lower().startswith("body:"):
                body_start = i + 1
                break
        
        body = "\n".join(lines[body_start:]).strip()
        
        return subject_line, body
    except FileNotFoundError:
        print(f"❌ Template file not found: {TEMPLATE_FILE}")
        return None, None


def fill_template(subject_template, body_template, lead):
    """
    Replace placeholders in template with lead data.
    
    Placeholders:
    - [Name] or [name] → creator's first name
    - [Video Title] or [video title] → source video title
    - [Link to EulaIQ Render] or [link] → branded player URL
    - [Math/Physics] → detected subject (math, physics, etc.)
    """
    source_video = lead.get("source_video", {})
    video_title = source_video.get("title", "your video")
    
    # Get creator name (prefer first name from LLM analysis, fallback to channel name)
    creator_name = lead.get("creator_name", "")
    if not creator_name:
        # Try to get first name from icp_analysis
        icp = lead.get("icp_analysis", {})
        creator_name = icp.get("creator_first_name", lead.get("channel_name", "there"))
    
    # Get the branded URL
    branded_url = lead.get("branded_player_url", "[LINK NOT GENERATED]")
    
    # Detect subject from icp_analysis or default to "educational"
    icp = lead.get("icp_analysis", {})
    manim_info = icp.get("manim_compatibility", {})
    subject_type = "Math/Physics"  # Default
    
    # Try to infer from manim tier
    tier = manim_info.get("tier", "").lower() if isinstance(manim_info, dict) else ""
    if "math" in tier or "geometry" in tier:
        subject_type = "Math"
    elif "physics" in tier:
        subject_type = "Physics"
    elif "chemistry" in tier:
        subject_type = "Chemistry"
    elif "computer" in tier or "cs" in tier:
        subject_type = "Computer Science"
    
    # === SUBJECT LINE ===
    # Replace the example title with actual video title
    subject = video_title + " - Animation Draft"
    
    # === BODY ===
    body = body_template
    
    # Replace all placeholder variations
    replacements = {
        "[Name]": creator_name,
        "[name]": creator_name,
        "[Video Title]": video_title,
        "[video title]": video_title,
        '"[Video Title]"': f'"{video_title}"',
        "[Link to EulaIQ Render]": branded_url,
        "[link]": branded_url,
        "[Math/Physics]": subject_type,
        "[math/physics]": subject_type,
    }
    
    for placeholder, value in replacements.items():
        body = body.replace(placeholder, value)
    
    return subject, body


def draft_emails(limit=None):
    """
    Generate email drafts by filling in the template.
    Saves drafts to MongoDB.
    """
    db = get_db()
    
    # Load template
    subject_template, body_template = load_template()
    if not subject_template or not body_template:
        return
    
    print(f"📄 Loaded template from: {TEMPLATE_FILE}\n")
    
    # Get leads that have assets but no draft yet
    leads = db.get_leads_by_status(LeadStatus.ASSET_GENERATED)
    
    if not leads:
        print("No leads with generated assets pending email drafts.")
        return
    
    if limit:
        leads = leads[:limit]
    
    print(f"Found {len(leads)} leads to draft emails for.\n")
    
    drafted_count = 0
    
    for i, lead in enumerate(leads, 1):
        source_video = lead.get("source_video", {})
        video_title = source_video.get("title", "Unknown")[:50]
        creator = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        channel_id = lead["channel_id"]
        
        print(f"[{i}/{len(leads)}] Drafting for: {creator} ({video_title}...)...")
        
        # Fill template
        subject, body = fill_template(subject_template, body_template, lead)
        
        # Save to MongoDB
        db.set_draft_email(
            channel_id=channel_id,
            subject=subject,
            body=body
        )
        
        print(f"  ✅ Draft saved: \"{subject[:50]}...\"")
        drafted_count += 1
    
    # Print summary
    stats = db.get_pipeline_stats()
    print("\n" + "="*50)
    print("Drafting Complete!")
    print(f"  Drafts Created: {drafted_count}")
    print(f"  Total Drafted: {stats.get(LeadStatus.DRAFTED, 0)}")
    print(f"\nNext steps:")
    print("  1. Review drafts: python manage_leads.py drafts")
    print("  2. Add emails: python manage_leads.py set-email <channel_id> <email>")
    print("  3. Approve: python manage_leads.py approve-all")


def redraft_emails(limit=None):
    """
    Re-draft emails for leads that already have drafts.
    Use this after updating video_url or video_title via import-emails.
    """
    db = get_db()
    
    # Load template
    subject_template, body_template = load_template()
    if not subject_template or not body_template:
        return
    
    print(f"📄 Loaded template from: {TEMPLATE_FILE}\n")
    
    # Get leads that already have drafts
    leads = db.get_leads_by_status(LeadStatus.DRAFTED)
    
    if not leads:
        print("No drafted leads to re-draft.")
        return
    
    if limit:
        leads = leads[:limit]
    
    print(f"Found {len(leads)} drafted leads to re-draft.\n")
    
    redrafted_count = 0
    
    for i, lead in enumerate(leads, 1):
        source_video = lead.get("source_video", {})
        video_title = source_video.get("title", "Unknown")[:50]
        creator = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        channel_id = lead["channel_id"]
        
        print(f"[{i}/{len(leads)}] Re-drafting for: {creator}...")
        
        # Fill template with updated data
        subject, body = fill_template(subject_template, body_template, lead)
        
        # Update the draft (keep status as DRAFTED)
        db.update_lead_by_channel(channel_id, {
            "draft_email.subject": subject,
            "draft_email.body": body,
            "draft_email.drafted_at": datetime.now()
        })
        
        print(f"  ✅ Re-drafted: \"{subject[:50]}...\"")
        print(f"      Video URL: {lead.get('branded_player_url', 'NOT SET')[:50]}...")
        redrafted_count += 1
    
    print("\n" + "="*50)
    print("Re-drafting Complete!")
    print(f"  Re-drafted: {redrafted_count}")
    print(f"\nNext steps:")
    print("  1. Review drafts: python manage_leads.py drafts")
    print("  2. Approve: python manage_leads.py approve-all")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Draft emails using template replacement")
    parser.add_argument("--limit", type=int, help="Limit number of drafts to create")
    parser.add_argument("--redraft", action="store_true", 
                        help="Re-draft already drafted emails (after updating video_url/video_title)")
    args = parser.parse_args()
    
    if args.redraft:
        redraft_emails(limit=args.limit)
    else:
        draft_emails(limit=args.limit)
