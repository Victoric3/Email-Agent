#!/usr/bin/env python3
"""
Lead Management CLI Tool.

Provides easy commands to view, update, and manage leads in MongoDB.
This is your "brain interface" to interact with all creator data.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).parent.parent))  # Add scripts/ to path
from db_client import get_db, LeadStatus


def format_date(dt):
    """Format datetime for display."""
    if dt is None:
        return "-"
    if isinstance(dt, str):
        return dt[:10]
    return dt.strftime("%Y-%m-%d")


def cmd_list(args):
    """List leads with optional status filter."""
    db = get_db()
    
    if args.status:
        leads = db.get_leads_by_status(args.status)
    else:
        leads = db.get_all_leads(limit=args.limit)
    
    if not leads:
        print("No leads found.")
        return
    
    # Prepare table data
    table_data = []
    for lead in leads:
        table_data.append([
            lead["channel_id"][:12] + "...",
            lead["creator_name"][:20],
            lead.get("email", "-")[:25] if lead.get("email") else "-",
            lead.get("icp_score", "-"),
            lead["status"],
            format_date(lead.get("next_followup_date"))
        ])
    
    headers = ["Channel ID", "Creator", "Email", "Score", "Status", "Next Followup"]
    print(tabulate(table_data, headers=headers, tablefmt="simple"))
    print(f"\nTotal: {len(leads)} leads")


def cmd_show(args):
    """Show detailed info for a single lead."""
    db = get_db()
    lead = db.get_lead_by_channel(args.channel_id)
    
    if not lead:
        # Try searching
        leads = db.search_leads(args.channel_id)
        if leads:
            print(f"Did you mean one of these?")
            for l in leads[:5]:
                print(f"  - {l['channel_id']} ({l['creator_name']})")
            return
        print(f"Lead not found: {args.channel_id}")
        return
    
    # Pretty print the lead
    print("\n" + "="*60)
    print(f"LEAD: {lead['creator_name']}")
    print("="*60)
    
    print(f"\n📺 Channel Info:")
    print(f"   Channel ID: {lead['channel_id']}")
    print(f"   Channel Name: {lead['channel_name']}")
    print(f"   Video: {lead['video_title']}")
    print(f"   URL: {lead['video_url']}")
    
    print(f"\n📧 Contact:")
    print(f"   Email: {lead.get('email', 'NOT SET')}")
    
    print(f"\n📊 Qualification:")
    print(f"   ICP Score: {lead.get('icp_score', '-')}/10")
    print(f"   Reason: {lead.get('icp_reason', '-')}")
    
    print(f"\n🎬 Asset:")
    print(f"   Player URL: {lead.get('branded_player_url', 'NOT GENERATED')}")
    print(f"   S3 URL: {lead.get('s3_video_url', '-')}")
    
    print(f"\n📤 Outreach:")
    print(f"   Status: {lead['status']}")
    print(f"   Reached Out: {format_date(lead.get('reached_out_at'))}")
    print(f"   Next Followup: {format_date(lead.get('next_followup_date'))}")
    print(f"   Followup Count: {lead.get('followup_count', 0)}")
    
    if lead.get("draft_email", {}).get("subject"):
        print(f"\n📝 Draft Email:")
        print(f"   Subject: {lead['draft_email']['subject']}")
        print(f"   Drafted: {format_date(lead['draft_email'].get('drafted_at'))}")
    
    if lead.get("sent_email", {}).get("sent_at"):
        print(f"\n✉️ Sent Email:")
        print(f"   Subject: {lead['sent_email']['subject']}")
        print(f"   Sent: {format_date(lead['sent_email']['sent_at'])}")
        print(f"   Via: {lead['sent_email'].get('sent_via')}")
    
    if lead.get("conversation_history"):
        print(f"\n💬 Conversation ({len(lead['conversation_history'])} messages):")
        for msg in lead["conversation_history"][-3:]:  # Last 3
            direction = "→" if msg["direction"] == "outbound" else "←"
            print(f"   {direction} [{format_date(msg['date'])}] {msg['content'][:50]}...")
    
    if lead.get("notes"):
        print(f"\n📝 Notes:")
        print(f"   {lead['notes']}")
    
    print()


def cmd_update_email(args):
    """Update email address for a lead."""
    db = get_db()
    if db.update_email(args.channel_id, args.email):
        print(f"✅ Email updated to: {args.email}")
    else:
        print(f"❌ Lead not found: {args.channel_id}")


def cmd_import_emails(args):
    """
    Import emails from a JSON file.
    
    JSON format (array):
    [
        {"channel_id": "UCxxx...", "email": "creator@example.com"},
        {"channel_id": "UCyyy...", "email": "another@example.com"}
    ]
    
    OR object format:
    {
        "UCxxx...": "creator@example.com",
        "UCyyy...": "another@example.com"
    }
    
    NEW FORMAT (recommended) - can update email, video_url, video_title:
    [
        {
            "channel_id": "UCxxx...",
            "email": "creator@example.com",
            "video_url": "https://render.eulaiq.com/player/xxx",
            "video_title": "My Video Title"
        }
    ]
    """
    db = get_db()
    
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return
    
    # Detect format and process
    if isinstance(data, dict):
        # Simple format: {"channel_id": "email", ...}
        print("📧 Detected simple format (email only)...\n")
        _import_simple_format(db, data)
    elif isinstance(data, list):
        # Full format: [{"channel_id": "...", "email": "...", "video_url": "...", ...}]
        print("📧 Detected full format (email + video_url + video_title)...\n")
        _import_full_format(db, data)
    else:
        print("❌ JSON must be an array or object")
        return


def _import_simple_format(db, data):
    """Import simple {channel_id: email} format."""
    success = 0
    not_found = 0
    
    for channel_id, email in data.items():
        if not isinstance(email, str) or "@" not in email:
            print(f"  ⚠️ Skipping invalid: {channel_id}: {email}")
            continue
        
        lead = db.get_lead_by_channel(channel_id)
        if lead:
            db.update_email(channel_id, email)
            creator = lead.get("creator_name", lead.get("channel_name", "Unknown"))
            print(f"  ✅ {creator}: {email}")
            success += 1
        else:
            print(f"  ❌ Not found: {channel_id}")
            not_found += 1
    
    print(f"\n{'='*50}")
    print(f"Import Complete! Updated: {success}, Not Found: {not_found}")
    if success > 0:
        print(f"\nNext: python manage_leads.py approve-all")


def _import_full_format(db, data):
    """Import full format with email, video_url, video_title."""
    updated = 0
    not_found = 0
    needs_redraft = []
    
    for item in data:
        channel_id = item.get("channel_id")
        if not channel_id:
            print(f"  ⚠️ Skipping entry without channel_id")
            continue
        
        lead = db.get_lead_by_channel(channel_id)
        if not lead:
            print(f"  ❌ Not found: {channel_id}")
            not_found += 1
            continue
        
        creator = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        changes = []
        update_data = {}
        redraft_needed = False
        
        # Check email
        new_email = item.get("email", "").strip()
        if new_email and new_email != lead.get("email", ""):
            update_data["email"] = new_email
            changes.append(f"email → {new_email}")
        
        # Check video_url (branded_player_url)
        new_video_url = item.get("video_url", "").strip()
        if new_video_url and new_video_url != lead.get("branded_player_url", ""):
            update_data["branded_player_url"] = new_video_url
            changes.append(f"video_url → {new_video_url[:40]}...")
            redraft_needed = True
        
        # Check video_title
        new_video_title = item.get("video_title", "").strip()
        source_video = lead.get("source_video", {})
        if new_video_title and new_video_title != source_video.get("title", ""):
            update_data["source_video.title"] = new_video_title
            changes.append(f"video_title → {new_video_title[:30]}...")
            redraft_needed = True
        
        if update_data:
            db.update_lead_by_channel(channel_id, update_data)
            print(f"  ✅ {creator}:")
            for change in changes:
                print(f"      {change}")
            updated += 1
            
            if redraft_needed:
                needs_redraft.append(channel_id)
        else:
            print(f"  - {creator}: no changes")
    
    print(f"\n{'='*50}")
    print(f"Import Complete!")
    print(f"  Updated: {updated}")
    print(f"  Not Found: {not_found}")
    
    if needs_redraft:
        print(f"\n⚠️  {len(needs_redraft)} leads had video_url or video_title changed.")
        print(f"   Email drafts need to be regenerated!")
        print(f"\n   Run: python 4_draft_emails.py --redraft")
        print(f"   This will re-draft emails with the new values.")
    elif updated > 0:
        print(f"\nNext: python manage_leads.py approve-all")


def cmd_export_for_emails(args):
    """
    Export drafted leads to JSON for review and updates.
    You can update: email, video_url (EulaIQ render link), video_title
    """
    db = get_db()
    
    # Get drafted leads without emails
    status = args.status if args.status else LeadStatus.DRAFTED
    leads = db.get_leads_by_status(status)
    
    if not leads:
        print(f"No leads with status '{status}' found.")
        return
    
    # Filter to those without emails if requested
    if args.missing_only:
        leads = [l for l in leads if not l.get("email")]
    
    if not leads:
        print("All leads already have emails.")
        return
    
    # Build export data with all editable fields
    export_data = []
    for lead in leads:
        source_video = lead.get("source_video", {})
        export_data.append({
            "channel_id": lead["channel_id"],
            "channel_name": lead.get("channel_name", ""),
            "creator_name": lead.get("creator_name", ""),
            "youtube_url": source_video.get("url", ""),  # Reference: original YouTube video
            "video_title": source_video.get("title", ""),  # EDITABLE: used in email
            "video_url": lead.get("branded_player_url", ""),  # EDITABLE: EulaIQ render link for email
            "email": lead.get("email", "")  # EDITABLE: recipient email
        })
    
    # Write to file
    output_file = Path(args.output) if args.output else Path("emails_to_collect.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"📄 Exported {len(export_data)} leads to: {output_file}")
    print(f"\n📝 Editable fields:")
    print(f"   - email: recipient email address")
    print(f"   - video_url: EulaIQ render link (for the email)")
    print(f"   - video_title: video title (used in email subject/body)")
    print(f"\n💡 youtube_url is for reference only (original video)")
    print(f"\nAfter editing, import with:")
    print(f"  python manage_leads.py import-emails {output_file}")


def cmd_approve(args):
    """Mark a lead's draft as ready to send."""
    db = get_db()
    lead = db.get_lead_by_channel(args.channel_id)
    
    if not lead:
        print(f"Lead not found: {args.channel_id}")
        return
    
    if not lead.get("email"):
        print(f"⚠️ Warning: Lead has no email address!")
        print(f"   Use: python manage_leads.py set-email {args.channel_id} <email>")
        return
    
    if not lead.get("draft_email", {}).get("subject"):
        print(f"⚠️ Lead has no draft email. Run step 4 first.")
        return
    
    db.mark_ready_to_send(args.channel_id)
    print(f"✅ {lead['creator_name']} marked as ready_to_send")
    print(f"   Subject: {lead['draft_email']['subject']}")


def cmd_approve_all(args):
    """Approve all drafted leads that have emails."""
    db = get_db()
    leads = db.get_leads_by_status(LeadStatus.DRAFTED)
    
    if not leads:
        print("No drafted leads to approve.")
        return
    
    # Filter leads with emails
    ready_leads = [l for l in leads if l.get("email")]
    no_email = [l for l in leads if not l.get("email")]
    
    if no_email:
        print(f"⚠️ {len(no_email)} leads have no email and will be skipped:")
        for l in no_email:
            print(f"   - {l['creator_name']} ({l['channel_id'][:15]}...)")
        print()
    
    if not ready_leads:
        print("No leads with emails to approve.")
        return
    
    if not args.force:
        print(f"About to approve {len(ready_leads)} leads for sending:")
        for l in ready_leads:
            print(f"   - {l['creator_name']} → {l['email']}")
        confirm = input(f"\nApprove all {len(ready_leads)} leads? [y/N]: ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return
    
    approved = 0
    for lead in ready_leads:
        db.mark_ready_to_send(lead["channel_id"])
        approved += 1
    
    print(f"\n✅ Approved {approved} leads for sending")
    print(f"   Run: python 5_dispatch_emails.py")


def cmd_drafts(args):
    """View all drafted emails for review."""
    db = get_db()
    leads = db.get_leads_by_status(LeadStatus.DRAFTED)
    
    if not leads:
        print("No drafted emails to review.")
        return
    
    print(f"\n{'='*70}")
    print(f"📝 DRAFT EMAILS FOR REVIEW ({len(leads)} drafts)")
    print(f"{'='*70}\n")
    
    for i, lead in enumerate(leads, 1):
        draft = lead.get("draft_email", {})
        creator = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        email = lead.get("email", "NO EMAIL")
        
        print(f"[{i}] {creator}")
        print(f"    Channel ID: {lead['channel_id']}")
        print(f"    Email: {email}")
        print(f"    Subject: {draft.get('subject', 'NO SUBJECT')}")
        print(f"    {'-'*60}")
        
        body = draft.get("body", "NO BODY")
        # Show first 300 chars of body
        if len(body) > 300:
            print(f"    {body[:300]}...")
            print(f"    [... {len(body)-300} more chars]")
        else:
            print(f"    {body}")
        
        print(f"\n{'='*70}\n")
    
    # Summary
    with_email = sum(1 for l in leads if l.get("email"))
    print(f"Summary: {len(leads)} drafts, {with_email} with emails")
    print(f"\nTo approve all: python manage_leads.py approve-all")
    print(f"To approve one: python manage_leads.py approve <channel_id>")


def cmd_show_draft(args):
    """Show full draft email for a specific lead."""
    db = get_db()
    lead = db.get_lead_by_channel(args.channel_id)
    
    if not lead:
        print(f"Lead not found: {args.channel_id}")
        return
    
    draft = lead.get("draft_email", {})
    if not draft.get("subject"):
        print("No draft email for this lead.")
        return
    
    creator = lead.get("creator_name", lead.get("channel_name", "Unknown"))
    
    print(f"\n{'='*70}")
    print(f"📧 DRAFT EMAIL FOR: {creator}")
    print(f"{'='*70}")
    print(f"To: {lead.get('email', 'NO EMAIL SET')}")
    print(f"Subject: {draft['subject']}")
    print(f"{'='*70}")
    print(draft.get("body", "NO BODY"))
    print(f"{'='*70}\n")
    
    print(f"Channel ID: {lead['channel_id']}")
    print(f"Status: {lead['status']}")
    if lead.get("email"):
        print(f"\nTo approve: python manage_leads.py approve {lead['channel_id']}")
    else:
        print(f"\n⚠️ Set email first: python manage_leads.py set-email {lead['channel_id']} <email>")


def cmd_record_reply(args):
    """Record that a creator replied."""
    db = get_db()
    lead = db.get_lead_by_channel(args.channel_id)
    
    if not lead:
        print(f"Lead not found: {args.channel_id}")
        return
    
    db.record_reply(args.channel_id, args.content)
    print(f"✅ Reply recorded for {lead['creator_name']}")
    print(f"   Status changed to: {LeadStatus.REPLIED}")


def cmd_add_note(args):
    """Add a note to a lead."""
    db = get_db()
    lead = db.get_lead_by_channel(args.channel_id)
    
    if not lead:
        print(f"Lead not found: {args.channel_id}")
        return
    
    # Append to existing notes
    existing = lead.get("notes", "")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    new_note = f"[{timestamp}] {args.note}\n"
    
    db.update_lead_by_channel(args.channel_id, {"notes": existing + new_note})
    print(f"✅ Note added to {lead['creator_name']}")


def cmd_set_status(args):
    """Manually set lead status."""
    db = get_db()
    
    valid_statuses = [
        LeadStatus.QUALIFIED, LeadStatus.ASSET_GENERATED, LeadStatus.DRAFTED,
        LeadStatus.READY_TO_SEND, LeadStatus.SENT, LeadStatus.REPLIED,
        LeadStatus.CONVERTED, LeadStatus.UNSUBSCRIBED, LeadStatus.DEAD
    ]
    
    if args.status not in valid_statuses:
        print(f"Invalid status. Valid options: {', '.join(valid_statuses)}")
        return
    
    db.set_status(args.channel_id, args.status)
    print(f"✅ Status set to: {args.status}")


def cmd_stats(args):
    """Show pipeline statistics."""
    db = get_db()
    stats = db.get_pipeline_stats()
    total = db.get_total_leads()
    
    print("\n📊 PIPELINE STATISTICS")
    print("="*40)
    
    for status, count in sorted(stats.items()):
        bar = "█" * int(count / max(stats.values()) * 20) if stats.values() else ""
        print(f"  {status:20} {count:4} {bar}")
    
    print("-"*40)
    print(f"  {'TOTAL':20} {total:4}")
    print()


def cmd_search(args):
    """Search leads by name, channel, or email."""
    db = get_db()
    leads = db.search_leads(args.query)
    
    if not leads:
        print(f"No leads found matching: {args.query}")
        return
    
    print(f"Found {len(leads)} leads:\n")
    for lead in leads:
        print(f"  • {lead['creator_name']} ({lead['channel_name']})")
        print(f"    ID: {lead['channel_id']}")
        print(f"    Email: {lead.get('email', '-')}")
        print(f"    Status: {lead['status']}")
        print()


def cmd_delete(args):
    """Delete a lead (with confirmation)."""
    db = get_db()
    lead = db.get_lead_by_channel(args.channel_id)
    
    if not lead:
        print(f"Lead not found: {args.channel_id}")
        return
    
    if not args.force:
        confirm = input(f"Delete {lead['creator_name']}? [y/N]: ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return
    
    db.delete_lead(args.channel_id)
    print(f"✅ Deleted: {lead['creator_name']}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="EulaIQ Lead Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_leads.py list                     # List all leads
  python manage_leads.py list --status drafted    # List drafted leads
  python manage_leads.py show UC123...            # Show lead details
  python manage_leads.py set-email UC123 a@b.com  # Update email
  python manage_leads.py approve UC123            # Mark ready to send
  python manage_leads.py reply UC123 "Thanks!"    # Record reply
  python manage_leads.py stats                    # Pipeline statistics
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # list
    p_list = subparsers.add_parser("list", help="List leads")
    p_list.add_argument("--status", help="Filter by status")
    p_list.add_argument("--limit", type=int, default=50, help="Max leads to show")
    
    # show
    p_show = subparsers.add_parser("show", help="Show lead details")
    p_show.add_argument("channel_id", help="Channel ID or search term")
    
    # set-email
    p_email = subparsers.add_parser("set-email", help="Update email address")
    p_email.add_argument("channel_id", help="Channel ID")
    p_email.add_argument("email", help="New email address")
    
    # approve
    p_approve = subparsers.add_parser("approve", help="Mark draft as ready to send")
    p_approve.add_argument("channel_id", help="Channel ID")
    
    # approve-all
    p_approve_all = subparsers.add_parser("approve-all", help="Approve all drafted leads with emails")
    p_approve_all.add_argument("--force", action="store_true", help="Skip confirmation")
    
    # drafts
    subparsers.add_parser("drafts", help="View all drafted emails for review")
    
    # show-draft
    p_show_draft = subparsers.add_parser("show-draft", help="Show full draft for a lead")
    p_show_draft.add_argument("channel_id", help="Channel ID")
    
    # reply
    p_reply = subparsers.add_parser("reply", help="Record creator reply")
    p_reply.add_argument("channel_id", help="Channel ID")
    p_reply.add_argument("content", help="Reply content")
    
    # note
    p_note = subparsers.add_parser("note", help="Add note to lead")
    p_note.add_argument("channel_id", help="Channel ID")
    p_note.add_argument("note", help="Note content")
    
    # status
    p_status = subparsers.add_parser("status", help="Set lead status")
    p_status.add_argument("channel_id", help="Channel ID")
    p_status.add_argument("status", help="New status")
    
    # stats
    subparsers.add_parser("stats", help="Show pipeline statistics")
    
    # search
    p_search = subparsers.add_parser("search", help="Search leads")
    p_search.add_argument("query", help="Search term")
    
    # delete
    p_delete = subparsers.add_parser("delete", help="Delete a lead")
    p_delete.add_argument("channel_id", help="Channel ID")
    p_delete.add_argument("--force", action="store_true", help="Skip confirmation")
    
    # import-emails
    p_import = subparsers.add_parser("import-emails", help="Import emails from JSON file")
    p_import.add_argument("file", help="Path to JSON file with emails")
    
    # export-for-emails
    p_export = subparsers.add_parser("export-for-emails", help="Export leads to JSON for email collection")
    p_export.add_argument("--output", "-o", help="Output file path (default: emails_to_collect.json)")
    p_export.add_argument("--status", help="Status to export (default: drafted)")
    p_export.add_argument("--missing-only", action="store_true", help="Only export leads without emails")
    
    args = parser.parse_args()
    
    if args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "set-email":
        cmd_update_email(args)
    elif args.command == "approve":
        cmd_approve(args)
    elif args.command == "approve-all":
        cmd_approve_all(args)
    elif args.command == "drafts":
        cmd_drafts(args)
    elif args.command == "show-draft":
        cmd_show_draft(args)
    elif args.command == "reply":
        cmd_record_reply(args)
    elif args.command == "note":
        cmd_add_note(args)
    elif args.command == "status":
        cmd_set_status(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "import-emails":
        cmd_import_emails(args)
    elif args.command == "export-for-emails":
        cmd_export_for_emails(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
