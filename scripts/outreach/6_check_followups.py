#!/usr/bin/env python3
"""
Step 6: Check & Send Followup Emails.

Identifies leads needing followup today and optionally sends followup emails.
Implements the 3-7-10-15 day followup pattern.
"""
import asyncio
import json
import os
import smtplib
from pathlib import Path
from datetime import datetime, timedelta
from email.message import EmailMessage
from itertools import cycle
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))  # Add scripts/ to path

from aws_bedrock_client import AWSBedrockClient
from db_client import get_db, LeadStatus, FOLLOWUP_PATTERN

# ZeptoMail Config (same as dispatch)
SMTP_SERVER = "smtp.zeptomail.com"
PORT = 587

# Load SMTP accounts from environment variable SMTP_ACCOUNTS to avoid hard-coded secrets
env_smtp_accounts = os.getenv('SMTP_ACCOUNTS')
if env_smtp_accounts:
    try:
        smtp_list = json.loads(env_smtp_accounts)
        SENDERS = smtp_list
    except Exception as e:
        print(f"⚠️ Could not parse SMTP_ACCOUNTS env var: {e}")
        SENDERS = []
else:
    SENDERS = []

if not SENDERS:
    print('⚠️ ERROR: No SMTP accounts found for followups. Define SMTP_ACCOUNTS in your environment or .env (see .env.example). Aborting.')
    sys.exit(1)


def send_email(sender, to_email, subject, body):
    """Send email using ZeptoMail SMTP."""
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f"Victor from EulaIQ <{sender['email']}>"
    msg['To'] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_SERVER, PORT) as server:
            server.starttls()
            server.login(sender['username'], sender['password'])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"  ❌ Send failed: {e}")
        return False


FOLLOWUP_TEMPLATES = {
    1: """Just following up on my email from a few days ago about the animation I created for your "{video_title}" video.

Did you get a chance to watch it? Here's the link again: {branded_player_url}

I'd love to hear your thoughts - even if it's just "not interested right now." Either way, no pressure!

Best,
Victor""",
    
    2: """Hey {creator_name},

I know you're busy, so I'll keep this short.

I made a full animated version of your "{video_title}" video using our system. It handles complex diagrams and equations better than generic AI tools.

Take a look when you have a moment: {branded_player_url}

If you'd prefer I stop reaching out, just let me know.

Victor
CEO, EulaIQ""",
    
    3: """Quick bump on this - the animation I generated for "{video_title}" is still available here: {branded_player_url}

If animated content isn't something you're exploring right now, totally understand. Just reply "pass" and I won't follow up again.

Victor""",
    
    4: """Last note from me - if you're ever curious about adding animations to your content, the sample I created for "{video_title}" will be here: {branded_player_url}

Thanks for your time, {creator_name}.

Best,
Victor
EulaIQ"""
}


def get_leads_for_followup():
    """Get all leads where followup is due today or earlier."""
    db = get_db()
    return db.get_leads_needing_followup()


def preview_followups():
    """Show leads needing followup without sending."""
    leads = get_leads_for_followup()
    
    if not leads:
        print("🎉 No followups due today!")
        return
    
    print(f"📬 {len(leads)} FOLLOWUPS DUE\n")
    print("-" * 60)
    
    for lead in leads:
        followup_num = lead.get("followup_count", 0) + 1
        days_since = (datetime.utcnow() - lead.get("reached_out_at", datetime.utcnow())).days
        
        print(f"  {lead['creator_name']} ({lead['channel_name']})")
        print(f"    Email: {lead.get('email', 'MISSING')}")
        print(f"    Followup #{followup_num} (Day {days_since})")
        print(f"    Video: {lead['video_title'][:40]}...")
        print()
    
    print("-" * 60)
    print(f"\nTo send followups, run:")
    print(f"  python 6_check_followups.py --send")


async def generate_followup_email(lead, followup_number):
    """Generate a followup email using template or AI."""
    # Use template if available
    if followup_number in FOLLOWUP_TEMPLATES:
        template = FOLLOWUP_TEMPLATES[followup_number]
        body = template.format(
            creator_name=lead["creator_name"],
            video_title=lead["video_title"],
            branded_player_url=lead.get("branded_player_url", "")
        )
        
        subject_prefix = {1: "Re: ", 2: "Re: ", 3: "Quick bump - ", 4: "Final note - "}
        original_subject = lead.get("sent_email", {}).get("subject", "Animation Draft")
        subject = f"{subject_prefix.get(followup_number, 'Re: ')}{original_subject}"
        
        return subject, body
    
    # Fallback to AI generation for custom followups
    client = AWSBedrockClient()
    
    prompt = f"""
Write a brief, professional followup email #{followup_number} for a creator who hasn't responded.

Original context:
- Creator: {lead['creator_name']}
- Video: {lead['video_title']}
- Animation Link: {lead.get('branded_player_url', '')}
- Days since last contact: {(datetime.utcnow() - lead.get('reached_out_at', datetime.utcnow())).days}

Tone: Friendly but professional. Not pushy. Give them an easy out.
Keep it SHORT (3-4 sentences max).

Output JSON:
{{"subject": "...", "body": "..."}}
"""
    
    response = await client.converse(prompt)
    text = response["text"]
    
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    
    import json
    data = json.loads(text.strip())
    return data["subject"], data["body"]


async def send_followups(dry_run=False, limit=None):
    """Send followup emails to leads that need them."""
    db = get_db()
    leads = get_leads_for_followup()
    
    if not leads:
        print("🎉 No followups due today!")
        return
    
    if limit:
        leads = leads[:limit]
    
    print(f"📬 Sending {len(leads)} followups...\n")
    
    # Use module-level send_email and SENDERS
    sender_iter = cycle(SENDERS)
    
    sent = 0
    failed = 0
    
    for lead in leads:
        email = lead.get("email")
        if not email:
            print(f"  [SKIP] {lead['creator_name']}: No email")
            continue
        
        followup_num = lead.get("followup_count", 0) + 1
        
        print(f"  [{followup_num}/4] {lead['creator_name']}...", end="")
        
        try:
            subject, body = await generate_followup_email(lead, followup_num)
            
            if dry_run:
                print(f" [DRY RUN]")
                print(f"      Subject: {subject}")
                sent += 1
                continue
            
            sender = next(sender_iter)
            
            # Use module-level send_email function
            if send_email(sender, email, subject, body):
                print(" ✅ Sent")
                
                # Update MongoDB
                db.record_followup_sent(
                    channel_id=lead["channel_id"],
                    followup_number=followup_num,
                    subject=subject,
                    body=body
                )
                sent += 1
            else:
                print(" ❌ Failed")
                failed += 1
                
        except Exception as e:
            print(f" ❌ Error: {e}")
            failed += 1
    
    print(f"\n{'='*40}")
    print(f"Followups Complete: {sent} sent, {failed} failed")
    
    if sent > 0 and not dry_run:
        print(f"Next followup dates updated in MongoDB.")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Check and send followup emails")
    parser.add_argument("--send", action="store_true", help="Actually send followups")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails without sending")
    parser.add_argument("--limit", type=int, help="Limit number of followups to send")
    
    args = parser.parse_args()
    
    if args.send or args.dry_run:
        asyncio.run(send_followups(dry_run=args.dry_run, limit=args.limit))
    else:
        preview_followups()


if __name__ == "__main__":
    main()
