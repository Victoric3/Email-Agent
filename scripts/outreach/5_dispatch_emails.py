#!/usr/bin/env python3
"""
Step 5: Dispatch Emails via ZeptoMail with Scheduling.

Features:
- Select sender account (--email 1 for .com, --email 2 for .me)
- Round-robin mode (--round-robin): Alternates between all sender accounts
- Schedule emails (--date now, --date tomorrow, --date 2025-12-10)
- Set sending interval (--interval 60 for 60 minutes between emails)
- Limit number to send (--limit 10)
- Test mode (--test-email your@email.com)

Examples:
  python 5_dispatch_emails.py --email 1 --limit 5 --date now --interval 30
  python 5_dispatch_emails.py --round-robin --limit 10 --date now --interval 30
  python 5_dispatch_emails.py --email 1 --limit 3 --date 2025-12-10 --interval 45 --test-email test@example.com
"""
import smtplib
import datetime
import time
import json
import os
from pathlib import Path
from email.message import EmailMessage
from dateutil import parser as date_parser
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))  # Add scripts/ to path

from db_client import get_db, LeadStatus

# Configuration
MAX_EMAILS_PER_DAY = 50

# ZeptoMail Config
SMTP_SERVER = "smtp.zeptomail.com"
PORT = 587

# Sender Accounts
# Prefer to load SMTP accounts from environment variable SMTP_ACCOUNTS as JSON array.
env_smtp_accounts = os.getenv('SMTP_ACCOUNTS')
if env_smtp_accounts:
    try:
        parsed = json.loads(env_smtp_accounts)
        SENDERS = {i+1: acc for i, acc in enumerate(parsed)}
        if not all('email' in acc and 'username' in acc and 'password' in acc for acc in parsed):
            raise ValueError('Each SMTP account must contain email, username, and password')
    except Exception as e:
        print(f"⚠️ Could not parse SMTP_ACCOUNTS env var: {e}")
        SENDERS = {}
else:
    SENDERS = {}

# Fallback to hard-coded senders only if env var not provided (not recommended)
if not SENDERS:
    print('⚠️ ERROR: No SMTP accounts found. Define SMTP_ACCOUNTS as JSON in your environment or .env (see .env.example). Aborting to avoid using hard-coded credentials.')
    sys.exit(1)

# Schedule storage file
SCHEDULE_FILE = Path(__file__).parent.parent.parent / "data" / "email_schedule.json"
SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)


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


def parse_date(date_str):
    """Parse date string into datetime object."""
    date_str = date_str.lower().strip()
    now = datetime.datetime.now()
    
    if date_str == "now":
        return now
    elif date_str == "tomorrow":
        return now + datetime.timedelta(days=1)
    elif date_str == "today":
        return now
    else:
        # Try to parse specific date
        try:
            parsed = date_parser.parse(date_str)
            # If only date given, set time to 9:00 AM
            if parsed.hour == 0 and parsed.minute == 0:
                parsed = parsed.replace(hour=9, minute=0)
            return parsed
        except Exception as e:
            print(f"❌ Invalid date format: {date_str}")
            print("   Use: now, tomorrow, or YYYY-MM-DD format")
            return None


def create_schedule(leads, sender_id, start_date, interval_minutes, test_email=None, round_robin=False):
    """
    Create a sending schedule for the given leads.
    Returns list of scheduled items with send times.
    
    Args:
        sender_id: Which sender to use (1 or 2), or starting sender for round-robin
        round_robin: If True, alternate between all available senders
    """
    if not round_robin:
        sender = SENDERS.get(sender_id)
        if not sender:
            print(f"❌ Invalid sender ID: {sender_id}. Use 1 or 2.")
            return None
    
    schedule = []
    current_time = start_date
    sender_ids = list(SENDERS.keys())  # [1, 2, ...]
    
    valid_index = 0  # Track actual scheduled items for round-robin
    
    for i, lead in enumerate(leads):
        email = test_email if test_email else lead.get("email")
        if not email:
            print(f"  [SKIP] {lead.get('creator_name', 'Unknown')}: No email address")
            continue
        
        draft = lead.get("draft_email", {})
        subject = draft.get("subject")
        body = draft.get("body")
        
        if not subject or not body:
            print(f"  [SKIP] {lead.get('creator_name', 'Unknown')}: No draft email")
            continue
        
        # Select sender: round-robin or fixed
        if round_robin:
            current_sender_id = sender_ids[valid_index % len(sender_ids)]
        else:
            current_sender_id = sender_id
        
        current_sender = SENDERS[current_sender_id]
        
        schedule.append({
            "index": valid_index + 1,
            "channel_id": lead["channel_id"],
            "creator_name": lead.get("creator_name", lead.get("channel_name", "Unknown")),
            "to_email": email,
            "original_email": lead.get("email"),
            "subject": subject,
            "body": body,
            "sender_id": current_sender_id,
            "sender_email": current_sender["email"],
            "scheduled_time": current_time.isoformat(),
            "status": "pending"
        })
        
        valid_index += 1
        current_time = current_time + datetime.timedelta(minutes=interval_minutes)
    
    return schedule


def save_schedule(schedule):
    """Save schedule to JSON file."""
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "created_at": datetime.datetime.now().isoformat(),
            "items": schedule
        }, f, indent=2)
    print(f"\n📅 Schedule saved to: {SCHEDULE_FILE}")


def load_schedule():
    """Load schedule from JSON file."""
    if not SCHEDULE_FILE.exists():
        return None
    with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def display_schedule(schedule):
    """Display the schedule in a readable format."""
    print("\n" + "=" * 70)
    print("📅 EMAIL SCHEDULE")
    print("=" * 70)
    
    for item in schedule:
        scheduled = datetime.datetime.fromisoformat(item["scheduled_time"])
        status_icon = "⏳" if item["status"] == "pending" else "✅" if item["status"] == "sent" else "❌"
        
        print(f"\n{status_icon} [{item['index']}] {item['creator_name']}")
        print(f"   To: {item['to_email']}")
        if item.get("original_email") and item["original_email"] != item["to_email"]:
            print(f"   (Original: {item['original_email']} - TEST MODE)")
        print(f"   Subject: {item['subject'][:50]}...")
        print(f"   Via: {item['sender_email']}")
        print(f"   Scheduled: {scheduled.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n" + "=" * 70)
    
    first_time = datetime.datetime.fromisoformat(schedule[0]["scheduled_time"])
    last_time = datetime.datetime.fromisoformat(schedule[-1]["scheduled_time"])
    
    print(f"Total: {len(schedule)} emails")
    print(f"First: {first_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Last:  {last_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


def execute_schedule(schedule, dry_run=False, test_mode=False):
    """
    Execute the schedule, waiting for each scheduled time.
    """
    db = get_db()
    
    sent_count = 0
    failed_count = 0
    
    print("\n🚀 Starting scheduled dispatch...")
    if dry_run:
        print("   (DRY RUN - no emails will actually be sent)")
    if test_mode:
        print("   (TEST MODE - sending to test email, lead status will NOT be updated)")
    print()
    
    for item in schedule:
        if item["status"] != "pending":
            continue
        
        scheduled_time = datetime.datetime.fromisoformat(item["scheduled_time"])
        now = datetime.datetime.now()
        
        # Wait until scheduled time
        if scheduled_time > now:
            wait_seconds = (scheduled_time - now).total_seconds()
            print(f"⏳ Waiting {int(wait_seconds)}s until {scheduled_time.strftime('%H:%M:%S')} for {item['creator_name']}...")
            time.sleep(wait_seconds)
        
        sender = SENDERS[item["sender_id"]]
        print(f"\n📧 [{item['index']}/{len(schedule)}] Sending to {item['creator_name']} ({item['to_email']})...")
        print(f"   Via: {sender['email']}")
        print(f"   Subject: {item['subject'][:50]}...")
        
        if dry_run:
            print("   [DRY RUN - skipped]")
            item["status"] = "dry_run"
            sent_count += 1
            continue
        
        if send_email(sender, item["to_email"], item["subject"], item["body"]):
            print("   ✅ Sent!")
            item["status"] = "sent"
            item["sent_at"] = datetime.datetime.now().isoformat()
            
            if not test_mode:
                db.mark_sent(
                    channel_id=item["channel_id"],
                    subject=item["subject"],
                    body=item["body"],
                    sent_via=sender["email"]
                )
            else:
                print("   [TEST MODE] Lead status NOT updated")
            
            sent_count += 1
        else:
            item["status"] = "failed"
            failed_count += 1
        
        save_schedule(schedule)
    
    print("\n" + "=" * 50)
    print("📬 DISPATCH COMPLETE")
    print("=" * 50)
    print(f"  Sent: {sent_count}")
    print(f"  Failed: {failed_count}")
    
    if sent_count > 0 and not dry_run and not test_mode:
        print(f"\nFollowups scheduled for 3 days from now.")
        print("Run `python 6_check_followups.py` daily to see pending followups.")


def dispatch_scheduled(email_id, limit, date_str, interval, dry_run=False, test_email=None, round_robin=False):
    """Main dispatch function with scheduling."""
    db = get_db()
    
    if not round_robin and email_id not in [1, 2]:
        print(f"❌ Invalid --email value: {email_id}")
        print("   Use --email 1 for victor@eulaiq.com")
        print("   Use --email 2 for victor@eulaiq.me")
        print("   Or use --round-robin to alternate between all senders")
        return
    
    if round_robin:
        print(f"🔄 ROUND-ROBIN MODE: Alternating between {len(SENDERS)} sender accounts")
        for sid, sender in SENDERS.items():
            print(f"   Sender {sid}: {sender['email']}")
    else:
        sender = SENDERS[email_id]
        print(f"📧 Sender: {sender['email']}")
    
    start_date = parse_date(date_str)
    if not start_date:
        return
    
    print(f"📅 Start: {start_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Interval: {interval} minutes between emails")
    
    leads = db.get_leads_by_status(LeadStatus.READY_TO_SEND)
    
    if not leads:
        print("\n❌ No leads marked as ready_to_send.")
        print("\nTo approve drafts for sending:")
        print("  python manage_leads.py approve <channel_id>")
        print("  python manage_leads.py approve-all")
        return
    
    if limit:
        leads = leads[:limit]
    
    print(f"📋 Leads to send: {len(leads)}")
    
    if test_email:
        print(f"🧪 TEST MODE: All emails will be sent to {test_email}")
    
    print("\nCreating schedule...")
    schedule = create_schedule(leads, email_id, start_date, interval, test_email, round_robin=round_robin)
    
    if not schedule:
        print("❌ No emails could be scheduled (missing emails or drafts)")
        return
    
    display_schedule(schedule)
    
    if not dry_run:
        print("\n⚠️  Ready to send emails according to schedule above.")
        confirm = input("Proceed? (yes/no): ").strip().lower()
        if confirm not in ["yes", "y"]:
            print("Cancelled.")
            save_schedule(schedule)
            print("Schedule saved. You can review it or run again.")
            return
    
    save_schedule(schedule)
    execute_schedule(schedule, dry_run=dry_run, test_mode=bool(test_email))


def dispatch_single(channel_id: str, email_id: int = 1, dry_run=False, test_email=None):
    """Send email to a single lead by channel_id."""
    db = get_db()
    lead = db.get_lead_by_channel(channel_id)
    
    if not lead:
        print(f"Lead not found: {channel_id}")
        return
    
    sender = SENDERS.get(email_id, SENDERS[1])
    email = test_email if test_email else lead.get("email")
    if not email:
        print(f"No email address for {lead.get('creator_name', 'Unknown')}")
        return
    
    creator_name = lead.get("creator_name", lead.get("channel_name", "Unknown"))
    draft = lead.get("draft_email", {})
    subject = draft.get("subject")
    body = draft.get("body")
    
    if not subject or not body:
        print(f"No draft email for {creator_name}")
        return
    
    if test_email:
        print(f"[TEST MODE] Sending to {test_email} (original: {lead.get('email', 'N/A')})...")
    else:
        print(f"Sending to {creator_name} ({email})...")
    print(f"Subject: {subject}")
    print(f"Via: {sender['email']}")
    
    if dry_run:
        print("\n[DRY RUN - not actually sent]")
        return
    
    if send_email(sender, email, subject, body):
        print("\n✅ Sent successfully!")
        if not test_email:
            db.mark_sent(channel_id=channel_id, subject=subject, body=body, sent_via=sender["email"])
        else:
            print("[TEST MODE] Lead status NOT updated")
    else:
        print("\n❌ Failed to send")


def show_schedule():
    """Display the current saved schedule."""
    data = load_schedule()
    if not data:
        print("No schedule found.")
        return
    
    print(f"Schedule created: {data['created_at']}")
    display_schedule(data["items"])
    
    pending = sum(1 for i in data["items"] if i["status"] == "pending")
    sent = sum(1 for i in data["items"] if i["status"] == "sent")
    failed = sum(1 for i in data["items"] if i["status"] == "failed")
    
    print(f"\nStatus: {pending} pending, {sent} sent, {failed} failed")


def resume_schedule(dry_run=False):
    """Resume a previously saved schedule."""
    data = load_schedule()
    if not data:
        print("No schedule found to resume.")
        return
    
    pending = [i for i in data["items"] if i["status"] == "pending"]
    if not pending:
        print("No pending emails in schedule. All done!")
        return
    
    print(f"Found {len(pending)} pending emails to send.")
    display_schedule(data["items"])
    
    if not dry_run:
        confirm = input("\nResume sending? (yes/no): ").strip().lower()
        if confirm not in ["yes", "y"]:
            print("Cancelled.")
            return
    
    test_mode = any(i.get("original_email") and i["original_email"] != i["to_email"] for i in data["items"])
    execute_schedule(data["items"], dry_run=dry_run, test_mode=test_mode)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Dispatch emails with scheduling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send 5 emails now, 30 min apart, via eulaiq.com
  python 5_dispatch_emails.py --email 1 --limit 5 --date now --interval 30
  
  # Schedule 10 emails for tomorrow, 1 hour apart, via eulaiq.me
  python 5_dispatch_emails.py --email 2 --limit 10 --date tomorrow --interval 60
  
  # ROUND-ROBIN: Alternate between all sender accounts
  python 5_dispatch_emails.py --round-robin --limit 10 --date now --interval 30
  
  # Test with your email (no lead status updates)
  python 5_dispatch_emails.py --email 1 --limit 3 --date now --interval 5 --test-email chukwujiobivictoric@gmail.com
  
  # Preview schedule without sending
  python 5_dispatch_emails.py --email 1 --limit 5 --date now --interval 30 --dry-run
  
  # View current schedule
  python 5_dispatch_emails.py --show-schedule
  
  # Resume interrupted schedule
  python 5_dispatch_emails.py --resume
        """
    )
    parser.add_argument("--email", type=int, choices=[1, 2], default=1,
                        help="Sender: 1=victor@eulaiq.com, 2=victor@eulaiq.me")
    parser.add_argument("--round-robin", "-rr", action="store_true",
                        help="Alternate between all sender accounts (ignores --email)")
    parser.add_argument("--limit", type=int, help="Max emails to send")
    parser.add_argument("--date", type=str, default="now",
                        help="Start: 'now', 'tomorrow', or 'YYYY-MM-DD HH:MM'")
    parser.add_argument("--interval", type=int, default=60,
                        help="Minutes between emails (default: 60)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--test-email", type=str, help="Send all to this address (testing)")
    parser.add_argument("--single", type=str, help="Send to single channel_id")
    parser.add_argument("--show-schedule", action="store_true", help="Show saved schedule")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted schedule")
    
    args = parser.parse_args()
    
    if args.show_schedule:
        show_schedule()
    elif args.resume:
        resume_schedule(dry_run=args.dry_run)
    elif args.single:
        dispatch_single(args.single, email_id=args.email, dry_run=args.dry_run, test_email=args.test_email)
    else:
        dispatch_scheduled(
            email_id=args.email, limit=args.limit, date_str=args.date,
            interval=args.interval, dry_run=args.dry_run, test_email=args.test_email,
            round_robin=args.round_robin
        )
