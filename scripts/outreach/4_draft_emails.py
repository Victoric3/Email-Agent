#!/usr/bin/env python3
"""
Step 4: Draft Emails using LLM with Interactive Review.

For each lead with generated assets:
1. Generate personalized email using LLM (incorporating notes field)
2. Interactive review: approve, modify, reprompt, or skip
3. Set scheduled send time on approval

Features:
- LLM-powered personalized emails using lead context and notes
- Interactive mode: review each email before approval
- Direct editing or reprompting for changes
- Round-robin sender assignment
"""
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))  # Add scripts/ to path

from db_client import get_db, LeadStatus
from aws_bedrock_client import AWSBedrockClient

# Configuration
CONTEXT_DIR = Path(__file__).parent.parent.parent / "Context"
TEMPLATE_FILE = CONTEXT_DIR / "template.txt"

# Default interval between scheduled emails (minutes)
DEFAULT_SEND_INTERVAL = 60


def load_template():
    """Load email template as reference for LLM."""
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"⚠️ Template file not found: {TEMPLATE_FILE}")
        return None


async def generate_email_with_llm(client, lead, template_reference):
    """
    Generate personalized email using LLM.
    Uses lead data, notes field, and template as guidance.
    """
    source_video = lead.get("source_video", {})
    video_title = lead.get("video_title") or source_video.get("title", "your video")
    creator_name = lead.get("creator_name", lead.get("channel_name", "there"))
    notes = lead.get("notes", "")
    branded_url = lead.get("branded_player_url", "[VIDEO_LINK]")
    
    # Get channel info
    channel_name = lead.get("channel_name", "")
    overall_assessment = lead.get("overall_assessment", "")
    subject_area = lead.get("subject_area", "educational content")
    
    # Build the prompt
    prompt = f"""You are writing a cold outreach email to a YouTube creator about a video animation service.

CREATOR INFO:
- Name: {creator_name}
- Channel: {channel_name}
- Video we animated: "{video_title}"
- Subject area: {subject_area}
- Assessment: {overall_assessment}

PERSONALIZED VIDEO LINK:
{branded_url}

SPECIAL NOTES/INSTRUCTIONS:
{notes if notes else "No special notes - write a standard outreach email."}

REFERENCE TEMPLATE (for tone/structure, but personalize based on notes):
{template_reference[:1500] if template_reference else "Write a professional, friendly cold email introducing an animation service for educational content."}

TASK: Write a personalized cold email. The email should:
1. Have a catchy subject line referencing their video
2. Be friendly and personal (use their name)
3. Mention the specific video we animated for them
4. Include the video link naturally
5. Be concise (under 200 words for body)
6. If there are special notes, incorporate them thoughtfully

Respond with JSON only:
{{
    "subject": "Email subject line",
    "body": "Full email body with proper formatting and line breaks"
}}

Important: The body should be ready to send - proper greeting, content, signature. Use \\n for line breaks."""

    try:
        response = await client.converse(prompt)
        text = response.get("text", "")
        
        # Clean up potential markdown
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        result = json.loads(text.strip())
        return result.get("subject", ""), result.get("body", "")
    except Exception as e:
        print(f"    ⚠️ LLM email generation failed: {e}")
        return None, None


async def reprompt_email(client, current_subject, current_body, modification_request):
    """
    Reprompt LLM to modify the email based on user feedback.
    """
    prompt = f"""The user wants to modify this email draft.

CURRENT EMAIL:
Subject: {current_subject}

Body:
{current_body}

USER'S MODIFICATION REQUEST:
{modification_request}

TASK: Rewrite the email incorporating the user's feedback. Keep the same general structure unless they asked to change it.

Respond with JSON only:
{{
    "subject": "Updated subject line",
    "body": "Updated email body"
}}"""

    try:
        response = await client.converse(prompt)
        text = response.get("text", "")
        
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        result = json.loads(text.strip())
        return result.get("subject", current_subject), result.get("body", current_body)
    except Exception as e:
        print(f"    ⚠️ Reprompt failed: {e}")
        return current_subject, current_body


def interactive_draft_and_schedule():
    """
    Interactive mode: Generate and review emails one by one.
    Approve with scheduled time, modify, reprompt, or skip.
    """
    db = get_db()
    
    # Get leads with generated assets
    leads = list(db.get_leads_by_status(LeadStatus.ASSET_GENERATED))
    
    if not leads:
        print("No leads with generated assets pending email drafts.")
        print("Run 3b_generate_videos.py and 3c_accept_videos.py first.")
        return
    
    print(f"\n📧 Interactive Email Drafting - {len(leads)} leads\n")
    print("Commands:")
    print("  [a]pprove  - Approve and set schedule time")
    print("  [e]dit     - Edit email directly")
    print("  [r]eprompt - Ask LLM to modify")
    print("  [s]kip     - Skip for now")
    print("  [q]uit     - Exit\n")
    
    # Load template for LLM reference
    template = load_template()
    
    # Initialize LLM client
    client = AWSBedrockClient()
    if not client.is_enabled():
        print("⚠️ Bedrock client is in MOCK mode - emails will use template fallback.\n")
    
    approved = 0
    skipped = 0
    
    # Track scheduled times for round-robin
    scheduled_times = {}  # sender_id -> next available time
    
    for i, lead in enumerate(leads, 1):
        channel_id = lead["channel_id"]
        creator_name = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        video_title = lead.get("video_title", "Unknown")
        email_addr = lead.get("email", "")
        notes = lead.get("notes", "")
        branded_url = lead.get("branded_player_url", "")
        
        print("="*60)
        print(f"[{i}/{len(leads)}] {creator_name}")
        print(f"  Email: {email_addr}")
        print(f"  Video: {video_title}")
        print(f"  Video URL: {branded_url[:60]}..." if branded_url else "  Video URL: NOT SET")
        print(f"  Notes: {notes[:100]}..." if notes else "  Notes: -")
        print()
        
        # Generate email using LLM
        print("  🤖 Generating personalized email...")
        subject, body = asyncio.run(generate_email_with_llm(client, lead, template))
        
        if not subject or not body:
            print("  ⚠️ Email generation failed, using fallback template")
            subject = f"{video_title} - Animation Draft"
            body = f"Hi {creator_name},\n\nI created an animation for your video.\n\nCheck it out: {branded_url}\n\nBest,\nVictor"
        
        # Review loop
        while True:
            print("\n" + "-"*40)
            print(f"📨 Subject: {subject}")
            print("-"*40)
            print(body)
            print("-"*40)
            
            action = input("\nAction [a/e/r/s/q]: ").lower().strip()
            
            if action == 'q':
                print(f"\n✅ Approved: {approved}, ⏭️ Skipped: {skipped}")
                return
            
            if action == 's':
                print("  ⏭️ Skipped")
                skipped += 1
                break
            
            if action == 'e':
                # Direct edit
                print("\n  📝 Enter new subject (or press Enter to keep current):")
                new_subject = input("  Subject: ").strip()
                if new_subject:
                    subject = new_subject
                
                print("  📝 Enter new body (type 'END' on a new line when done):")
                print("  (Press Enter twice then type END to finish)")
                lines = []
                while True:
                    line = input()
                    if line.strip().upper() == 'END':
                        break
                    lines.append(line)
                if lines:
                    body = '\n'.join(lines)
                print("  ✅ Email updated")
                continue
            
            if action == 'r':
                # Reprompt LLM
                print("  📝 What changes would you like? (e.g., 'make it shorter', 'add humor'):")
                modification = input("  Request: ").strip()
                if modification:
                    print("  🤖 Regenerating...")
                    subject, body = asyncio.run(reprompt_email(client, subject, body, modification))
                    print("  ✅ Email regenerated")
                continue
            
            if action == 'a':
                # Approve and schedule
                print("\n  📅 Schedule email:")
                print("     Enter time offset in minutes from now (e.g., 60 for 1 hour)")
                print("     Or enter specific time (e.g., '2025-12-10 14:30')")
                print("     Or press Enter for default (next available slot)")
                
                time_input = input("  Schedule: ").strip()
                
                if time_input:
                    try:
                        # Try parsing as minutes offset
                        minutes = int(time_input)
                        scheduled_time = datetime.now() + timedelta(minutes=minutes)
                    except ValueError:
                        # Try parsing as datetime
                        try:
                            from dateutil import parser as date_parser
                            scheduled_time = date_parser.parse(time_input)
                        except:
                            print("  ⚠️ Invalid time format, using default")
                            scheduled_time = datetime.now() + timedelta(minutes=DEFAULT_SEND_INTERVAL * approved)
                else:
                    # Default: increment from last scheduled
                    scheduled_time = datetime.now() + timedelta(minutes=DEFAULT_SEND_INTERVAL * (approved + 1))
                
                # Save draft to database
                db.set_draft_email(
                    channel_id=channel_id,
                    subject=subject,
                    body=body
                )
                
                # Update with scheduled time
                db.update_lead_by_channel(channel_id, {
                    "scheduled_send_time": scheduled_time,
                    "status": LeadStatus.DRAFTED
                })
                
                approved += 1
                print(f"  ✅ Approved! Scheduled for: {scheduled_time.strftime('%Y-%m-%d %H:%M')}")
                break
            
            print("  Invalid action. Use: a=approve, e=edit, r=reprompt, s=skip, q=quit")
    
    print("\n" + "="*50)
    print("Drafting Complete!")
    print(f"  ✅ Approved: {approved}")
    print(f"  ⏭️ Skipped: {skipped}")
    print("\n📌 Next Steps:")
    print("  1. Review drafts: python manage_leads.py drafts")
    print("  2. Approve for sending: python manage_leads.py approve-all")
    print("  3. Dispatch: python 5_dispatch_emails.py --email 1 --date now")


def draft_emails_batch(limit=None):
    """
    Batch mode: Generate emails without interactive review.
    Uses LLM for personalization but auto-approves.
    """
    db = get_db()
    
    template = load_template()
    client = AWSBedrockClient()
    
    leads = list(db.get_leads_by_status(LeadStatus.ASSET_GENERATED))
    
    if not leads:
        print("No leads with generated assets pending email drafts.")
        return
    
    if limit:
        leads = leads[:limit]
    
    print(f"Found {len(leads)} leads to draft emails for.\n")
    
    drafted_count = 0
    
    for i, lead in enumerate(leads, 1):
        creator = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        channel_id = lead["channel_id"]
        
        print(f"[{i}/{len(leads)}] Drafting for: {creator}...")
        
        subject, body = asyncio.run(generate_email_with_llm(client, lead, template))
        
        if not subject or not body:
            # Fallback to simple template
            source_video = lead.get("source_video", {})
            video_title = lead.get("video_title") or source_video.get("title", "your video")
            branded_url = lead.get("branded_player_url", "[LINK]")
            subject = f"{video_title} - Animation Draft"
            body = f"Hi {creator},\n\nI created an animation for your video.\n\nCheck it out: {branded_url}\n\nBest,\nVictor"
        
        db.set_draft_email(channel_id=channel_id, subject=subject, body=body)
        print(f"  ✅ Draft saved: \"{subject[:50]}...\"")
        drafted_count += 1
    
    print("\n" + "="*50)
    print("Drafting Complete!")
    print(f"  Drafts Created: {drafted_count}")
    print(f"\nNext steps:")
    print("  1. Review: python 4_draft_emails.py --interactive")
    print("  2. Or approve all: python manage_leads.py approve-all")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Draft emails with LLM personalization")
    parser.add_argument("--interactive", "-i", action="store_true", 
                        help="Interactive mode: review each email before approval")
    parser.add_argument("--batch", action="store_true",
                        help="Batch mode: generate all drafts without review")
    parser.add_argument("--limit", type=int, help="Limit number of drafts (batch mode)")
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_draft_and_schedule()
    elif args.batch:
        draft_emails_batch(limit=args.limit)
    else:
        parser.print_help()
        print("\n📌 Quick Start:")
        print("  Interactive: python 4_draft_emails.py --interactive")
        print("  Batch:       python 4_draft_emails.py --batch")
