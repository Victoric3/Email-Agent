#!/usr/bin/env python3
"""
Step 2: Refine & Qualify Leads using LLM.

Reads "harvested" leads from MongoDB, uses Bedrock for deep analysis,
calculates final scores, and updates qualified leads.
"""
import json
import re
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from aws_bedrock_client import AWSBedrockClient
from db_client import get_db, LeadStatus

# Configuration
MIN_FINAL_SCORE = 7
CONTEXT_DIR = Path(__file__).parent.parent.parent / "Context"


def load_icp_context():
    """Load ICP context for better LLM prompts."""
    icp_file = CONTEXT_DIR / "icp.md"
    if icp_file.exists():
        with open(icp_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def extract_email_from_text(text):
    """Extract email from description using regex."""
    if not text:
        return None
    # Match common email patterns
    patterns = [
        r'[\w\.-]+@[\w\.-]+\.\w+',
        r'business\s*(?:email|inquiry|enquiry)?\s*[:\s]+[\w\.-]+@[\w\.-]+\.\w+',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            email = match.group(0)
            # Clean up if it caught extra text
            email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', email)
            if email:
                return email.group(0).lower()
    return None


async def analyze_lead_with_llm(client, lead):
    """
    Use LLM to deeply analyze a lead and determine:
    - Manim compatibility
    - Content depth
    - Visual complexity need
    - Creator name extraction
    - Geographic signals
    """
    source_video = lead.get("source_video", {})
    
    # Handle unknown/unavailable subscriber counts
    sub_count = lead.get('subscriber_count')
    stats_available = lead.get('stats_available', sub_count is not None)
    
    if stats_available and sub_count:
        sub_display = f"{sub_count:,}"
    else:
        sub_display = "UNKNOWN (stats unavailable - evaluate based on content only)"
    
    prompt = f"""You are analyzing a YouTube creator for EulaIQ, an AI animation company specializing in "3Blue1Brown-style" mathematical and scientific visualizations.

CHANNEL INFO:
- Name: {lead.get('channel_name', 'Unknown')}
- Subscribers: {sub_display}
- Channel Description: {lead.get('channel_description', 'N/A')[:500]}

SOURCE VIDEO:
- Title: {source_video.get('title', 'N/A')}
- Description: {source_video.get('description', 'N/A')}
- Views: {source_video.get('view_count', 'N/A')}

NOTE: If subscriber count is UNKNOWN, focus on content quality signals from the video title/description. A creator making deep math/physics content is valuable even without stats.

TASK: Analyze this creator and respond with JSON ONLY (no markdown, no explanation):

{{
    "creator_first_name": "The creator's likely first name (from channel name or guess, e.g., 'Grant' from '3Blue1Brown')",
    
    "manim_compatibility": {{
        "score": 0-3,
        "tier": "perfect|good|possible|marginal|incompatible",
        "reason": "Brief explanation"
    }},
    
    "content_analysis": {{
        "is_educational": true/false,
        "content_depth_score": 0-2,
        "visual_complexity_need": 0-2,
        "current_production_quality": "basic|moderate|high",
        "production_score": -1 to 2
    }},
    
    "geographic": {{
        "likely_language": "english|spanish|hindi|other",
        "language_score": -1 to 2,
        "likely_location": "usa_uk_canada_aus|western_europe|other",
        "location_score": 0-2
    }},
    
    "disqualify": {{
        "should_disqualify": true/false,
        "reason": "Reason if disqualified, else null"
    }},
    
    "overall_assessment": "One sentence summary of fit"
}}

SCORING GUIDE:
- manim_compatibility: 3=perfect (math/geometry), 2=good (physics), 1=possible (chemistry/CS), 0=marginal, -10=incompatible
- content_depth_score: 2=deep conceptual, 1=tutorial, 0=surface level
- visual_complexity_need: 2=complex equations/diagrams needed, 1=moderate, 0=low
- production_score: 2=basic/DIY (room to upgrade), 1=none, 0=moderate, -1=already high-end
- language_score: 2=English, 1=Spanish/French/German, 0=other
- location_score: 2=USA/UK/Canada/Australia, 1=Western Europe, 0=other

Respond with valid JSON only."""

    try:
        response = await client.converse(prompt)
        text = response.get("text", "")
        
        # Clean up potential markdown
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        return json.loads(text.strip())
    except Exception as e:
        print(f"    ⚠️ LLM analysis failed: {e}")
        return None


def calculate_final_score(lead, llm_analysis):
    """
    Calculate the final score combining programmatic metrics and LLM analysis.
    """
    score = 5  # Base score
    breakdown = {"base": 5}
    
    # === PROGRAMMATIC SCORES (already in lead) ===
    
    # Subscriber tier
    sub_tier = lead.get("subscriber_tier", "unknown")
    tier_bonus = {"sweet_spot": 3, "big": 2, "small": 1, "unknown": 0}.get(sub_tier, 0)
    score += tier_bonus
    breakdown["subscriber_tier"] = tier_bonus
    
    # View count bonus (from pre_score breakdown if available)
    pre_breakdown = lead.get("score_breakdown", {})
    
    # Email availability
    email = lead.get("email") or extract_email_from_text(lead.get("channel_description", ""))
    if email:
        score += 1
        breakdown["email_available"] = 1
    else:
        breakdown["email_available"] = 0
    
    # === LLM SCORES ===
    
    if llm_analysis:
        # Manim compatibility
        manim = llm_analysis.get("manim_compatibility", {})
        manim_score = manim.get("score", 0)
        score += manim_score
        breakdown["manim_compatibility"] = manim_score
        
        # Content analysis
        content = llm_analysis.get("content_analysis", {})
        depth_score = content.get("content_depth_score", 0)
        visual_score = content.get("visual_complexity_need", 0)
        prod_score = content.get("production_score", 0)
        
        score += depth_score + visual_score + prod_score
        breakdown["content_depth"] = depth_score
        breakdown["visual_complexity"] = visual_score
        breakdown["production_quality"] = prod_score
        
        # Geographic
        geo = llm_analysis.get("geographic", {})
        lang_score = geo.get("language_score", 0)
        loc_score = geo.get("location_score", 0)
        
        score += lang_score + loc_score
        breakdown["language"] = lang_score
        breakdown["location"] = loc_score
    
    # Clamp to 1-15 range (higher ceiling with more factors)
    final_score = max(1, min(15, score))
    
    return final_score, breakdown


async def refine_leads(limit=None, test_email=None):
    """
    Process harvested leads with LLM analysis and update scores.
    
    Args:
        limit: Max number of leads to process
        test_email: If provided, override all emails with this (for testing)
    """
    db = get_db()
    
    # Get leads with status "harvested"
    query = {"status": "harvested"}
    harvested_leads = list(db.leads.find(query))
    
    if not harvested_leads:
        print("No harvested leads to refine.")
        return
    
    if limit:
        harvested_leads = harvested_leads[:limit]
    
    print(f"\n{'='*60}")
    print(f"LEAD REFINEMENT & QUALIFICATION")
    print(f"{'='*60}")
    print(f"Leads to process: {len(harvested_leads)}")
    print(f"Min score for qualification: {MIN_FINAL_SCORE}")
    if test_email:
        print(f"⚠️  TEST MODE: All emails will be set to {test_email}")
    print(f"{'='*60}\n")
    
    client = AWSBedrockClient()
    if not client.is_enabled():
        print("⚠️  Bedrock client is in MOCK mode. Using simulated responses.\n")
    
    stats = {
        "processed": 0,
        "qualified": 0,
        "disqualified": 0,
        "failed": 0
    }
    
    for lead in harvested_leads:
        channel_name = lead.get("channel_name", "Unknown")
        print(f"Analyzing: {channel_name}...")
        
        # LLM Analysis
        llm_analysis = await analyze_lead_with_llm(client, lead)
        
        if not llm_analysis:
            stats["failed"] += 1
            continue
        
        stats["processed"] += 1
        
        # Check for disqualification
        disqualify = llm_analysis.get("disqualify", {})
        if disqualify.get("should_disqualify"):
            print(f"  ❌ DISQUALIFIED: {disqualify.get('reason')}")
            db.leads.update_one(
                {"_id": lead["_id"]},
                {"$set": {
                    "status": "disqualified",
                    "disqualify_reason": disqualify.get("reason"),
                    "llm_analysis": llm_analysis
                }}
            )
            stats["disqualified"] += 1
            continue
        
        # Calculate final score
        final_score, breakdown = calculate_final_score(lead, llm_analysis)
        
        # Extract/override email
        email = test_email or lead.get("email") or extract_email_from_text(lead.get("channel_description", ""))
        
        # Extract creator name from LLM
        creator_name = llm_analysis.get("creator_first_name", channel_name.split()[0])
        
        # Determine qualification
        if final_score >= MIN_FINAL_SCORE:
            status = LeadStatus.QUALIFIED
            stats["qualified"] += 1
            emoji = "✅"
        else:
            status = "low_score"
            emoji = "📉"
        
        # Update lead in MongoDB
        update_data = {
            "status": status,
            "email": email,
            "creator_name": creator_name,
            "final_score": final_score,
            "score_breakdown": breakdown,
            "llm_analysis": llm_analysis,
            "manim_compatibility": llm_analysis.get("manim_compatibility", {}).get("tier"),
            "content_depth": llm_analysis.get("content_analysis", {}).get("content_depth_score"),
            "visual_complexity_need": llm_analysis.get("content_analysis", {}).get("visual_complexity_need"),
            "overall_assessment": llm_analysis.get("overall_assessment"),
        }
        
        db.leads.update_one(
            {"_id": lead["_id"]},
            {"$set": update_data}
        )
        
        # Print result
        tier = llm_analysis.get("manim_compatibility", {}).get("tier", "?")
        print(f"  {emoji} Score: {final_score}/15 | Manim: {tier} | Email: {email or 'None'}")
        print(f"     Breakdown: {breakdown}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"REFINEMENT COMPLETE")
    print(f"{'='*60}")
    print(f"Processed: {stats['processed']}")
    print(f"Qualified (score >= {MIN_FINAL_SCORE}): {stats['qualified']}")
    print(f"Disqualified: {stats['disqualified']}")
    print(f"Failed: {stats['failed']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Refine and qualify harvested leads using LLM")
    parser.add_argument("--limit", "-l", type=int, default=None, help="Limit number of leads to process")
    parser.add_argument("--test-email", type=str, default=None, help="Override all emails with this address (for testing)")
    
    args = parser.parse_args()
    asyncio.run(refine_leads(limit=args.limit, test_email=args.test_email))
