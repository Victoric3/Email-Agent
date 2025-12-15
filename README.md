# EulaIQ Outreach Pipeline

A fully automated lead generation and email outreach system for YouTube educational creators. Intelligently identifies math/science educators who could benefit from professional video animations.

---

## 🎯 Key Features

- **Parallel Lead Harvesting**: 10 concurrent channel fetches with 2-minute timeouts
- **Transcript-Based Qualification**: AI analyzes video content, not just metadata
- **Smart Filtering**: Auto-disqualifies content farms (>2500 videos) and non-English channels
- **10-Point Scoring System**: Clear, interpretable lead quality metrics
- **Dual Video Generation**: Creates 2 variations per lead for comparison
- **YouTube Upload Automation**: 20 videos/day across 4 channels
- **Email Campaign Management**: Scheduled delivery via ZeptoMail

---

## 📋 Quick Reference - New Pipeline

| Step | Script | Description |
|------|--------|-------------|
| 1 | `1_harvest_leads.py` | Search YouTube, collect creators |
| 2 | `2_refine_leads.py` | LLM qualification + scoring |
| 3a | `3a_review_leads.py` | **MANUAL:** Add emails, approve/disqualify leads |
| 3b | `3b_generate_videos.py` | Generate 2 video options per lead (5-min audio) |
| 3c | `3c_accept_videos.py` | **MANUAL:** Compare videos, select best one |
| 3d | `3d_upload_youtube.py` | Upload to YouTube (4 channels, 20/day) |
| 4 | `4_draft_emails.py` | Generate email drafts with YouTube URLs |
| 5 | **MANUAL** | Review drafts |
| 6 | `5_dispatch_emails.py` | Schedule and send via ZeptoMail |
| 7 | `6_check_followups.py` | Monitor followup schedule |

---

## 🚀 Full Production Workflow

### Prerequisites

```bash
cd "c:\Users\pharm victor\Desktop\company files\Emails\scripts\outreach"

# Install dependencies
pip install -r ../../requirements.txt

# Copy .env.example to .env and fill in your secrets
cp ../../.env.example ../../.env
```

**Required tools:**
- Python 3.10+
- ffmpeg (for audio trimming)
 - yt-dlp (for metadata & YouTube info extraction)
- MongoDB Atlas account
- EulaIQ accounts (for video generation)
- YouTube channels with API credentials
- ZeptoMail account (for email sending)

---

## Step 1: Harvest Leads

```bash
python 1_harvest_leads.py --limit 5
```

**Features:**
- Searches YouTube for educational videos based on keywords
- **Parallel processing**: Fetches 10 channels simultaneously with 2-minute timeout (configurable)
- Extracts channel info and subscriber counts
- Fetches video count per channel
- **Auto-disqualifies** channels with >2500 videos (content farms)

**CLI Flags:**
- `--limit, -l`: Number of keywords to process from `keywords.txt` (example: `--limit 5`)
- `--skip-stats, -s`: Skip channel stat fetching (faster, less metadata)
- `--parallel, -p`: Number of concurrent channel fetch workers (default: 10)
- `--timeout, -t`: Timeout in seconds per batch (default: 120)

**Configuration:**
- `PARALLEL_WORKERS = 10` - Concurrent channel fetches (default)
- `CHANNEL_FETCH_TIMEOUT = 120` - 2-minute timeout per channel batch (default)
- `MAX_VIDEO_COUNT = 2500` - Content farm threshold

**Example:**
```bash
# Harvest 5 keywords, use 15 parallel workers and 3-minute timeout per batch
python 1_harvest_leads.py --limit 5 --parallel 15 --timeout 180
```

**Output:** Leads saved to MongoDB with status `harvested`

---

## Step 2: Refine & Qualify Leads

```bash
python 2_refine_leads.py --limit 20
```

**Features:**
- Uses Claude LLM to analyze each lead
- **Parallel async processing**: 10 leads at a time (configurable via `--batch-size`)
- **Transcript analysis**: Fetches and analyzes video transcript for content fit
- **10-point scoring system** (pass threshold: 6/10)
- **Auto-disqualifies** non-English channels (configurable)
- **Auto-disqualifies** channels with >2500 videos

**CLI Flags:**
- `--limit, -l`: Limit number of harvested leads to process
- `--test-email`: Override all discovered emails with a test address (useful for testing)
- `--english-only`: Enforce English-only filtering (default: enabled)
- `--no-english-only`: Allow non-English channels
- `--calculation-focus`: Prefer calculation-heavy content (math proofs, equations)
- `--batch-size, -b`: Number of leads processed in parallel (default: 5)

**Scoring Breakdown (10 points max):**
- Base: 2 points
- Subscriber tier: 0-2 points (sweet_spot=2, big=1, small=1)
- Content fit: 0-2 points (from transcript analysis)
- Visual need: 0-2 points (needs diagrams/equations)
- Production gap: 0-1 point (room for improvement)
- Language: 0-1 point (English=1, European languages=0, other=disqualify)
- Email available: 0-1 point

**Configuration:**
- `ENGLISH_ONLY = True` - Auto-disqualify non-English channels (default)
- `CALCULATION_FOCUS = False` - Not targeting calc-only channels (default)
- `MIN_FINAL_SCORE = 6` - Pass threshold out of 10
- `MAX_VIDEO_COUNT = 2500` - Content farm threshold

**Example:**
```bash
# Refine 30 leads, process 10 at a time and prioritize calculation content
python 2_refine_leads.py --limit 30 --batch-size 10 --calculation-focus
```

**Output:** Status changes to `qualified` or `disqualified`

---

## Step 3a: Manual Lead Review (Add Emails)

This is where YOU review leads, find their emails, and approve for video generation.

### Option A: Export/Import (Recommended)

```bash
# Export qualified leads to JSON
python 3a_review_leads.py --export --limit 20

# This creates: review_queue/review_queue_[timestamp].json
```

Edit the JSON file:
- Add `email` for each lead (find on their channel About page, socials, etc.)
- Set `decision` to `approve` or `disqualify`
- Add `disqualify_reason` if rejecting

```bash
# Import your decisions
python 3a_review_leads.py --import review_queue_2025-12-08_143022.json
```

### Option B: Interactive Mode

```bash
python 3a_review_leads.py --interactive
```

Review leads one-by-one in terminal with extended commands:

| Command | Action |
|---------|--------|
| `a` | **Approve** - Enter email address and optional notes |
| `d` | **Disqualify** - Enter reason for rejection |
| `s` | **Skip** - Move lead to end of queue for later |
| `v` | **Change Video** - Enter new YouTube URL for source video |
| `l` | **Local Audio** - Provide path to custom audio file |
| `n` | **Update Name** - Manually set or correct the creator's name (used in email greeting) |
| `q` | **Quit** - Exit review mode |

**Notes Field:** When approving, you can add notes that will be used by the LLM to personalize the email draft.

**Creator Name Fallback:** If `creator_name` was not discovered during harvest/refine (or is generic like `Unknown`), the interactive review and drafting scripts will attempt to fetch channel metadata using the channel URL to fill in the name automatically. Use the `n` command during interactive review to correct or override the fetched name before finalizing the draft.

**Change Video:** If the selected source video isn't ideal, provide a different YouTube URL from the same creator.

**Local Audio:** If you recorded custom audio for this lead, provide the file path. The audio filename will be used as the video title.
> Note: If we couldn't find a suitable audio track on the creator's channel, a local audio may be an AI-generated lecture created by our team to demonstrate the concept for the animation. The draft emails will explain this clearly to the creator so they understand the provenance of the voiceover.

**Output:** Approved leads move to status `approved`

### Modifying Approved Leads

If you need to change the video, add local audio, or set the final video URL for a lead you've **already approved** (but haven't generated videos for yet), use the `--status` flag. You can now review both `approved` and `uploaded` leads interactively:

```bash
# Re-review approved leads (change source, add local audio, or set template)
python 3a_review_leads.py --interactive --status approved

# Re-review uploaded leads (change final URL or template if you uploaded manually)
python 3a_review_leads.py --interactive --status uploaded
```

In interactive mode these additional commands are available when reviewing `approved` or `uploaded` leads:

| Command | Action |
|---------|--------|
| `t` | Change or set the `video_to_generate` template (useful if you want to alter the animation style before generating) |
| `f` | Set the final unlisted YouTube URL for the lead (enter the video URL). When you set this, the lead's `status` is updated to `uploaded` automatically. |
| `v` | Change the source video URL used to generate the video (remixes the audio from a different source) |
| `l` | Assign a local audio file path (for manual audio) |
| `n` | Update the recorded creator name in the lead (handy if the name is missing or generic). |

Notes:
- `f` is intended for the case where you uploaded the final video manually (or used another workflow) and need to record the final YouTube link in the lead document.
- `t` allows you to change which template or video style the generator should use for that particular lead.
- These commands are available when `--status` is `approved` or `uploaded` so you can make final changes before drafting/sending.

---

## Step 3b: Generate Dual Videos

```bash
python 3b_generate_videos.py --limit 10
```

For each approved lead:
1. **Checks for local audio path** - If you provided custom audio in 3a, uses that file
2. Otherwise, downloads audio from YouTube
3. **Trims to first 5 minutes** using ffmpeg
4. Generates **2 video variations** simultaneously using different EulaIQ accounts
5. Stores both URLs for comparison

**Local Audio Support:** If you provided a `local_audio_path` during review (step 3a), the script uses that audio file directly instead of downloading from YouTube. The video title will be taken from the audio filename.
> Note: In many cases where the original channel audio doesn't fit our animation pipeline, we create an AI-generated lecture/voiceover to demonstrate the animated concept. This local audio is meant to be a conceptual demo, and the email templates will explain that it is a demo generated from the creator's content (not a misrepresentation of the creator's real voice).

**Export Audios for Manual Generation:** If you prefer to download and prepare audios for manual editing or external generation, use the `export_audios.py` script. It will download/trim audio for all `approved` leads into a dated folder under `audios/`.

```bash
python export_audios.py
# Exports trimmed mp3s to: audios/YYYY-MM-DD/
```

**Output:** Status changes to `asset_pending_review`

**Time:** ~15-30 minutes per lead (videos generated in parallel)

---

## Step 3c: Accept Videos (Choose Best)

### Option A: Interactive Mode (Recommended)

```bash
python 3c_accept_videos.py --interactive
```

For each lead:
- Opens both video URLs in browser
- You compare and select `a`, `b`, `custom`, or `regenerate`

### Option B: Export/Import

```bash
# Export for review
python 3c_accept_videos.py --export

# Edit JSON with selections
# Import decisions
python 3c_accept_videos.py --import video_review_2025-12-08_150000.json
```

**Selection options:**
- `a` - Use Video A
- `b` - Use Video B
- `custom` - Provide your own URL (if you generated manually)
- `regenerate` - Send back for new generation
- `reject` - Disqualify the lead

**Output:** Approved leads move to status `asset_approved`

---

## Step 3d: Upload to YouTube

```bash
# Check upload capacity
python 3d_upload_youtube.py --status

# Upload approved videos
python 3d_upload_youtube.py --limit 20
```

Videos are uploaded as **unlisted** to your YouTube channels:
- Uses 4 channels in round-robin
- 5 videos per channel per day = 20 total daily capacity
- Automatically tracks daily limits

**First-time setup:** See `docs/getYoutubeCredentials.md`

**Output:** Status changes to `uploaded`, YouTube URL saved

---

## Step 4: Draft Emails

This step drafts personalized emails for leads that are in the `uploaded` status (final video available). If you have videos still in `asset_generated` or `asset_pending_review`, run `3c_accept_videos.py` and/or `3d_upload_youtube.py` to finalize the video first.

```bash
# Interactive mode - review each email before approval
python 4_draft_emails.py --interactive

# Batch mode - generate all drafts without review
python 4_draft_emails.py --batch --limit 20
```

### Interactive Mode (Recommended)

For each lead, the script:
1. **Generates personalized email** using LLM (Claude via AWS Bedrock)
2. **Uses notes field** from lead review for personalization
3. Displays the draft for your review

**Creator Name Fallback**: If a lead does not have a valid `creator_name` (for example, the harvester found a generic or missing title), `4_draft_emails.py` will attempt to fetch the channel metadata using the creator's channel URL and populate the `creator_name` automatically. You can still manually update the name during interactive review using the `n` command — this updates the lead document in the DB.

**Local Audio in Drafts (AI-generated demos)**: If the lead uses a `local_audio_path` (or we exported/imported an audio file), the system treats it as a demonstration track. In many cases this audio is an AI-generated lecture or conceptual voiceover created to show how an animation would look, rather than a direct copy of the creator's own audio. The email drafts will explicitly explain this (so creators understand that the demo is conceptual and meant to show possibilities, not to misrepresent the original creator's voice).

**Commands:**
| Command | Action |
|---------|--------|
| `a` | **Approve** - Set schedule time and save draft |
| `e` | **Edit** - Directly modify subject and body |
| `r` | **Reprompt** - Ask LLM to modify (e.g., "make it shorter", "add humor") |
| `s` | **Skip** - Skip for now |
| `n` | **Update Name** - Edit the creator name (updates DB). Use `[r]` to regenerate a draft with the new name. |
| `q` | **Quit** - Exit review mode |

**Scheduling:** When approving, enter:
- Minutes offset from now (e.g., `60` for 1 hour)
- Specific datetime (e.g., `2025-12-10 14:30`)
- Press Enter for default slot

**Output:** Status changes to `drafted`

---

## Step 5: Review Drafts (MANUAL)

```bash
# View all drafts
python manage_leads.py drafts

# View single draft in full
python manage_leads.py show-draft <channel_id>

# Approve for sending
python manage_leads.py approve <channel_id>

# Approve all
python manage_leads.py approve-all
```

---

## Step 6: Schedule & Send Emails

```bash
# Send 10 emails using sender 1, 30 min apart
python 5_dispatch_emails.py --email 1 --limit 10 --date now --interval 30

# ROUND-ROBIN: Alternate between all sender accounts
python 5_dispatch_emails.py --round-robin --limit 10 --date now --interval 30

# Schedule for tomorrow
python 5_dispatch_emails.py --email 2 --limit 10 --date tomorrow --interval 60

# Preview schedule (dry run)
python 5_dispatch_emails.py --email 1 --limit 5 --dry-run
```

**Round-Robin Mode:** Use `--round-robin` or `-rr` to automatically alternate emails between all configured sender accounts. This distributes the sending load across accounts evenly.

**Output:** Status changes to `sent`

---

## Step 7: Monitor Followups

```bash
python 6_check_followups.py
```

---

## 🛠️ Management Commands

```bash
# View stats
python manage_leads.py stats

# List leads by status
python manage_leads.py list --status approved
python manage_leads.py list --status uploaded

# Search leads
python manage_leads.py search "3blue"

# Set email manually
python manage_leads.py set-email <channel_id> email@example.com

# Record reply
python manage_leads.py reply <channel_id> "They said yes!"
```

### Utility Scripts

```bash
# Delete all harvested/qualified leads (fresh start)
python delete_leads.py

# Generate OAuth tokens for YouTube channels
python get_youtube_token.py
```

---

## 📊 Lead Statuses (New Flow)

| Status | Meaning |
|--------|---------|
| `harvested` | Just found, needs LLM refinement |
| `qualified` | Passed LLM check, needs manual review |
| `approved` | Manually approved with email, ready for video |
| `disqualified` | Rejected at any stage |
| `asset_generating` | Video generation in progress |
| `asset_pending_review` | 2 videos ready, awaiting selection |
| `asset_approved` | Video selected, ready for YouTube |
| `uploaded` | On YouTube, ready for email draft |
| `drafted` | Email ready for review |
| `ready_to_send` | Approved, will be sent |
| `sent` | Email sent |
| `followup_1-4` | Followup emails sent |
| `replied` | Creator responded |
| `converted` | Deal closed |

---

## 📝 Example: Daily Production Run

```bash
cd "c:\Users\pharm victor\Desktop\company files\Emails\scripts\outreach"

# Morning: Harvest & Refine (parallel processing - ~30 min)
python 1_harvest_leads.py --limit 5          # 10 channels at a time
python 2_refine_leads.py --limit 30          # Transcript analysis + LLM scoring

# Morning: Review leads, add emails (15-20 min)
# Use skip/video/local commands as needed
python 3a_review_leads.py --interactive
# To re-review approved or uploaded leads and set templates/final URLs:
python 3a_review_leads.py --interactive --status approved
python 3a_review_leads.py --interactive --status uploaded

# Late Morning: Generate videos (runs for ~2 hours)
# Automatically handles local audio if provided
python 3b_generate_videos.py --limit 10      # Dual video generation
# Optionally prepare audios for manual generation or offline review
python export_audios.py  # Exports trimmed audio files to audios/YYYY-MM-DD/

# Afternoon: Review generated videos (10-15 min)
python 3c_accept_videos.py --interactive

# Afternoon: Upload to YouTube
python 3d_upload_youtube.py                   # 20/day capacity

# Afternoon: Draft emails with LLM + review
python 4_draft_emails.py --interactive       # Approve/edit/reprompt each email

# Evening: Schedule emails (round-robin between senders)
python 5_dispatch_emails.py --round-robin --limit 10 --date tomorrow --interval 60

# Daily: Check for replies
python 6_check_followups.py
```

**Expected throughput:**
- Harvest: ~50 channels/hour (parallel processing)
- Refine: ~20 leads/hour (with transcript analysis)
- Videos: 10 leads/2 hours (dual generation)
- Uploads: 20 videos/day (YouTube limits)
- Emails: 50/day per sender (ZeptoMail limits)

---

## 🔐 Security & Secrets

All secrets go in `.env` (never committed to git):

```env
MONGODB_URI=mongodb+srv://...
EULAIQ_ACCOUNTS=[...]
SMTP_ACCOUNTS=[...]
YOUTUBE_CHANNELS=[...]
AWS_API_KEY=...
```

See `.env.example` for format. See `docs/getYoutubeCredentials.md` for YouTube setup.

---

## 📁 Directory Structure

```
Emails/
├── .env                    # Your secrets (git-ignored)
├── .env.example           # Template
├── requirements.txt
├── keywords.txt           # 120+ targeted search terms
├── used_keywords.txt      # Tracking used keywords
├── credentials/           # OAuth tokens (git-ignored)
├── assets/
│   ├── audio/            # Downloaded audio
│   ├── audio_trimmed/    # 5-min trimmed audio
│   └── videos_for_upload/ # Downloaded videos
├── review_queue/         # Lead review JSONs
├── video_review/         # Video selection JSONs
├── scripts/
│   └── outreach/
│       ├── 1_harvest_leads.py       # Parallel YouTube harvesting
│       ├── 2_refine_leads.py        # LLM + transcript qualification
│       ├── 3a_review_leads.py       # Manual email addition
│       ├── 3b_generate_videos.py    # Dual video generation
│       ├── 3c_accept_videos.py      # Video selection
│       ├── 3d_upload_youtube.py     # YouTube automation
│       ├── 4_draft_emails.py        # Email generation
│       ├── 5_dispatch_emails.py     # Email sending
│       ├── 6_check_followups.py     # Followup monitoring
│       ├── manage_leads.py          # Lead management CLI
│       ├── get_youtube_token.py     # OAuth token generator
│       └── delete_leads.py          # Utility: clear DB
└── docs/
    ├── getYoutubeCredentials.md     # YouTube API setup
    └── pipeline_guide.md            # Detailed workflow
```

---

## ⚠️ Daily Limits & Performance

| Service | Limit | Notes |
|---------|-------|-------|
| YouTube uploads | 20/day | 5 per channel × 4 channels |
| EulaIQ videos | ~90/day | 30 per account × 3 accounts |
| ZeptoMail emails | 50/day | Per sender account |
| Bedrock LLM calls | Variable | Based on AWS quota |
| Harvest rate | ~50/hour | 10 parallel workers |
| Refinement rate | ~20/hour | Includes transcript fetch + LLM |

**Performance Tips:**
- Run harvesting overnight for large batches
- Use `--limit` flags to control processing size
- Monitor `PARALLEL_WORKERS` and `CHANNEL_FETCH_TIMEOUT` in scripts
- Check MongoDB for bottlenecks if refinement slows down

---

## 🔧 Requirements

- Python 3.10+
- ffmpeg (install: `choco install ffmpeg` on Windows)
- MongoDB Atlas account
- Google Cloud project with YouTube API
- ZeptoMail account
- EulaIQ accounts
