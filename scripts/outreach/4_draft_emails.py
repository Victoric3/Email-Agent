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
import yt_dlp
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


def fetch_channel_metadata(channel_url):
    """Fetch channel name from URL using yt-dlp."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            return {
                'channel_name': info.get('uploader') or info.get('title'),
            }
    except Exception as e:
        print(f"    ⚠️ Could not fetch channel metadata: {e}")
        return None


def load_template():
    """Load email template as reference for LLM."""
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"⚠️ Template file not found: {TEMPLATE_FILE}")
        return None


async def generate_email_with_llm(client, lead, template_reference, permission_mode=False):
    """
    Generate personalized email using LLM.
    Uses lead data, notes field, and template as guidance.
    """
    source_video = lead.get("source_video", {})
    video_title = lead.get("video_title") or source_video.get("title", "your video")
    creator_name = lead.get("creator_name", lead.get("channel_name", "there"))
    
    # Check for local audio
    local_audio_path = lead.get("local_audio_path")
    is_local_audio = bool(local_audio_path)
    
    # Fetch metadata if needed (unknown creator)
    if not creator_name or creator_name.lower() in ["there", "unknown", "channel", "none"]:
        channel_url = f"https://www.youtube.com/channel/{lead['channel_id']}"
        print(f"    Fetching metadata for {channel_url}...")
        metadata = fetch_channel_metadata(channel_url)
        if metadata and metadata.get('channel_name'):
            creator_name = metadata['channel_name']
            # Update DB with the discovered metadata so future steps have accurate names
            try:
                db = get_db()
                db.update_lead_by_channel(lead['channel_id'], {
                    'creator_name': metadata.get('channel_name'),
                    'channel_name': metadata.get('channel_name')
                })
                print(f"    ✅ Channel metadata saved to DB for {lead['channel_id']}")
            except Exception as e:
                print(f"    ⚠️ Could not update channel metadata in DB: {e}")

    notes = lead.get("notes", "")
    # Prefer final/public video links if present (uploaded YouTube URL or final URL), then branded player
    branded_url = lead.get("final_video_url") or lead.get("youtube_url") or lead.get("branded_player_url") or "[VIDEO_LINK]"
    
    # Get channel info
    channel_name = lead.get("channel_name", "")
    overall_assessment = lead.get("overall_assessment", "")
    subject_area = lead.get("subject_area", "educational content")
    
    if permission_mode:
        # PERMISSION MODE PROMPT
        prompt = f"""You are writing a cold outreach email to a YouTube creator.
The goal is to ask for PERMISSION to create a demo video for them. We have NOT created it yet.

SENDER INFO:
- Name: Victor
- Title: Founder & CEO, EulaIQ

CREATOR INFO:
- Name: {creator_name}
- Channel: {channel_name}
- Video we want to animate: "{video_title}"
- Subject area: {subject_area}

SPECIAL NOTES (Use for compliment):
{notes if notes else "No special notes."}

MANDATORY INSTRUCTIONS:
1. SUBJECT LINE: "{video_title} - Animation Demo?"
2. OPENING: Compliment their content specifically (use the notes if available).
3. INTRO: Briefly explain EulaIQ (AI animation engine for math/science) and mention we are part of the NVIDIA Inception program.
4. THE ASK: Explicitly ask for permission to use the audio from their video "{video_title}" to create a custom animation demo for them.
5. CALL TO ACTION: Ask them to reply "yes" if they are interested in seeing the demo.
6. LENGTH: Keep it short. Under 150 words.
7. SIGNATURE: Sign off as "Victor\\nFounder & CEO, EulaIQ".
8. FORMATTING: Use double newlines (\\n\\n) between paragraphs.

Respond with JSON only:
{{
    "subject": "Email subject line",
    "body": "Full email body with proper formatting and line breaks"
}}"""

    else:
        # STANDARD MODE PROMPT (Video already created)
        prompt = f"""You are writing a cold outreach email to a YouTube creator.
The goal is to sound like a helpful engineer or potential partner, NOT a salesperson.
The vibe should be: "I made this for you to see if it's useful," similar to how an editor might send a draft to a creator.

SENDER INFO:
- Name: Victor
- Title: Founder & CEO, EulaIQ

CREATOR INFO:
- Name: {creator_name}
- Channel: {channel_name}
- Video we animated: "{video_title}"
- Subject area: {subject_area}
- Assessment: {overall_assessment}

PERSONALIZED VIDEO LINK:
{branded_url}

SPECIAL CONTEXT:
{ "This video was generated using a LOCAL AUDIO file (AI-generated lecture based on their content). You MUST explain this clearly: we created a conceptual demonstration using an AI voice/lecture derived from their work to demonstrate the strengths of our animation engine and show them what's possible." if is_local_audio else "" }

SPECIAL NOTES/INSTRUCTIONS:
{notes if notes else "No special notes."}

MANDATORY INSTRUCTIONS:
1. SUBJECT LINE: Must be exactly "{video_title} - Animation Draft" (or very similar, e.g. "Animation Draft: {video_title}"). Do not use "catchy" marketing subjects.
2. OPENING: Brief, genuine compliment on their content.
3. THE "PITCH": Don't pitch. Just say you ran their audio from "{video_title}" through your animation engine (EulaIQ) to see what it would look like.
4. THE LINK: Present the link clearly.
5. CREDIBILITY: Mention EulaIQ is part of the NVIDIA Inception program naturally (e.g. "We're building this engine as part of the NVIDIA Inception program...").
6. VALUE PROP: Focus on "automating the tedious parts" or "going from script to video in minutes".
7. CALL TO ACTION: Ask if they want a login to try it or a quick demo.
8. LENGTH: Keep it short. Under 150 words.
9. SIGNATURE: Sign off as "Victor\\nFounder & CEO, EulaIQ". Do NOT use placeholders like "[Your Name]".
10. FORMATTING: Use double newlines (\\n\\n) between paragraphs to ensure readability.

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


async def reprompt_email(client, current_subject, current_body, modification_request, creator_name=None):
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

{f"IMPORTANT: The creator's name is '{creator_name}'. Ensure the greeting uses this name." if creator_name else ""}

TASK: Rewrite the email incorporating the user's feedback. Keep the same general structure unless they asked to change it.
Ensure the subject line remains focused (e.g. "{current_subject}") and the tone is helpful/internal, not salesy.
Ensure the email mentions that EulaIQ is part of the NVIDIA Inception program.
Ensure the signature is "Victor\\nFounder & CEO, EulaIQ".
Ensure proper line breaks (\\n\\n) between paragraphs.

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


def interactive_draft_and_schedule(target_channel_id=None, permission_mode=False):
    """
    Interactive mode: Generate and review emails one by one.
    Approve with scheduled time, modify, reprompt, or skip.
    """
    db = get_db()
    
    if target_channel_id:
        lead = db.get_lead_by_channel(target_channel_id)
        if not lead:
            print(f"Lead not found: {target_channel_id}")
            return
        leads = [lead]
        print(f"Editing draft for: {lead.get('creator_name')} (Status: {lead['status']})")
    else:
        if permission_mode:
            # In permission mode, we want leads that are APPROVED (reviewed & have email) but not yet processed/uploaded
            # We look for leads in APPROVED status
            leads = list(db.get_leads_by_status(LeadStatus.APPROVED))
            print(f"Found {len(leads)} APPROVED leads for permission request.")
        else:
            # Get leads that were uploaded (final videos available) so we can draft emails
            leads = list(db.get_leads_by_status(LeadStatus.UPLOADED))
    
    if not leads:
        if permission_mode:
            print("No APPROVED leads found for permission request.")
            print("Run 3a_review_leads.py to approve leads and add emails first.")
        else:
            print("No uploaded leads pending email drafts.")
            print("Run 3b_generate_videos.py, 3c_accept_videos.py, and 3d_upload_youtube.py (or use --status uploaded) first.")
        return
    
    print(f"\n📧 Interactive Email Drafting ({'PERMISSION MODE' if permission_mode else 'STANDARD MODE'}) - {len(leads)} leads\n")
    print("Commands:")
    print("  [a]pprove  - Approve and set schedule time")
    print("  [e]dit     - Edit email directly")
    print("  [r]eprompt - Ask LLM to modify")
    print("  [n]ame     - Update creator name")
    print("  [m]ail     - Update recipient email")
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
        # Determine and show video title
        vt = video_title or "Unknown"
        source_video = lead.get("source_video", {})
        local_audio_path = lead.get("local_audio_path")
        # Prefer final/public URLs for display
        final_link = lead.get("final_video_url") or lead.get("youtube_url") or lead.get("branded_player_url") or ""
        print(f"  Video: {vt}")
        
        if not permission_mode:
            # Show final video URL if present (branded/youtube/final) and source video URL if different
            def trunc(s, n=80):
                s = str(s)
                return (s[:n] + "...") if len(s) > n else s

            if final_link:
                print(f"  Video URL: {trunc(final_link)}")
            else:
                print("  Video URL: NOT SET")
            source_display = lead.get("video_url") or source_video.get("video_url") or source_video.get("url")
            if source_display and source_display != branded_url:
                print(f"  Source URL: {trunc(source_display)}")

            if local_audio_path:
                print(f"  🎵 Local Audio: {local_audio_path}")

        # Normalize notes display
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
        
        # Check for existing draft
        existing_draft = lead.get("draft_email", {})
        if existing_draft.get("subject") and existing_draft.get("body"):
            print("  📝 Found existing draft. Loading...")
            subject = existing_draft["subject"]
            body = existing_draft["body"]
        else:
            # Generate email using LLM
            print("  🤖 Generating personalized email...")
            subject, body = asyncio.run(generate_email_with_llm(client, lead, template, permission_mode=permission_mode))
        
        if not subject or not body:
            print("  ⚠️ Email generation failed, using fallback template")
            subject = f"{video_title} - Animation Draft"
            body = f"Hi {creator_name},\n\nI created an animation for your video.\n\nCheck it out: {final_link or '[LINK]'}\n\nBest,\nVictor"
        
        # Review loop
        while True:
            print("\n" + "-"*40)
            print(f"📨 Subject: {subject}")
            print("-"*40)
            print(body)
            print("-"*40)
            
            action = input("\nAction [a/e/r/n/m/s/q]: ").lower().strip()
            
            if action == 'q':
                print(f"\n✅ Approved: {approved}, ⏭️ Skipped: {skipped}")
                return
            
            if action == 's':
                print("  ⏭️ Skipped")
                skipped += 1
                break
            
            if action == 'm':
                # Update email address
                new_email = input(f"  New Email [{email_addr}]: ").strip()
                if new_email:
                    db.update_email(channel_id, new_email)
                    lead["email"] = new_email
                    email_addr = new_email
                    print(f"  ✅ Email updated to: {new_email}")
                continue

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
                    subject, body = asyncio.run(reprompt_email(client, subject, body, modification, creator_name=creator_name))
                    print("  ✅ Email regenerated")
                continue
            
            if action == 'n':
                # Update creator name
                new_name = input(f"  New Creator Name [{creator_name}]: ").strip()
                if new_name:
                    db.update_lead_by_channel(channel_id, {"creator_name": new_name})
                    lead["creator_name"] = new_name
                    creator_name = new_name
                    print(f"  ✅ Creator name updated to: {new_name}")
                    print("  💡 Tip: Use [r]eprompt to regenerate the email with the new name.")
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
    
    leads = list(db.get_leads_by_status(LeadStatus.UPLOADED))
    
    if not leads:
        print("No uploaded leads pending email drafts.")
        print("Run 3b_generate_videos.py, 3c_accept_videos.py, and 3d_upload_youtube.py (or ensure the final video URL is set) first.")
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
            # Prefer final or public URLs for email link
            branded_url = lead.get("final_video_url") or lead.get("youtube_url") or lead.get("branded_player_url") or "[LINK]"
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
    parser.add_argument("--channel", type=str, help="Target specific channel ID (edit existing draft)")
    parser.add_argument("--batch", action="store_true",
                        help="Batch mode: generate all drafts without review")
    parser.add_argument("--limit", type=int, help="Limit number of drafts (batch mode)")
    parser.add_argument("--permission", action="store_true",
                        help="Permission mode: Draft emails asking for permission (no video link)")
    
    args = parser.parse_args()
    
    if args.channel:
        interactive_draft_and_schedule(target_channel_id=args.channel, permission_mode=args.permission)
    elif args.interactive:
        interactive_draft_and_schedule(permission_mode=args.permission)
    elif args.permission:
        # If only --permission is passed, assume interactive mode
        interactive_draft_and_schedule(permission_mode=True)
    elif args.batch:
        draft_emails_batch(limit=args.limit)
    else:
        parser.print_help()
        print("\n📌 Quick Start:")
        print("  Interactive: python 4_draft_emails.py --interactive")
        print("  Permission:  python 4_draft_emails.py --permission")
        print("  Batch:       python 4_draft_emails.py --batch")
