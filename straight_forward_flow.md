### Prerequisites

```bash
cd "c:\Users\pharm victor\Desktop\company files\Emails\scripts\outreach"
```

## 🛠️ Management Commands

```bash
# View stats
python manage_leads.py stats

# List leads by status
python manage_leads.py list --status approved
python manage_leads.py list --status uploaded


# To revert status to uploaded:
python manage_leads.py status UC6MExc-ZeDFb4VFoGfU4Nfw uploaded
```

## Step 1: Harvest Leads

```bash
python 1_harvest_leads.py --limit 5
```

## Step 2: Refine & Qualify Leads

```bash
python 2_refine_leads.py --limit 20
```

## Step 3a: Manual Lead Review (Add Emails)

```bash
python 3a_review_leads.py --interactive
```

**Export Audios for Manual Generation:**

```bash
python export_audios.py
```

### Modifying Approved Leads

If you need to change the video, add local audio, or set the final video URL for a lead you've **already approved** (but haven't generated videos for yet), use the `--status` flag. You can now review both `approved` and `uploaded` leads interactively:

```bash
# Re-review approved leads (change source, add local audio, or set template)
python 3a_review_leads.py --interactive --status approved

# Re-review uploaded leads (change final URL or template if you uploaded manually)
python 3a_review_leads.py --interactive --status uploaded
```

## Step 4: Draft Emails

```bash
# Interactive mode - review each email before approval
python 4_draft_emails.py --interactive --permission

```

## Step 5: Review Drafts (MANUAL)

```bash
# Approve all
python manage_leads.py approve-all
```

## Step 6: Schedule & Send Emails

```bash
# ROUND-ROBIN: Alternate between all sender accounts
python 5_dispatch_emails.py --round-robin --limit 20 --date now --interval 30

```

## Step 7: Monitor Followups

```bash
python 6_check_followups.py
```