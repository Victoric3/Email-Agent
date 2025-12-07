# EulaIQ Automated Outreach Pipeline Architecture

## Overview
This document details the architecture for the EulaIQ automated outreach system. The goal is to scale personalized outreach to educational creators (Math, Science, Coding) by automating lead sourcing, qualification, asset generation, and email drafting, while maintaining a high-touch "Founder-to-Founder" feel.

## Core Philosophy
*   **"The Victor Method":** High-signal, value-first outreach. We don't ask for permission; we deliver a finished asset (a full animated video) to prove value immediately.
*   **Automation with Human Oversight:** The system handles the heavy lifting (scraping, rendering, drafting), but the final "send" decision remains human to ensure quality control.
*   **Local-First Data:** Simple JSON storage avoids database complexity and allows for easy manual inspection.

---

## Pipeline Stages

### 1. Lead Harvesting (`scripts/1_harvest_leads.py`)
**Objective:** Source fresh, high-potential leads from YouTube based on specific educational keywords.

*   **Input:** List of keywords (e.g., "GCE math", "calculus derivation", "coding interview").
*   **Tool:** `scrapetube` library.
*   **Logic:**
    *   Iterate through keywords.
    *   Fetch the last ~50 videos per keyword (prioritizing active creators).
    *   **Deduplication:** Check against `data/leads_db.json` (master record of all seen channel IDs) to ensure we never spam the same creator.
*   **Output:** `data/raw_leads_[date].json` containing video ID, title, channel ID, and description.

### 2. Lead Refinement & Qualification (`scripts/2_refine_leads.py`)
**Objective:** Filter raw leads to find the "Perfect Fit" (ICP) and prepare them for outreach.

*   **Input:** `data/raw_leads_[date].json`.
*   **Tool:** `aws_bedrock_client.py` (Claude Sonnet/Opus).
*   **Logic:**
    *   **AI Analysis:** Feed channel info and video description to the LLM.
    *   **Scoring:** Rate 1-10 based on:
        *   **Topic Fit:** Is it Math/Science/Coding? (Hard filter)
        *   **Visual Potential:** Does the description imply diagrams/equations?
        *   **Vibe:** Is it educational/tutorial style?
    *   **Enrichment:**
        *   Extract Creator Name (if mentioned in description).
        *   **Manual/Heuristic Email Extraction:** Since we are self-sourcing, the script will parse descriptions for `mailto:` or patterns like `[at]gmail`. (Note: User will manually verify/add emails if missing).
    *   **Threshold:** Only leads with Score >= 7 proceed.
*   **Output:** `data/qualified_leads.json` (Appended with new qualified leads).

### 3. Asset Generation & Hosting (`scripts/3_generate_assets.py`)
**Objective:** Create the "Value Proof" – a fully animated video of their content.

*   **Input:** `data/qualified_leads.json`.
*   **Tools:** `yt-dlp`, `requests` (EulaIQ API), `ffmpeg`.
*   **Capacity:** 3 Pro Accounts (90 videos/day total).
*   **Logic:**
    1.  **Audio Extraction:** Download audio from the YouTube video using `yt-dlp`.
    2.  **Load Balancing:** Rotate between 3 EulaIQ accounts (`chukwujiobivictoric`, `kingsheartcbt`, `chukwujiobivictorif`) to distribute load.
    3.  **Generation:** Call `POST /video/createFromAudio` on EulaIQ API.
    4.  **Polling:** Wait for completion (`GET /video/status`).
    5.  **Hosting (The Pivot):** Instead of YouTube upload, we use the **EulaIQ Player API**.
        *   **Register:** Call `POST https://render.eulaiq.com/video/register` with the S3 URL from the generation step.
        *   **Branding:** Get a clean, branded URL (e.g., `render.eulaiq.com/player/calculus-intro`).
*   **Output:** Updates `data/qualified_leads.json` with the `branded_player_url`.

### 4. Email Drafting (`scripts/4_draft_emails.py`)
**Objective:** Write a hyper-personalized email that feels hand-written.

*   **Input:** `data/qualified_leads.json` (now with video links).
*   **Context:** `company_context.txt`, `template.txt`.
*   **Tool:** `aws_bedrock_client.py`.
*   **Logic:**
    *   **Prompt:** "Act as Victor. Analyze this video title/description. Write an email following the 'The Basel Problem' template structure. Replace placeholders. Mention specific details from their content to prove you watched it."
    *   **Drafting:** Generate the Subject and Body.
*   **Output:** `data/drafts/pending_[date].json`.

### 5. Review & Dispatch (`scripts/5_dispatch_emails.py`)
**Objective:** Human review followed by automated sending.

*   **Workflow:**
    1.  **Human Review:** User opens `data/drafts/pending_[date].json`, edits/approves drafts, and moves them to `data/drafts/ready_to_send.json`.
    2.  **Dispatch Script:** Reads `ready_to_send.json`.
*   **Tool:** ZeptoMail SMTP (Python `smtplib`).
*   **Configuration:**
    *   **Domains:** `eulaiq.com` (Victor), `eulaiq.me` (Victor).
    *   **Rate Limit:** Max 20 emails/day total (strict adherence).
    *   **Rotation:** Alternate between sender accounts to warm up domains.
*   **Logic:**
    *   Connect to `smtp.zeptomail.com:587`.
    *   Send email.
    *   Log success/failure.
    *   Move lead to `data/archived_leads.json`.

---

## Data Structure (JSON)

**`qualified_leads.json` Schema:**
```json
[
  {
    "lead_id": "yt_video_id",
    "channel_id": "channel_id",
    "channel_name": "MathWizard",
    "creator_name": "Gandalf",
    "email": "gandalf@math.com",
    "video_title": "Deriving E=mc2",
    "video_url": "https://youtube.com/watch?v=...",
    "icp_score": 9,
    "status": "asset_generated",
    "branded_player_url": "https://render.eulaiq.com/player/deriving-emc2",
    "draft_email": {
        "subject": "...",
        "body": "..."
    }
  }
]
```

## Directory Structure
```
workspace/
├── scripts/
│   ├── 1_harvest_leads.py
│   ├── 2_refine_leads.py
│   ├── 3_generate_assets.py
│   ├── 4_draft_emails.py
│   └── 5_dispatch_emails.py
├── data/
│   ├── leads_db.json          # Deduplication master list
│   ├── raw_leads_2025-12-03.json
│   ├── qualified_leads.json   # The active pipeline
│   ├── drafts/
│   │   ├── pending_2025-12-03.json
│   │   └── ready_to_send.json
│   └── archived_leads.json    # History
└── assets/
    └── audio/                 # Temp storage for downloads
```
