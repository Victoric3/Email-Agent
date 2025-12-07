# Lead Qualification System for EulaIQ Outreach

## Overview

This document describes the complete lead qualification system, scoring methodology, and pipeline flow for the EulaIQ outreach automation.

---

## Part 1: Qualification Touch Points

Based on our [ICP (Ideal Customer Profile)](../Context/icp.md), we qualify leads using **multiple signals** that combine into a final score.

### 1.1 Channel Metrics (Programmatic)

| Signal | Scoring | Rationale |
|--------|---------|-----------|
| **Subscriber Count** | | |
| < 5,000 | DISQUALIFY | Too small, likely not monetized |
| 5,000 - 100,000 | +1 | Small but growing, high engagement |
| 100,000 - 1,000,000 | +3 | **SWEET SPOT** - Big enough to pay, small enough to reply |
| > 1,000,000 | +2 | Large but harder to reach |
| **Video Views (source video)** | | |
| > 1,000,000 | +2 | Viral potential |
| > 100,000 | +1 | Good engagement |
| < 1,000 | -1 | Low engagement |
| **Channel Age** | | |
| < 6 months | -1 | Too new, unproven |
| 6 months - 2 years | +1 | Active growth phase |
| > 2 years | +0 | Established (neutral) |
| **Upload Frequency** | | |
| > 4 videos/month | +2 | High volume = high pain point |
| 1-4 videos/month | +1 | Regular uploader |
| < 1 video/month | -1 | Inactive |
| **Has Email in Description** | +1 | Easy to contact |

### 1.2 Content Analysis (LLM-Based)

| Signal | Scoring | Rationale |
|--------|---------|-----------|
| **Manim Compatibility** | | |
| Perfect (Math/Geometry/Linear Algebra) | +3 | Ideal for our tech |
| Good (Physics/Mechanics/Waves) | +2 | Strong fit |
| Possible (Chemistry/CS/ML) | +1 | Can work with effort |
| Marginal (History/Geography) | +0 | Limited use |
| Incompatible (Vlogs/Gaming) | DISQUALIFY | Not our market |
| **Content Depth** | | |
| Deep conceptual explainers | +2 | High value from animation |
| Tutorial/How-to | +1 | Moderate value |
| News/Commentary | -1 | Low animation need |
| **Visual Complexity Need** | | |
| Complex equations/diagrams | +2 | High pain point |
| Moderate visuals | +1 | Some benefit |
| Talking head only | -1 | Low animation need |
| **Current Production Quality** | | |
| Basic/DIY animations | +2 | Room to upgrade |
| No animations | +1 | Opportunity |
| High-end animations | -1 | Already solved |

### 1.3 Geographic & Language (LLM-Based)

| Signal | Scoring | Rationale |
|--------|---------|-----------|
| **Primary Language** | | |
| English | +2 | Primary market |
| Spanish/French/German | +1 | Secondary markets |
| Hindi/Regional | +0 | Price sensitivity |
| Non-Latin script only | -1 | Harder to serve |
| **Likely Location** | | |
| USA/UK/Canada/Australia | +2 | High purchasing power |
| Western Europe | +1 | Good market |
| Other | +0 | Neutral |

### 1.4 Engagement Signals (Programmatic)

| Signal | Scoring | Rationale |
|--------|---------|-----------|
| **Comments Enabled** | +0 (neutral) | Normal |
| **Comments Disabled** | -1 | May not want engagement |
| **Engagement Rate** | | |
| > 5% (likes/views) | +1 | Active audience |
| < 1% | -1 | Passive audience |

---

## Part 2: Final Score Calculation

```
FINAL_SCORE = BASE (5) 
            + Subscriber_Tier_Bonus
            + View_Count_Bonus
            + Channel_Age_Bonus
            + Upload_Frequency_Bonus
            + Email_Available_Bonus
            + Manim_Compatibility_Bonus (LLM)
            + Content_Depth_Bonus (LLM)
            + Visual_Complexity_Bonus (LLM)
            + Production_Quality_Bonus (LLM)
            + Language_Bonus (LLM)
            + Location_Bonus (LLM)
            + Engagement_Rate_Bonus
```

**Score Interpretation:**
- **10+**: 🔥 HOT LEAD - Prioritize immediately
- **8-9**: ⭐ HIGH QUALITY - Strong fit
- **6-7**: 📈 QUALIFIED - Worth reaching out
- **4-5**: ❓ MARGINAL - Low priority
- **< 4**: ❌ DISQUALIFY - Skip

---

## Part 3: How We Disqualify Wrong Content

### 3.1 Programmatic Disqualification (Fast Filter)

**Keyword-based exclusion** - If title/description contains:
```python
DISQUALIFY_KEYWORDS = [
    # Entertainment
    "vlog", "reaction", "unboxing", "gaming", "gameplay", "let's play",
    "mukbang", "asmr", "podcast", "interview", "news", "politics",
    
    # Lifestyle
    "cooking", "recipe", "travel", "fashion", "makeup", "beauty",
    "fitness", "workout", "sports", "entertainment",
    
    # Media
    "movie review", "tv show", "celebrity", "drama", "comedy skit", "prank",
    
    # Non-educational
    "music video", "song", "cover", "remix", "trailer"
]
```

**Channel type exclusion** - Skip channels that are:
- Verified music channels
- News organizations
- Entertainment networks
- Shorts-only channels (< 60 second average)

### 3.2 LLM-Based Disqualification (Accurate Filter)

The LLM analyzes the video title, description, and channel context to determine:

1. **Is this educational content?** (Yes/No)
2. **Does it involve concepts that benefit from animation?** (Yes/No)
3. **Can Manim/mathematical visualization enhance this?** (Yes/No)

If ANY answer is "No" → DISQUALIFY

**LLM Prompt for Classification:**
```
Analyze this YouTube video for EulaIQ (AI animation for Math/Science education).

Channel: {channel_name}
Title: {video_title}
Description: {description}
Subscriber Count: {subs}

Determine:
1. Content Type: [educational_stem | educational_other | entertainment | other]
2. Manim Compatibility: [perfect | good | possible | marginal | incompatible]
3. Visual Complexity Need: [high | medium | low | none]
4. Disqualify: [true/false] with reason

Output JSON only.
```

---

## Part 4: Pipeline Flow

### Simple Usage Flow

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: HARVEST LEADS                                      │
│  python scripts/outreach/1_harvest_leads.py --limit 5       │
│                                                              │
│  What it does:                                               │
│  - Searches YouTube for keywords from keywords.txt          │
│  - Gets channel subscriber counts via yt-dlp                │
│  - Filters out < 5K subscriber channels                     │
│  - Saves raw leads to MongoDB (status: "harvested")         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: REFINE & QUALIFY                                   │
│  python scripts/outreach/2_refine_leads.py                  │
│                                                              │
│  What it does:                                               │
│  - Reads "harvested" leads from MongoDB                     │
│  - Uses LLM to classify Manim compatibility                 │
│  - Uses LLM to extract creator name & analyze content       │
│  - Calculates final score (metrics + LLM scores)            │
│  - Updates leads to "qualified" if score >= 7               │
│  - Disqualifies incompatible content                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: GENERATE ASSETS                                    │
│  python scripts/outreach/3_generate_assets.py               │
│                                                              │
│  What it does:                                               │
│  - Downloads audio from source video (yt-dlp)               │
│  - Calls EulaIQ API to generate sample animation            │
│  - Registers branded player URL                             │
│  - Updates lead with video assets                           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: DRAFT EMAILS                                       │
│  python scripts/outreach/4_draft_emails.py                  │
│                                                              │
│  What it does:                                               │
│  - Uses LLM to generate personalized email                  │
│  - References their specific video/content                  │
│  - Includes branded player link to sample                   │
│  - Saves draft to MongoDB for review                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: SEND EMAILS                                        │
│  python scripts/outreach/5_dispatch_emails.py               │
│                                                              │
│  What it does:                                               │
│  - Sends emails via ZeptoMail                               │
│  - Tracks sent status in MongoDB                            │
│  - Schedules followups (3, 7, 10, 15 days)                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 6: CHECK FOLLOWUPS (Daily)                            │
│  python scripts/outreach/6_check_followups.py               │
│                                                              │
│  What it does:                                               │
│  - Checks for leads needing followup                        │
│  - Generates followup email content                         │
│  - Sends followup via ZeptoMail                             │
└─────────────────────────────────────────────────────────────┘
```

### Quick Commands Reference

```bash
# Full pipeline test with 1 keyword
python scripts/outreach/1_harvest_leads.py --limit 1
python scripts/outreach/2_refine_leads.py
python scripts/outreach/3_generate_assets.py
python scripts/outreach/4_draft_emails.py
python scripts/outreach/5_dispatch_emails.py

# Check pipeline status
python scripts/outreach/manage_leads.py stats

# View specific lead
python scripts/outreach/manage_leads.py view --channel-id <id>

# Run followups
python scripts/outreach/6_check_followups.py
```

---

## Part 5: Why Two Scripts (Harvest vs Refine)?

| Script | Purpose | Speed | Cost |
|--------|---------|-------|------|
| `1_harvest_leads.py` | **Bulk collection** with basic filtering | Fast (programmatic) | Free |
| `2_refine_leads.py` | **Deep analysis** with LLM qualification | Slow (API calls) | ~$0.01/lead |

**Rationale:**
1. Harvest casts a wide net (1000+ channels possible)
2. Programmatic filters remove obvious non-fits (gaming, vlogs, < 5K subs)
3. LLM refines the remaining ~20% with deep analysis
4. This reduces LLM costs by 80%+ while maintaining quality

---

## Part 6: Disqualification Summary

### Automatic Disqualification (No LLM needed)
- ❌ Subscriber count < 5,000
- ❌ Channel is a music/news/entertainment network
- ❌ Content keywords match DISQUALIFY list
- ❌ Shorts-only channel

### LLM Disqualification
- ❌ Content is not educational
- ❌ Content doesn't benefit from animation
- ❌ Manim compatibility = "incompatible"
- ❌ Final score < 4

### Manual Review Triggers
- ⚠️ Score between 4-6 (borderline)
- ⚠️ Unknown language/location
- ⚠️ Ambiguous content type
