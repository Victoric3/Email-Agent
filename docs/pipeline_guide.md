# EulaIQ Automated Outreach Pipeline v2.0

## Overview
A fully automated, MongoDB-backed pipeline for identifying, qualifying, and reaching out to YouTube educational creators. This system acts as your "brain storage" for all creator interactions.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         MONGODB                                  │
│   (eulaiq_outreach.leads - Single Source of Truth)              │
│                                                                  │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│   │ qualified│→ │  asset   │→ │ drafted  │→ │  sent    │       │
│   │          │  │ generated│  │          │  │          │       │
│   └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                   ↓             │
│                              ┌──────────────────────────────┐   │
│                              │   FOLLOWUP LOOP (3,7,10,15)  │   │
│                              │   followup_1 → ... → replied │   │
│                              └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Lead Document Schema

```javascript
{
  // Identity
  "channel_id": "UC123...",           // YouTube channel ID (unique key)
  "channel_name": "MathGuru",
  "creator_name": "John",
  "email": "john@example.com",
  
  // Video Context
  "video_id": "abc123",
  "video_title": "Calculus Made Easy",
  "video_url": "https://youtube.com/watch?v=...",
  "video_description": "...",
  
  // Qualification
  "icp_score": 9,                     // 1-10 ICP fit score
  "icp_reason": "Perfect math tutorial...",
  "keyword_source": "calculus tutorial",
  
  // Pipeline Status
  "status": "sent",                   // Current stage
  
  // Generated Asset
  "branded_player_url": "https://render.eulaiq.com/player/...",
  "s3_video_url": "https://...",
  "eulaiq_video_id": "vid_123",
  
  // Outreach
  "draft_email": {
    "subject": "...",
    "body": "...",
    "drafted_at": ISODate("...")
  },
  "sent_email": {
    "subject": "...",
    "body": "...",
    "sent_at": ISODate("..."),
    "sent_via": "victor@eulaiq.com"
  },
  
  // Followup Management
  "reached_out_at": ISODate("..."),   // When initial email sent
  "next_followup_date": ISODate("..."), // When to send next followup
  "followup_count": 1,                // Number of followups sent
  "followup_thread": [                // History of all followups
    {
      "date": ISODate("..."),
      "type": "initial_outreach",
      "content": {...},
      "response": null
    }
  ],
  
  // Conversation History (for replies)
  "conversation_history": [
    {
      "date": ISODate("..."),
      "direction": "inbound",         // or "outbound"
      "content": "Thanks for reaching out..."
    }
  ],
  
  // Timestamps
  "created_at": ISODate("..."),
  "updated_at": ISODate("..."),
  
  // Notes
  "notes": "[2025-12-03] Called, left voicemail..."
}
```

---

## Pipeline Scripts

### 1. Harvest Leads (`1_harvest_leads.py`)
**Purpose:** Scrape YouTube for potential leads using keywords.

```bash
python scripts/outreach/1_harvest_leads.py
```

**What it does:**
- Uses `scrapetube` to search YouTube by keywords
- Deduplicates against local `leads_db.json`
- Saves raw leads to `data/raw_leads_YYYY-MM-DD.json`

**Configuration:**
Edit the `KEYWORDS` list in the script to target your ICP:
```python
KEYWORDS = [
    "GCE math prep",
    "calculus tutorial",
    "physics derivation",
    ...
]
```

---

### 2. Refine & Qualify (`2_refine_leads.py`)
**Purpose:** Use AI to score leads and save qualified ones to MongoDB.

```bash
python scripts/outreach/2_refine_leads.py
```

**What it does:**
- Reads latest `raw_leads_*.json`
- Uses Bedrock (Claude) to score each lead 1-10
- Extracts creator name and email (if found)
- Saves leads with score ≥ 7 to MongoDB
- Skips channels already in database

---

### 3. Generate Assets (`3_generate_assets.py`)
**Purpose:** Create animated videos for qualified leads.

```bash
python scripts/outreach/3_generate_assets.py
python scripts/outreach/3_generate_assets.py --limit 10  # Process only 10
```

**What it does:**
1. Downloads audio from YouTube video via `yt-dlp`
2. Authenticates with EulaIQ API (round-robin across 3 accounts)
3. Triggers video generation
4. Polls for completion (up to 30 min)
5. Registers branded player link
6. Updates MongoDB with asset URLs

**Capacity:**
- 3 Pro accounts × 30 videos/day = **90 videos/day max**

---

### 4. Draft Emails (`4_draft_emails.py`)
**Purpose:** Generate personalized email drafts using AI.

```bash
python scripts/outreach/4_draft_emails.py
python scripts/outreach/4_draft_emails.py --limit 20
python scripts/outreach/4_draft_emails.py --redraft UC123 --instructions "Make it shorter"
```

**What it does:**
- Fetches leads with `status: asset_generated`
- Uses Bedrock to generate personalized email
- Saves draft to MongoDB (`draft_email` field)
- Updates status to `drafted`

---

### 5. Dispatch Emails (`5_dispatch_emails.py`)
**Purpose:** Send approved emails via ZeptoMail.

```bash
python scripts/outreach/5_dispatch_emails.py --dry-run  # Preview first
python scripts/outreach/5_dispatch_emails.py            # Send all ready
python scripts/outreach/5_dispatch_emails.py --single UC123  # Send one
```

**What it does:**
- Fetches leads with `status: ready_to_send`
- Sends via ZeptoMail SMTP (rotates between domains)
- Updates MongoDB: marks as `sent`, records `reached_out_at`, schedules `next_followup_date`
- Enforces **20 emails/day** limit

**ZeptoMail Configuration:**
- `victor@eulaiq.com`
- `victor@eulaiq.me`

---

### 6. Check Followups (`6_check_followups.py`)
**Purpose:** Identify and send followup emails.

```bash
python scripts/outreach/6_check_followups.py            # Preview due followups
python scripts/outreach/6_check_followups.py --send     # Send followups
python scripts/outreach/6_check_followups.py --dry-run  # Preview email content
```

**Followup Pattern:**
| Followup # | Days After Initial | Status After |
|------------|-------------------|--------------|
| 1          | 3 days            | followup_1   |
| 2          | 7 days            | followup_2   |
| 3          | 10 days           | followup_3   |
| 4          | 15 days           | dead         |

---

### Lead Management (`manage_leads.py`)
**Purpose:** CLI tool for viewing and managing leads.

```bash
# List leads
python manage_leads.py list
python manage_leads.py list --status drafted
python manage_leads.py list --limit 100

# View lead details
python manage_leads.py show UC123456789

# Search leads
python manage_leads.py search "calculus"

# Update email
python manage_leads.py set-email UC123 newemail@gmail.com

# Approve draft for sending
python manage_leads.py approve UC123

# Record creator reply
python manage_leads.py reply UC123 "Thanks for reaching out!"

# Add note
python manage_leads.py note UC123 "Called, seems interested"

# Change status manually
python manage_leads.py status UC123 converted

# View pipeline stats
python manage_leads.py stats

# Delete lead
python manage_leads.py delete UC123
```

---

## Daily Workflow

### Morning Routine
```bash
# 1. Check if any followups are due
python 6_check_followups.py

# 2. Send followups (if any)
python 6_check_followups.py --send

# 3. Check pipeline stats
python manage_leads.py stats
```

### Afternoon (Lead Gen)
```bash
# 1. Harvest new leads
python 1_harvest_leads.py

# 2. Qualify with AI
python 2_refine_leads.py

# 3. Generate assets (takes time)
python 3_generate_assets.py --limit 20
```

### Evening (Outreach)
```bash
# 1. Draft emails
python 4_draft_emails.py

# 2. Review drafts
python manage_leads.py list --status drafted

# 3. Approve good ones
python manage_leads.py approve UC123
python manage_leads.py approve UC456
...

# 4. Send (respect 20/day limit)
python 5_dispatch_emails.py --dry-run  # Preview first
python 5_dispatch_emails.py            # Send
```

### When You Get a Reply
```bash
# Record the reply
python manage_leads.py reply UC123 "Hi Victor, this looks interesting..."

# Add notes about the conversation
python manage_leads.py note UC123 "Scheduled call for Friday 3pm"

# If they convert
python manage_leads.py status UC123 converted
```

---

## Lead Statuses

| Status | Description |
|--------|-------------|
| `qualified` | Passed AI scoring, awaiting asset generation |
| `asset_generating` | Video is being generated |
| `asset_generated` | Video ready, awaiting email draft |
| `drafted` | Email drafted, awaiting review |
| `ready_to_send` | Approved, will be sent on next dispatch |
| `sent` | Initial outreach sent |
| `followup_1` | First followup sent (day 3) |
| `followup_2` | Second followup sent (day 7) |
| `followup_3` | Third followup sent (day 10) |
| `followup_4` | Fourth followup sent (day 15) |
| `replied` | Creator responded |
| `converted` | Deal closed |
| `unsubscribed` | Asked to stop contact |
| `dead` | No response after all followups |

---

## MongoDB Connection

```text
mongodb+srv://<username>:<password>@cluster0.<region>.mongodb.net/eulaiq_outreach
```

**Collection:** `leads`

**Indexes:**
- `channel_id` (unique)
- `status`
- `next_followup_date`
- `email`

---

## Dependencies

```bash
pip install pymongo scrapetube yt-dlp requests tabulate aiohttp python-dotenv
```

**Environment Variables (`.env`):**
```
MONGODB_DEV=mongodb+srv://<username>:<password>@cluster0.<region>.mongodb.net/?appName=Cluster0
AWS_API_KEY=your_bedrock_key
```

---

## File Structure

```
scripts/
├── db_client.py              # MongoDB client & Lead model
├── aws_bedrock_client.py     # AI client for Bedrock
└── outreach/
    ├── 1_harvest_leads.py    # Scrape YouTube
    ├── 2_refine_leads.py     # AI qualification → MongoDB
    ├── 3_generate_assets.py  # Video generation
    ├── 4_draft_emails.py     # AI email drafting
    ├── 5_dispatch_emails.py  # ZeptoMail sending
    ├── 6_check_followups.py  # Followup management
    └── manage_leads.py       # CLI for lead management
data/
├── raw_leads_YYYY-MM-DD.json # Daily raw scrapes
└── leads_db.json             # Deduplication tracker
assets/
└── audio/                    # Downloaded audio files
```

---

## Tips

1. **Start small:** Test with `--limit 5` on all scripts first.
2. **Dry run:** Always use `--dry-run` before sending emails.
3. **Monitor stats:** Run `python manage_leads.py stats` daily.
4. **Record everything:** Use `reply` and `note` commands to track conversations.
5. **Respect limits:** 20 emails/day, 90 videos/day.
