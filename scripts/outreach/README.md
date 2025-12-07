# EulaIQ Outreach Pipeline

A fully automated lead generation and email outreach system for YouTube educational creators.

---

## 📋 Quick Reference

| Step | Script | Description |
|------|--------|-------------|
| 1 | `1_harvest_leads.py` | Search YouTube, collect creators |
| 2 | `2_refine_leads.py` | LLM qualification + scoring |
| 3 | `3_export_for_manual.py` | Export leads for manual video generation |
| 3b | **MANUAL** | Generate videos yourself via EulaIQ |
| 3c | `3_export_for_manual.py --update` | Update URLs after generating |
| 4 | `4_draft_emails.py` | Fill template with lead data |
| 5 | **MANUAL** | Review drafts + Add emails |
| 6 | `5_dispatch_emails.py` | Send via ZeptoMail |
| 7 | `6_check_followups.py` | Monitor followup schedule |

**Alternative Step 3 (Automated):**
| Step | Script | Description |
|------|--------|-------------|
| 3 | `3_generate_assets.py` | Auto-generate videos via EulaIQ API |

---

## 🚀 Full Production Workflow

### Prerequisites
```bash
cd "c:\Users\pharm victor\Desktop\company files\Emails\scripts\outreach"
```

---

## Step 1: Harvest Leads

**What it does:** Searches YouTube for educational videos, extracts channel info, gets subscriber counts via yt-dlp.

```bash
# Harvest leads from 5 keywords (recommended batch size)
python 1_harvest_leads.py --limit 5

# Harvest from 10 keywords
python 1_harvest_leads.py --limit 10

# Custom keywords file (default: keywords.txt)
python 1_harvest_leads.py --limit 5 --keywords my_keywords.txt
```

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `--limit` | 10 | Number of keywords to process |
| `--keywords` | `keywords.txt` | Path to keywords file |

**Output:** Leads saved to MongoDB with status `harvested`

**Timing:** ~3 seconds per video found (yt-dlp calls)

---

## Step 2: Refine & Qualify Leads

**What it does:** Uses Claude LLM to analyze each lead for Manim compatibility, content quality, language, etc.

```bash
# Refine all harvested leads
python 2_refine_leads.py

# Refine limited batch (for testing or daily limits)
python 2_refine_leads.py --limit 20

# Set minimum score threshold (default: 12)
python 2_refine_leads.py --min-score 14
```

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `--limit` | None | Max leads to process |
| `--min-score` | 12 | Minimum ICP score to qualify (max 22) |

**Scoring System (Max 22 points):**
- Base score: 5 points
- Subscriber tier: 0-3 points (sweet_spot = 3, big = 2, small = 1)
- Email available: 0-2 points
- Manim compatibility: 0-3 points
- Content depth: 0-2 points
- Visual complexity: 0-2 points
- Production quality: 0-2 points
- English language: 0-2 points
- Location bonus: 0-1 point (US/UK/Canada/Australia)

**Output:** Status changes to `qualified` or `disqualified`

---

## Step 3: Generate Video Assets

You have two options for Step 3:

### Option A: Manual Generation (Recommended)

**What it does:** Exports qualified leads to a JSON file so you can manually generate videos via EulaIQ, then update the pipeline with actual URLs.

#### Step 3a: Export Leads for Manual Processing

```bash
# Export all qualified leads
python 3_export_for_manual.py

# Export limited batch
python 3_export_for_manual.py --limit 5
```

**Output:** Creates `manual_queue/manual_queue_[timestamp].json`:
```json
{
  "exported_at": "2025-12-07_143022",
  "count": 5,
  "items": [
    {
      "channel_id": "UCxxx...",
      "creator_name": "3Blue1Brown",
      "video_id": "abc123",
      "video_url": "https://youtube.com/watch?v=abc123",
      "video_title": "The Basel Problem",
      "placeholder_url": "https://render.eulaiq.com/player/PENDING_UCxxx...",
      "generated_url": null,
      "notes": ""
    }
  ]
}
```

Status changes to `asset_generated` with placeholder URLs.

#### Step 3b: Generate Videos Manually

1. Open the JSON file from `manual_queue/`
2. For each item:
   - Go to `video_url` on YouTube
   - Generate video using EulaIQ (download audio → upload → generate)
   - Copy the resulting player URL
   - Paste into `generated_url` field in JSON

#### Step 3c: Update URLs in Pipeline

```bash
# After filling in generated_url values
python 3_export_for_manual.py --update manual_queue_2025-12-07_143022.json
```

This updates all leads with actual URLs instead of placeholders.

**⚠️ Note:** You can also proceed with placeholder URLs - emails will be drafted with `PENDING_` links that you can update later.

---

### Option B: Automated Generation

**What it does:** Automatically downloads audio from YouTube, generates animated video via EulaIQ API, creates branded player link.

```bash
# Generate assets for all qualified leads
python 3_generate_assets.py

# Limit to first N leads
python 3_generate_assets.py --limit 5

# TEST MODE - Skip real generation, use mock URLs
python 3_generate_assets.py --test-mode --limit 5
```

**Parameters:**
| Parameter | Description |
|-----------|-------------|
| `--limit` | Max leads to process |
| `--test-mode` | Skip real video generation (for testing pipeline) |

**⚠️ IMPORTANT:** Real video generation takes 10-30 minutes per video and consumes API credits.

**Output:** Status changes to `asset_generated`, `branded_player_url` saved

---

## Step 4: Draft Personalized Emails

**What it does:** Fills in the email template (`Context/template.txt`) with lead data. No LLM needed - just string replacement.

```bash
# Draft emails for all leads with assets
python 4_draft_emails.py

# Limit batch size
python 4_draft_emails.py --limit 10
```

**Template Placeholders:**
| Placeholder | Replaced With |
|-------------|---------------|
| `[Name]` | Creator's first name |
| `[Video Title]` | Source video title |
| `[Link to EulaIQ Render]` | Branded player URL |
| `[Math/Physics]` | Detected subject type |

**Parameters:**
| Parameter | Description |
|-----------|-------------|
| `--limit` | Max drafts to create |

**Output:** Status changes to `drafted`, email saved to `draft_email` field

---

## Step 5: Review Drafts & Add Emails (MANUAL)

⚠️ **This is where YOU manually add email addresses since they're collected separately.**

### 5.1 View All Drafts

```bash
# View all drafted emails for review
python manage_leads.py drafts
```

This shows:
- Creator name
- Channel ID
- Current email (or "NO EMAIL")
- Subject line
- Body preview (first 300 chars)

### 5.2 View Single Draft (Full)

```bash
# See complete email for one lead
python manage_leads.py show-draft <channel_id>
```

### 5.3 Add Email Addresses

**Option A: One at a time**
```bash
python manage_leads.py set-email <channel_id> creator@example.com
```

**Option B: Bulk import from JSON (Recommended)**

1. First, export leads to a JSON file:
```bash
# Export all drafted leads
python manage_leads.py export-for-emails

# Export only leads missing emails
python manage_leads.py export-for-emails --missing-only

# Custom output file
python manage_leads.py export-for-emails -o my_leads.json
```

2. This creates `emails_to_collect.json`:
```json
[
  {
    "channel_id": "UCMsV0e2CLuzL7TyngBKvRTQ",
    "channel_name": "3Blue1Brown",
    "creator_name": "Grant",
    "youtube_url": "https://youtube.com/watch?v=...",
    "video_title": "The Basel Problem",
    "video_url": "",
    "email": ""
  }
]
```

3. **Fill in the editable fields:**
   - `email` - Creator's email address
   - `video_url` - Your EulaIQ render link (e.g., `https://render.eulaiq.com/player/xxx`)
   - `video_title` - Can be edited if needed (used in email subject/body)

4. Import the updates:
```bash
python manage_leads.py import-emails emails_to_collect.json
```

5. **If you updated `video_url` or `video_title`**, regenerate the email drafts:
```bash
python 4_draft_emails.py --redraft
```

**Alternative JSON format** (email only, simpler):
```json
{
  "UCMsV0e2CLuzL7TyngBKvRTQ": "grant@3b1b.com",
  "UC123...": "dianna@physicsgirl.com"
}
```

### 5.4 Approve Drafts for Sending

```bash
# Approve a single lead
python manage_leads.py approve <channel_id>

# Approve ALL drafted leads that have emails (with confirmation)
python manage_leads.py approve-all

# Approve ALL without confirmation
python manage_leads.py approve-all --force
```

**Output:** Status changes to `ready_to_send`

---

## Step 6: Dispatch Emails

**What it does:** Sends emails via ZeptoMail SMTP with scheduling control.

```bash
# Send 5 emails now, 30 minutes apart, via eulaiq.com
python 5_dispatch_emails.py --email 1 --limit 5 --date now --interval 30

# Schedule 10 emails for tomorrow, 1 hour apart, via eulaiq.me
python 5_dispatch_emails.py --email 2 --limit 10 --date tomorrow --interval 60

# Test: Send to your email (no status updates)
python 5_dispatch_emails.py --email 1 --limit 3 --date now --interval 5 --test-email your@email.com

# Preview schedule without sending
python 5_dispatch_emails.py --email 1 --limit 5 --date now --interval 30 --dry-run

# View saved schedule
python 5_dispatch_emails.py --show-schedule

# Resume interrupted schedule
python 5_dispatch_emails.py --resume
```

**Parameters:**
| Parameter | Description |
|-----------|-------------|
| `--email 1` | Use victor@eulaiq.com |
| `--email 2` | Use victor@eulaiq.me |
| `--limit N` | Max emails to send |
| `--date` | `now`, `tomorrow`, or `YYYY-MM-DD HH:MM` |
| `--interval N` | Minutes between emails (default: 60) |
| `--dry-run` | Preview without sending |
| `--test-email` | Send all to this address (for testing) |
| `--show-schedule` | View saved schedule |
| `--resume` | Resume interrupted schedule |

**Output:** Status changes to `sent`, followup scheduled for +3 days

**Sender Accounts (Round Robin):**
- victor@eulaiq.com
- victor@eulaiq.me

---

## Step 7: Check Followups

**What it does:** Shows leads that need followup attention.

```bash
python 6_check_followups.py
```

---

## 🛠️ Management Commands

The `manage_leads.py` script provides a full CLI for managing leads:

```bash
# View pipeline statistics
python manage_leads.py stats

# List all leads
python manage_leads.py list

# List by status
python manage_leads.py list --status qualified
python manage_leads.py list --status drafted
python manage_leads.py list --status sent

# Show full details for one lead
python manage_leads.py show <channel_id>

# Search leads by name/channel
python manage_leads.py search "3blue"

# Set email
python manage_leads.py set-email <channel_id> email@example.com

# View drafts for review
python manage_leads.py drafts

# View single draft (full)
python manage_leads.py show-draft <channel_id>

# Approve single draft
python manage_leads.py approve <channel_id>

# Approve all drafts with emails
python manage_leads.py approve-all

# Record that creator replied
python manage_leads.py reply <channel_id> "They said yes!"

# Add note to lead
python manage_leads.py note <channel_id> "Interested in Pro plan"

# Manually set status
python manage_leads.py status <channel_id> converted

# Delete lead
python manage_leads.py delete <channel_id>
```

---

## 📊 Lead Statuses

| Status | Meaning |
|--------|---------|
| `harvested` | Just found, needs refinement |
| `qualified` | Passed LLM check, ready for assets |
| `disqualified` | Didn't pass LLM check |
| `asset_generating` | Video being created |
| `asset_generated` | Video ready, needs email draft |
| `drafted` | Email written, needs review |
| `ready_to_send` | Approved, will be sent |
| `sent` | Initial email sent |
| `followup_1-4` | Followup sent |
| `replied` | Creator responded |
| `converted` | Deal closed |
| `unsubscribed` | Opt-out |
| `dead` | No response after all followups |

---

## 📝 Example: Full Production Run

### Option A: Manual Video Generation (Recommended)

```bash
# Day 1: Harvest new leads
cd "c:\Users\pharm victor\Desktop\company files\Emails\scripts\outreach"
python 1_harvest_leads.py --limit 5

# Day 1: Refine/qualify leads
python 2_refine_leads.py --limit 30

# Day 1: Check what we have
python manage_leads.py stats

# Day 1: Export leads for manual video generation
python 3_export_for_manual.py --limit 10
# → Creates manual_queue/manual_queue_[timestamp].json

# Day 1-2: MANUALLY generate videos
# - Open the JSON file
# - For each lead, go to video_url and generate via EulaIQ
# - Fill in generated_url field with actual player link

# Day 2: Update pipeline with actual URLs
python 3_export_for_manual.py --update manual_queue_2025-12-07_143022.json

# Day 2: Draft emails
python 4_draft_emails.py --limit 10

# Day 2: Review all drafts
python manage_leads.py drafts

# Day 2: Add emails you collected
python manage_leads.py set-email UC123... email1@example.com
python manage_leads.py set-email UC456... email2@example.com

# Day 2: Approve all that have emails
python manage_leads.py approve-all

# Day 2: Send!
python 5_dispatch_emails.py

# Daily: Check for replies and followups
python 6_check_followups.py
```

### Option B: Automated Video Generation

```bash
# Day 1: Harvest new leads
cd "c:\Users\pharm victor\Desktop\company files\Emails\scripts\outreach"
python 1_harvest_leads.py --limit 5

# Day 1: Refine/qualify leads
python 2_refine_leads.py --limit 30

# Day 1: Check what we have
python manage_leads.py stats

# Day 1: Generate video assets automatically (takes time!)
python 3_generate_assets.py --limit 10

# Day 2: Draft emails
python 4_draft_emails.py --limit 10

# Day 2: Review all drafts
python manage_leads.py drafts

# Day 2: Add emails you collected
python manage_leads.py set-email UC123... email1@example.com
python manage_leads.py set-email UC456... email2@example.com

# Day 2: Approve all that have emails
python manage_leads.py approve-all

# Day 2: Send!
python 5_dispatch_emails.py

# Daily: Check for replies and followups
python 6_check_followups.py
```

---

## ⚠️ Important Notes

1. **Email Collection is Manual**: The pipeline does NOT automatically find email addresses. You must manually research and add them via `manage_leads.py set-email`.

2. **Daily Limits**: 
   - Dispatch: 20 emails/day max
   - Video Generation: ~90 videos/day across 3 accounts

3. **API Costs**:
   - Bedrock (Claude): ~$0.01-0.03 per lead refinement (Step 2 only)
   - EulaIQ: Video generation counts against your plan
   - Email drafting: **FREE** (template replacement, no LLM)

4. **Rate Limiting**: Built-in delays prevent API blocks:
   - YouTube search: 0.3s between calls
   - Bedrock: 0.5s between LLM calls

5. **Always Review Drafts**: Use `python manage_leads.py drafts` before approving to catch any issues.

## 🔐 Security & Secrets

- Store API keys, database connection strings, and account passwords in a local `.env` file, not in source files.
- Copy `.env.example` to `.env` and fill in your secrets. The `.env` file is already ignored by `.gitignore`.
- **All scripts require environment variables** to be set. The scripts will **fail immediately** if `MONGODB_URI`, `EULAIQ_ACCOUNTS`, or `SMTP_ACCOUNTS` are not defined in `.env`.
- A pre-commit hook is provided as a sample at `hooks/pre-commit.sample` that scans staged files for common secret patterns (e.g. tokens, private keys, mongodb+srv) and blocks commits containing them. To enable it locally copy the file to `.git/hooks/pre-commit` and make it executable.
 - For convenience, a repo scanner is provided at `scripts/scan_secrets.py`. Run this before committing or as part of your CI checks.
   ```bash
   python scripts/scan_secrets.py
   ```

 - Install the sample hook to quickly block accidental commits with secrets (use your shell):
   ```bash
   cp hooks/pre-commit.sample .git/hooks/pre-commit
   chmod +x .git/hooks/pre-commit
   ```

---

## 🔧 Configuration Files

- `keywords.txt` - YouTube search keywords (one per line)
- `used_keywords.txt` - Keywords already used (auto-managed)
- `Context/company_context.txt` - Your company pitch for email drafts
- `Context/template.txt` - Email template structure

---

## 📁 MongoDB Structure

Database: `eulaiq_outreach`  
Collection: `leads`

Each lead document contains:
```json
{
  "channel_id": "UCxxx...",
  "channel_name": "3Blue1Brown",
  "creator_name": "Grant Sanderson",
  "email": "contact@example.com",
  "source_video": { "video_id": "...", "title": "..." },
  "channel_stats": { "subscriber_count": 5000000 },
  "icp_score": 18,
  "icp_analysis": { "manim_compatibility": "excellent", ... },
  "status": "drafted",
  "branded_player_url": "https://render.eulaiq.com/...",
  "draft_email": { "subject": "...", "body": "..." },
  "sent_email": { "subject": "...", "sent_at": "..." },
  "conversation_history": [...],
  "created_at": "2025-12-05T...",
  "updated_at": "2025-12-05T..."
}
```
