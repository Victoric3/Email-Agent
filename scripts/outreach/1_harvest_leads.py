#!/usr/bin/env python3
"""
Step 1: Harvest Leads from YouTube

Searches YouTube for educational content creators, gets channel stats,
applies basic filters, and saves to MongoDB for LLM refinement.

This script is optimized for SPEED - complex analysis is done in step 2.
"""
import os
import sys
import json
import datetime
import time
import re
import threading
import itertools
import subprocess
import multiprocessing
import scrapetube
import yt_dlp
from pathlib import Path


class Spinner:
    """Simple loading spinner for visual feedback."""
    def __init__(self, message="Processing...", delay=0.1):
        self.spinner = itertools.cycle(['|', '/', '-', '\\'])
        self.delay = delay
        self.message = message
        self.running = False
        self.thread = None

    def spin(self):
        while self.running:
            sys.stdout.write(f"\r{self.message} {next(self.spinner)}")
            sys.stdout.flush()
            time.sleep(self.delay)

    def __enter__(self):
        self.running = True
        self.thread = threading.Thread(target=self.spin)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stdout.write(f"\r{' ' * (len(self.message) + 2)}\r")
        sys.stdout.flush()

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_db

# Configuration
MAX_VIDEOS_PER_KEYWORD = 30
DELAY_BETWEEN_CHANNELS = 0.3  # Reduced delay for faster harvesting
DATA_DIR = Path(__file__).parent.parent.parent / "data"
KEYWORDS_FILE = Path(__file__).parent.parent.parent / "keywords.txt"
USED_KEYWORDS_FILE = Path(__file__).parent.parent.parent / "used_keywords.txt"

# Fast disqualification keywords (obvious non-fits)
DISQUALIFY_KEYWORDS = [
    "vlog", "reaction", "unboxing", "gaming", "gameplay", "let's play",
    "mukbang", "asmr", "podcast", "news", "politics",
    "cooking", "recipe", "travel", "fashion", "makeup", "beauty",
    "fitness", "workout", "sports", "movie review",
    "music video", "song", "cover", "remix", "trailer", "prank"
]


def get_subscriber_tier(subscriber_count):
    """Classify channel by subscriber count."""
    if subscriber_count is None:
        return "unknown", 0
    elif subscriber_count < 5000:
        return "too_small", -2
    elif subscriber_count < 100000:
        return "small", 1
    elif subscriber_count < 1000000:
        return "sweet_spot", 3
    else:
        return "big", 2


def quick_disqualify(title, description):
    """Fast keyword-based disqualification for obvious non-fits."""
    text = f"{title} {description}".lower()
    for keyword in DISQUALIFY_KEYWORDS:
        if keyword in text:
            return True, keyword
    return False, None


def extract_email(text):
    """Extract email from text using regex."""
    if not text:
        return None
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    return match.group(0).lower() if match else None


def _fetch_channel_info(channel_id, result_queue):
    """Worker function for multiprocessing - fetches channel info."""
    try:
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'skip_download': True,
            'no_warnings': True,
        }
        url = f'https://www.youtube.com/channel/{channel_id}'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
            info = ydl.extract_info(url, download=False)
            result_queue.put({
                'subscriber_count': info.get('channel_follower_count'),
                'channel_description': info.get('description', '') or '',
                'stats_available': info.get('channel_follower_count') is not None,
            })
    except Exception as e:
        result_queue.put({'error': str(e)})


def get_channel_stats(channel_id, max_retries=2, timeout=30):
    """
    Get channel subscriber count and description via yt-dlp.
    
    Uses multiprocessing with timeout - process can actually be killed on Windows.
    """
    for attempt in range(max_retries + 1):
        result_queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=_fetch_channel_info, 
            args=(channel_id, result_queue)
        )
        process.start()
        process.join(timeout=timeout)
        
        if process.is_alive():
            # Timeout - kill the process
            process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
            print(f"\n  ⏱️  Timeout ({timeout}s) - skipping channel")
            return {'subscriber_count': None, 'channel_description': '', 'stats_available': False}
        
        try:
            result = result_queue.get_nowait()
            
            if 'error' in result:
                err = result['error']
                if "HTTP Error 429" in err:
                    wait_time = 5 * (attempt + 1)
                    print(f"\n  ⚠️  Rate limit (429) - waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                elif "Sign in" in err:
                    print(f"\n  ⚠️  Auth required - skipping stats")
                    return {'subscriber_count': None, 'channel_description': '', 'stats_available': False}
                elif attempt < max_retries:
                    time.sleep(1 * (attempt + 1))
                    continue
                else:
                    return {'subscriber_count': None, 'channel_description': '', 'stats_available': False}
            
            return result
            
        except Exception:
            if attempt < max_retries:
                time.sleep(1)
                continue
    
    return {'subscriber_count': None, 'channel_description': '', 'stats_available': False}


def load_keywords():
    """Load keywords from file, excluding already used ones."""
    if not KEYWORDS_FILE.exists():
        print(f"Keywords file not found: {KEYWORDS_FILE}")
        return []
    
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        all_keywords = [line.strip() for line in f if line.strip()]
    
    used_keywords = set()
    if USED_KEYWORDS_FILE.exists():
        with open(USED_KEYWORDS_FILE, "r", encoding="utf-8") as f:
            used_keywords = set(line.strip() for line in f if line.strip())
    
    available = [k for k in all_keywords if k not in used_keywords]
    print(f"Keywords: {len(all_keywords)} total, {len(used_keywords)} used, {len(available)} available")
    return available


def mark_keyword_used(keyword):
    """Add a keyword to the used keywords file."""
    with open(USED_KEYWORDS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{keyword}\n")


def harvest_leads(limit_keywords=None, skip_stats=False):
    """
    Harvest leads from YouTube and save to MongoDB.
    
    Args:
        limit_keywords: Limit number of keywords to process
        skip_stats: Skip fetching channel stats (much faster but less data)
    """
    keywords = load_keywords()
    
    if not keywords:
        print("No available keywords. Add more to keywords.txt or clear used_keywords.txt")
        return
    
    if limit_keywords:
        keywords = keywords[:limit_keywords]
    
    db = get_db()
    
    # Get already seen channel IDs
    seen_channels = set(doc["channel_id"] for doc in db.leads.find({}, {"channel_id": 1}))
    
    stats = {
        "total_videos": 0,
        "new_leads": 0,
        "skipped_seen": 0,
        "skipped_disqualified": 0,
        "skipped_too_small": 0,
        "by_tier": {}
    }
    
    print(f"\n{'='*60}")
    print(f"LEAD HARVESTER")
    print(f"{'='*60}")
    print(f"Keywords: {len(keywords)}")
    print(f"Already seen: {len(seen_channels)} channels")
    print(f"Channel stats: {'DISABLED (fast mode)' if skip_stats else 'ENABLED'}")
    print(f"{'='*60}\n")

    for i, keyword in enumerate(keywords):
        print(f"[{i+1}/{len(keywords)}] Searching: '{keyword}'...")
        
        try:
            with Spinner(f"  Searching YouTube for '{keyword}'..."):
                videos = list(scrapetube.get_search(keyword, limit=MAX_VIDEOS_PER_KEYWORD, sort_by="upload_date"))
            print(f"  Found {len(videos)} videos")
            keyword_leads = 0
            
            for video in videos:
                stats["total_videos"] += 1
                
                # Extract channel ID
                try:
                    channel_id = video["ownerText"]["runs"][0]["navigationEndpoint"]["browseEndpoint"]["browseId"]
                except (KeyError, IndexError, TypeError):
                    continue
                
                # Skip if already seen
                if channel_id in seen_channels:
                    stats["skipped_seen"] += 1
                    continue
                
                # Extract basic info
                title = video.get("title", {}).get("runs", [{}])[0].get("text", "")
                channel_name = video.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
                description = ""
                if video.get("detailedMetadataSnippets"):
                    description = video.get("detailedMetadataSnippets", [{}])[0].get("snippetText", {}).get("runs", [{}])[0].get("text", "")
                
                # Quick disqualification
                is_disqualified, reason = quick_disqualify(title, description)
                if is_disqualified:
                    stats["skipped_disqualified"] += 1
                    continue
                
                # Get channel stats (if enabled)
                subscriber_count = None
                channel_description = ""
                stats_available = False
                if not skip_stats:
                    with Spinner(f"  Fetching stats for {channel_name[:25]}..."):
                        channel_stats = get_channel_stats(channel_id)
                    if channel_stats:
                        subscriber_count = channel_stats.get("subscriber_count")
                        channel_description = channel_stats.get("channel_description", "")
                        stats_available = channel_stats.get("stats_available", False)
                    time.sleep(DELAY_BETWEEN_CHANNELS)
                
                # Check subscriber tier
                sub_tier, _ = get_subscriber_tier(subscriber_count)
                
                # Only skip if we KNOW they're too small
                # If stats are unknown, let them through for LLM to decide
                if sub_tier == "too_small":
                    stats["skipped_too_small"] += 1
                    continue
                
                stats["by_tier"][sub_tier] = stats["by_tier"].get(sub_tier, 0) + 1
                
                # Extract channel URL
                try:
                    channel_handle = video["ownerText"]["runs"][0]["navigationEndpoint"]["browseEndpoint"].get("canonicalBaseUrl", "")
                except:
                    channel_handle = ""
                
                # Try to extract email from channel description
                email = extract_email(channel_description)
                
                # Build lead document
                lead = {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "channel_url": f"https://youtube.com{channel_handle}" if channel_handle else f"https://youtube.com/channel/{channel_id}",
                    "email": email,
                    
                    # Source video info
                    "source_video": {
                        "video_id": video.get("videoId"),
                        "title": title,
                        "description": description,
                        "view_count": video.get("viewCountText", {}).get("simpleText", ""),
                        "published_time": video.get("publishedTimeText", {}).get("simpleText", ""),
                    },
                    
                    # Channel stats
                    "subscriber_count": subscriber_count,
                    "subscriber_tier": sub_tier,
                    "channel_description": channel_description,
                    "stats_available": stats_available,  # Flag for LLM to know if stats were fetchable
                    
                    # Keyword that found this lead
                    "keyword_source": keyword,
                    
                    # Status
                    "status": "harvested",
                    "harvested_at": datetime.datetime.now(datetime.timezone.utc),
                }
                
                # Save to MongoDB
                db.leads.update_one(
                    {"channel_id": channel_id},
                    {"$set": lead},
                    upsert=True
                )
                
                seen_channels.add(channel_id)
                stats["new_leads"] += 1
                keyword_leads += 1
                
                # Print progress
                tier_emoji = {"sweet_spot": "⭐", "big": "🔥", "small": "📈", "unknown": "❓"}.get(sub_tier, "")
                subs_str = f"{subscriber_count:,}" if subscriber_count else "?"
                email_str = "📧" if email else ""
                print(f"  + {channel_name[:35]:35} | {subs_str:>10} | {sub_tier:10} {tier_emoji} {email_str}")
            
            print(f"  → {keyword_leads} new leads\n")
            mark_keyword_used(keyword)
            
        except Exception as e:
            print(f"  ❌ Error: {e}\n")

    # Summary
    print(f"{'='*60}")
    print(f"HARVEST COMPLETE")
    print(f"{'='*60}")
    print(f"Videos scanned: {stats['total_videos']}")
    print(f"New leads saved: {stats['new_leads']}")
    print(f"Skipped (already seen): {stats['skipped_seen']}")
    print(f"Skipped (disqualified): {stats['skipped_disqualified']}")
    print(f"Skipped (< 5K subs): {stats['skipped_too_small']}")
    print(f"\nBy tier:")
    for tier, count in stats["by_tier"].items():
        emoji = {"sweet_spot": "⭐", "big": "🔥", "small": "📈", "unknown": "❓"}.get(tier, "")
        print(f"  {emoji} {tier}: {count}")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Harvest YouTube leads")
    parser.add_argument("--limit", "-l", type=int, default=None, help="Limit keywords to process")
    parser.add_argument("--skip-stats", "-s", action="store_true", help="Skip channel stats (faster)")
    
    args = parser.parse_args()
    harvest_leads(limit_keywords=args.limit, skip_stats=args.skip_stats)
