"""
Vercel Serverless Function: Lead Harvesting & Qualification Worker

This worker runs continuously via Vercel Cron Jobs:
1. Harvests leads from YouTube using available keywords (from MongoDB)
2. Qualifies harvested leads using LLM
3. Auto-generates new keywords when exhausted

All state is stored in MongoDB (not files) for serverless compatibility.

Trigger via: GET /api/worker or Vercel Cron
"""
import os
import sys
import json
import asyncio
import re
import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import quote

import aiohttp
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================
MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGODB_DEV")
DATABASE_NAME = "eulaiq_outreach"
LEADS_COLLECTION = "leads"
KEYWORDS_COLLECTION = "keywords"  # New collection for keywords

MAX_VIDEOS_PER_KEYWORD = 30
MIN_FINAL_SCORE = 6

DISQUALIFY_KEYWORDS = [
    "vlog", "reaction", "unboxing", "gaming", "gameplay", "let's play",
    "mukbang", "asmr", "podcast", "news", "politics",
    "cooking", "recipe", "travel", "fashion", "makeup", "beauty",
    "fitness", "workout", "sports", "movie review",
    "music video", "song", "cover", "remix", "trailer", "prank",
    "shorts", "tiktok", "reels", "meme", "funny"
]


# ============================================================
# Bedrock Client (inline for serverless)
# ============================================================
class BedrockClient:
    def __init__(self):
        self.enabled = False
        self.region = os.getenv("AWS_REGION")
        self.api_key = os.getenv("AWS_API_KEY")
        self.account_id = os.getenv("AWS_ACCOUNT_ID")
        self.model_id = os.getenv(
            "AWS_BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5-20250929-v1:0"
        )
        if self.api_key:
            self.enabled = True

    def is_enabled(self) -> bool:
        return self.enabled

    async def converse(self, prompt: str, timeout: int = 120) -> dict:
        if not self.enabled:
            return {"text": "[MOCK] Bedrock not configured", "model": "mock"}

        model_arn = f"arn:aws:bedrock:{self.region}:{self.account_id}:inference-profile/global.{self.model_id}"
        encoded = quote(model_arn, safe='')
        url = f"https://bedrock-runtime.{self.region}.amazonaws.com/model/{encoded}/converse"

        headers = {
            "Content-Type": "application/json",
            "X-Amz-Target": "AWSBedrockRuntime.Converse",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "modelId": model_arn,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"temperature": 0.2, "maxTokens": 16384},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                text = await resp.text()
                result = json.loads(text)
                
                if result.get("output") and result["output"].get("message"):
                    content = result["output"]["message"].get("content", [])
                    if content and isinstance(content, list):
                        first = content[0]
                        if isinstance(first, dict) and 'text' in first:
                            return {"text": first.get("text", ""), "model": self.model_id}
                
                return {"text": str(result), "model": self.model_id}


# ============================================================
# Database Helper
# ============================================================
def get_db():
    if not MONGODB_URI:
        raise ValueError("MONGODB_URI not configured")
    client = MongoClient(MONGODB_URI)
    return client[DATABASE_NAME]


# ============================================================
# Keyword Management (MongoDB-backed)
# ============================================================
def get_available_keywords(db, limit=3):
    """Get unused keywords from MongoDB."""
    keywords_coll = db[KEYWORDS_COLLECTION]
    
    available = list(keywords_coll.find(
        {"used": {"$ne": True}},
        {"keyword": 1}
    ).limit(limit))
    
    return [k["keyword"] for k in available]


def mark_keyword_used(db, keyword):
    """Mark a keyword as used."""
    keywords_coll = db[KEYWORDS_COLLECTION]
    keywords_coll.update_one(
        {"keyword": keyword},
        {"$set": {"used": True, "used_at": datetime.now(timezone.utc)}}
    )


def count_available_keywords(db):
    """Count unused keywords."""
    keywords_coll = db[KEYWORDS_COLLECTION]
    return keywords_coll.count_documents({"used": {"$ne": True}})


def get_used_keywords(db, limit=30):
    """Get recently used keywords for context."""
    keywords_coll = db[KEYWORDS_COLLECTION]
    used = list(keywords_coll.find(
        {"used": True},
        {"keyword": 1}
    ).sort("used_at", -1).limit(limit))
    return [k["keyword"] for k in used]


def add_keywords(db, keywords):
    """Add new keywords to the database."""
    keywords_coll = db[KEYWORDS_COLLECTION]
    for kw in keywords:
        keywords_coll.update_one(
            {"keyword": kw},
            {"$setOnInsert": {"keyword": kw, "used": False, "created_at": datetime.now(timezone.utc)}},
            upsert=True
        )


# ============================================================
# Lead Status Constants
# ============================================================
class LeadStatus:
    HARVESTED = "harvested"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"


# ============================================================
# Vercel Handler
# ============================================================
class handler(BaseHTTPRequestHandler):
    """Vercel serverless handler."""
    
    def do_GET(self):
        """Handle GET request - run the worker."""
        try:
            result = asyncio.run(run_worker())
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result, default=str).encode())
            
        except Exception as e:
            import traceback
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": str(e),
                "traceback": traceback.format_exc(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }).encode())
    
    def do_POST(self):
        """Handle POST request - same as GET for cron jobs."""
        self.do_GET()


# ============================================================
# Main Worker Logic
# ============================================================
async def run_worker():
    """
    Main worker logic:
    1. Check if keywords available
    2. If not, generate new keywords using LLM
    3. Harvest leads (limited batch)
    4. Qualify harvested leads
    """
    print("\n" + "="*60)
    print("🚀 WORKER STARTED")
    print("="*60)
    
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "started",
        "harvest": None,
        "qualify": None,
        "keywords_generated": False
    }
    
    try:
        print("Connecting to MongoDB...")
        db = get_db()
        print("✓ Connected to MongoDB\n")
        
        # Step 1: Check keywords
        print("Checking available keywords...")
        keywords_available = count_available_keywords(db)
        print(f"✓ Found {keywords_available} available keywords\n")
        
        if keywords_available == 0:
            print("No keywords available, generating new ones...")
            generated = await generate_new_keywords(db)
            result["keywords_generated"] = True
            result["new_keywords_count"] = generated
            keywords_available = count_available_keywords(db)
        
        result["keywords_available"] = keywords_available
        
        # Step 2: Harvest leads (limit to 3 keywords per run)
        if keywords_available > 0:
            print("Starting harvest batch (3 keywords)...")
            harvest_result = await harvest_batch(db, limit_keywords=3)
            result["harvest"] = harvest_result
            print(f"✓ Harvest complete: {harvest_result}\n")
        else:
            print("⚠️ No keywords available for harvesting\n")
        
        # Step 3: Qualify harvested leads
        print("Checking for harvested leads to qualify...")
        harvested_count = db[LEADS_COLLECTION].count_documents({"status": "harvested"})
        print(f"Found {harvested_count} harvested leads\n")
        
        if harvested_count > 0:
            print("Starting qualification batch (10 leads max)...")
            qualify_result = await qualify_batch(db, limit=10)
            result["qualify"] = qualify_result
            print(f"✓ Qualification complete: {qualify_result}\n")
        else:
            result["qualify"] = {"skipped": True, "reason": "No harvested leads"}
            print("⚠️ No harvested leads to qualify\n")
        
        result["status"] = "completed"
        print("="*60)
        print("✅ WORKER COMPLETED")
        print("="*60)
        
    except Exception as e:
        import traceback
        result["status"] = "error"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
    
    return result


# ============================================================
# Harvest Logic
# ============================================================
async def harvest_batch(db, limit_keywords=3):
    """Harvest leads from YouTube with parallel channel fetching."""
    import scrapetube
    import yt_dlp
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    keywords = get_available_keywords(db, limit=limit_keywords)
    
    if not keywords:
        return {"keywords_processed": 0, "new_leads": 0}
    
    leads_coll = db[LEADS_COLLECTION]
    seen_channels = set(doc["channel_id"] for doc in leads_coll.find({}, {"channel_id": 1}))
    
    stats = {
        "keywords_processed": 0,
        "total_videos": 0,
        "new_leads": 0,
        "skipped": 0
    }
    
    def quick_disqualify(title, description):
        text = f"{title} {description}".lower()
        for keyword in DISQUALIFY_KEYWORDS:
            if keyword in text:
                return True
        return False
    
    def extract_email(text):
        if not text:
            return None
        match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        return match.group(0).lower() if match else None
    
    def get_subscriber_tier(count):
        if count is None:
            return "unknown"
        elif count < 1000:
            return "too_small"
        elif count < 100000:
            return "small"
        elif count < 1000000:
            return "sweet_spot"
        else:
            return "big"
    
    def fetch_channel_info_worker(channel_id):
        """Worker function to fetch channel info in parallel."""
        try:
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'skip_download': True,
                'no_warnings': True,
                'socket_timeout': 30,
            }
            url = f'https://www.youtube.com/channel/{channel_id}'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
                info = ydl.extract_info(url, download=False)
                return {
                    'channel_id': channel_id,
                    'subscriber_count': info.get('channel_follower_count'),
                    'channel_description': info.get('description', '') or '',
                    'error': None
                }
        except Exception as e:
            return {
                'channel_id': channel_id,
                'subscriber_count': None,
                'channel_description': '',
                'error': str(e)
            }
    
    def fetch_channels_parallel(channel_data_list, max_workers=10, timeout=120):
        """Fetch multiple channels in parallel."""
        results = {}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_channel = {
                executor.submit(fetch_channel_info_worker, ch['id']): ch
                for ch in channel_data_list
            }
            
            try:
                for future in as_completed(future_to_channel, timeout=timeout):
                    channel_data = future_to_channel[future]
                    try:
                        result = future.result(timeout=10)
                        if not result.get('error'):
                            results[result['channel_id']] = result
                    except Exception as e:
                        print(f"    ✗ {channel_data['name'][:30]:<30} | Error: {str(e)[:30]}")
            except:
                pass
        
        return results
    
    for keyword in keywords:
        print(f"  Searching keyword: '{keyword}'...")
        try:
            videos = list(scrapetube.get_search(keyword, limit=MAX_VIDEOS_PER_KEYWORD, sort_by="upload_date"))
            print(f"    Found {len(videos)} videos")
            
            # First pass: collect unique channels
            channels_to_fetch = []
            video_by_channel = {}
            
            for video in videos:
                stats["total_videos"] += 1
                
                try:
                    channel_id = video["ownerText"]["runs"][0]["navigationEndpoint"]["browseEndpoint"]["browseId"]
                except:
                    continue
                
                if channel_id in seen_channels:
                    stats["skipped"] += 1
                    continue
                
                title = video.get("title", {}).get("runs", [{}])[0].get("text", "")
                channel_name = video.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
                description = ""
                if video.get("detailedMetadataSnippets"):
                    description = video.get("detailedMetadataSnippets", [{}])[0].get("snippetText", {}).get("runs", [{}])[0].get("text", "")
                
                if quick_disqualify(title, description):
                    stats["skipped"] += 1
                    continue
                
                # Store for parallel fetching
                if channel_id not in video_by_channel:
                    channels_to_fetch.append({'id': channel_id, 'name': channel_name})
                    video_by_channel[channel_id] = {
                        'video': video,
                        'title': title,
                        'channel_name': channel_name,
                        'description': description
                    }
            
            # Parallel fetch channel stats
            if channels_to_fetch:
                print(f"    Fetching stats for {len(channels_to_fetch)} channels (parallel)...")
                channel_stats = fetch_channels_parallel(channels_to_fetch, max_workers=10, timeout=120)
                print(f"    ✓ Fetched {len(channel_stats)} channel stats")
            else:
                channel_stats = {}
            
            # Second pass: save leads with fetched stats
            for channel_id, data in video_by_channel.items():
                ch_stats = channel_stats.get(channel_id, {'subscriber_count': None, 'channel_description': ''})
                sub_tier = get_subscriber_tier(ch_stats.get("subscriber_count"))
                
                if sub_tier == "too_small":
                    stats["skipped"] += 1
                    continue
                
                seen_channels.add(channel_id)
                
                video = data['video']
                title = data['title']
                channel_name = data['channel_name']
                description = data['description']
                
                try:
                    channel_handle = video["ownerText"]["runs"][0]["navigationEndpoint"]["browseEndpoint"].get("canonicalBaseUrl", "")
                except:
                    channel_handle = ""
                
                email = extract_email(ch_stats.get("channel_description", ""))
                
                lead = {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "channel_url": f"https://youtube.com{channel_handle}" if channel_handle else f"https://youtube.com/channel/{channel_id}",
                    "email": email,
                    "source_video": {
                        "video_id": video.get("videoId"),
                        "title": title,
                        "description": description,
                        "view_count": video.get("viewCountText", {}).get("simpleText", ""),
                        "published_time": video.get("publishedTimeText", {}).get("simpleText", ""),
                    },
                    "subscriber_count": ch_stats.get("subscriber_count"),
                    "subscriber_tier": sub_tier,
                    "channel_description": ch_stats.get("channel_description", ""),
                    "keyword_source": keyword,
                    "status": "harvested",
                    "harvested_at": datetime.now(timezone.utc),
                }
                
                leads_coll.update_one(
                    {"channel_id": channel_id},
                    {"$set": lead},
                    upsert=True
                )
                
                stats["new_leads"] += 1
                print(f"    + {channel_name[:40]:40} | {sub_tier} | Email: {'YES' if email else 'NO'}")
            
            # Mark keyword as used
            print(f"    \u2713 Keyword '{keyword}' marked as used")
            mark_keyword_used(db, keyword)
            stats["keywords_processed"] += 1
            
        except Exception as e:
            print(f"    \u2716 Error processing keyword '{keyword}': {e}")
    
    return stats


# ============================================================
# Qualification Logic
# ============================================================
async def qualify_batch(db, limit=10):
    """Qualify harvested leads using LLM."""
    client = BedrockClient()
    
    if not client.is_enabled():
        return {"skipped": True, "reason": "Bedrock not configured"}
    
    leads_coll = db[LEADS_COLLECTION]
    harvested_leads = list(leads_coll.find({"status": "harvested"}).limit(limit))
    
    if not harvested_leads:
        return {"processed": 0}
    
    stats = {
        "processed": 0,
        "qualified": 0,
        "disqualified": 0,
        "failed": 0
    }
    
    for lead in harvested_leads:
        try:
            result = await analyze_and_qualify(client, lead, leads_coll)
            stats["processed"] += 1
            
            if result == "qualified":
                stats["qualified"] += 1
            elif result == "disqualified":
                stats["disqualified"] += 1
            else:
                stats["failed"] += 1
                
        except Exception as e:
            stats["failed"] += 1
            print(f"Error qualifying {lead.get('channel_name')}: {e}")
    
    return stats


async def analyze_and_qualify(client, lead, leads_coll):
    """Analyze a single lead and update its status."""
    source_video = lead.get("source_video", {})
    sub_count = lead.get('subscriber_count')
    sub_display = f"{sub_count:,}" if sub_count else "Unknown"
    
    prompt = f"""You are qualifying YouTube creators for EulaIQ, an AI animation company.

CHANNEL INFO:
- Name: {lead.get('channel_name', 'Unknown')}
- Subscribers: {sub_display}
- Description: {lead.get('channel_description', 'N/A')[:500]}

VIDEO:
- Title: {source_video.get('title', 'N/A')}
- Description: {source_video.get('description', 'N/A')[:300]}

Respond with JSON only:
{{
    "creator_first_name": "Best guess at creator's first name",
    "is_english": true/false,
    "subject_area": "math|physics|chemistry|cs|engineering|biology|economics|other",
    "is_educational": true/false,
    "content_depth": "deep_conceptual|tutorial|surface",
    "needs_visual_animation": true/false,
    "should_disqualify": true/false,
    "disqualify_reason": "reason or null",
    "fit_score": 0-10,
    "overall_assessment": "One sentence summary"
}}"""
    
    try:
        response = await client.converse(prompt)
        text = response.get("text", "")
        
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        analysis = json.loads(text.strip())
        
        # Check disqualification
        if analysis.get("should_disqualify"):
            leads_coll.update_one(
                {"_id": lead["_id"]},
                {"$set": {
                    "status": LeadStatus.DISQUALIFIED,
                    "disqualify_reason": analysis.get("disqualify_reason"),
                    "llm_analysis": analysis
                }}
            )
            return "disqualified"
        
        # Check language
        if not analysis.get("is_english", True):
            leads_coll.update_one(
                {"_id": lead["_id"]},
                {"$set": {
                    "status": LeadStatus.DISQUALIFIED,
                    "disqualify_reason": "Non-English channel",
                    "llm_analysis": analysis
                }}
            )
            return "disqualified"
        
        # Calculate score
        score = analysis.get("fit_score", 0)
        
        # Extract email
        def extract_email(text):
            if not text:
                return None
            match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
            return match.group(0).lower() if match else None
        
        email = lead.get("email") or extract_email(lead.get("channel_description", ""))
        
        if score >= MIN_FINAL_SCORE:
            status = LeadStatus.QUALIFIED
            result = "qualified"
        else:
            status = "low_score"
            result = "low_score"
        
        leads_coll.update_one(
            {"_id": lead["_id"]},
            {"$set": {
                "status": status,
                "email": email,
                "creator_name": analysis.get("creator_first_name", lead.get("channel_name")),
                "final_score": score,
                "subject_area": analysis.get("subject_area"),
                "content_depth": analysis.get("content_depth"),
                "overall_assessment": analysis.get("overall_assessment"),
                "llm_analysis": analysis
            }}
        )
        
        return result
        
    except Exception as e:
        print(f"LLM analysis failed: {e}")
        return "failed"


# ============================================================
# Keyword Generation
# ============================================================
async def generate_new_keywords(db):
    """Use LLM to generate new keywords."""
    client = BedrockClient()
    if not client.is_enabled():
        return 0
    
    used_keywords = get_used_keywords(db, limit=30)
    
    prompt = f"""You are helping find YouTube educational content creators for EulaIQ, an AI animation company that creates "3Blue1Brown-style" mathematical and scientific visualizations.

RECENTLY USED KEYWORDS (avoid these):
{chr(10).join(used_keywords[-20:])}

TASK: Generate 50 NEW, UNIQUE YouTube search keywords to find educational creators in:
- Mathematics (calculus, algebra, geometry, topology, number theory)
- Physics (quantum mechanics, relativity, thermodynamics, electromagnetism)
- Chemistry (organic chemistry, physical chemistry, biochemistry)
- Computer Science (algorithms, data structures, machine learning)
- Engineering (control systems, signal processing)

REQUIREMENTS:
1. Keywords should find creators who make CONCEPTUAL explanation videos
2. Avoid generic terms like "math tutorial" - be specific (e.g., "Fourier transform intuition")
3. Mix of advanced topics and popular explainer-style content
4. Include "explained", "intuition", "visualization", "visually" in some keywords
5. DO NOT repeat any keyword from the RECENTLY USED list

Respond with ONLY the keywords, one per line, no numbering or bullets."""

    try:
        response = await client.converse(prompt)
        text = response.get("text", "")
        
        # Parse keywords
        new_keywords = [line.strip() for line in text.strip().split("\n") if line.strip()]
        
        # Filter out any that match used keywords
        used_set = set(k.lower() for k in used_keywords)
        new_keywords = [k for k in new_keywords if k.lower() not in used_set]
        
        if new_keywords:
            add_keywords(db, new_keywords)
        
        return len(new_keywords)
        
    except Exception as e:
        print(f"Keyword generation failed: {e}")
        return 0


# ============================================================
# Script to seed initial keywords (run locally once)
# ============================================================
def seed_keywords_from_file(keywords_file_path):
    """
    One-time script to seed keywords from keywords.txt to MongoDB.
    Run this locally before deploying to Vercel.
    """
    db = get_db()
    
    with open(keywords_file_path, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    add_keywords(db, keywords)
    print(f"Seeded {len(keywords)} keywords to MongoDB")


if __name__ == "__main__":
    # For local testing
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        # Seed keywords from file
        keywords_file = sys.argv[2] if len(sys.argv) > 2 else "keywords.txt"
        seed_keywords_from_file(keywords_file)
    else:
        # Run worker
        result = asyncio.run(run_worker())
        print(json.dumps(result, indent=2, default=str))
