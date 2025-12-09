#!/usr/bin/env python3
"""
Step 1: Harvest Leads from YouTube (Parallelized)

Searches YouTube for educational content creators, gets channel stats,
applies basic filters, and saves to MongoDB for LLM refinement.

Key Features:
- Parallel channel stat fetching (10 at a time)
- 2-minute timeout per channel
- Fast keyword-based pre-filtering
"""
import os
import sys
import json
import datetime
import time
import re
import threading
import itertools
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# ============================================================
# CONFIGURATION
# ============================================================
MAX_VIDEOS_PER_KEYWORD = 30
PARALLEL_CHANNELS = 10  # Process 10 channels at a time
CHANNEL_TIMEOUT = 120  # 2 minutes timeout per channel
DELAY_BETWEEN_BATCHES = 1  # Small delay between batches

DATA_DIR = Path(__file__).parent.parent.parent / "data"
KEYWORDS_FILE = Path(__file__).parent.parent.parent / "keywords.txt"
USED_KEYWORDS_FILE = Path(__file__).parent.parent.parent / "used_keywords.txt"

# Fast disqualification keywords (obvious non-fits)
DISQUALIFY_KEYWORDS = [
    "vlog", "reaction", "unboxing", "gaming", "gameplay", "let's play",
    "mukbang", "asmr", "podcast", "news", "politics",
    "cooking", "recipe", "travel", "fashion", "makeup", "beauty",
    "fitness", "workout", "sports", "movie review",
    "music video", "song", "cover", "remix", "trailer", "prank",
    "shorts", "tiktok", "reels", "meme", "funny"
]

# ============================================================


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


def _fetch_channel_info_worker(channel_id):
    """
    Worker function to fetch channel info.
    Returns dict with channel stats or error.
    """
    try:
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'skip_download': True,
            'no_warnings': True,
            'socket_timeout': 30,
        }
        url = f'https://www.youtube.com/channel/{channel_id}'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
            info = ydl.extract_info(url, download=False)
            return {
                'channel_id': channel_id,
                'subscriber_count': info.get('channel_follower_count'),
                'channel_description': info.get('description', '') or '',
                'stats_available': info.get('channel_follower_count') is not None,
                'error': None
            }
    except Exception as e:
        return {
            'channel_id': channel_id,
            'subscriber_count': None,
            'channel_description': '',
            'stats_available': False,
            'error': str(e)
        }


def fetch_channel_stats_parallel(channel_ids, timeout=CHANNEL_TIMEOUT, max_workers=None):
    """
    Fetch stats for multiple channels in parallel.
    Returns dict mapping channel_id -> stats.
    """
    results = {}
    workers = max_workers or PARALLEL_CHANNELS
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Submit all tasks
        future_to_channel = {
            executor.submit(_fetch_channel_info_worker, cid): cid 
            for cid in channel_ids
        }
        
        # Collect results with timeout
        for future in as_completed(future_to_channel, timeout=timeout):
            channel_id = future_to_channel[future]
            try:
                result = future.result(timeout=10)
                results[channel_id] = result
            except Exception as e:
                results[channel_id] = {
                    'channel_id': channel_id,
                    'subscriber_count': None,
                    'channel_description': '',
                    'stats_available': False,
                    'error': f"Timeout or error: {e}"
                }
    
    # Fill in any missing channels that timed out
    for cid in channel_ids:
        if cid not in results:
            results[cid] = {
                'channel_id': cid,
                'subscriber_count': None,
                'channel_description': '',
                'stats_available': False,
                'error': 'Timeout'
            }
    
    return results


def load_keywords():
    """Load keywords from file, excluding already used ones."""
    if not KEYWORDS_FILE.exists():
        print(f"Keywords file not found: {KEYWORDS_FILE}")
        return []
    
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        all_keywords = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
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


def harvest_leads(limit_keywords=None, skip_stats=False, parallel_workers=None, channel_timeout=None):
    """
    Harvest leads from YouTube and save to MongoDB.
    
    Args:
        limit_keywords: Limit number of keywords to process
        skip_stats: Skip fetching channel stats (much faster but less data)
        parallel_workers: Number of parallel channel fetches
        channel_timeout: Timeout in seconds for channel batch
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
    
    # Use provided values or defaults
    workers = parallel_workers or PARALLEL_CHANNELS
    timeout = channel_timeout or CHANNEL_TIMEOUT
    
    print(f"\n{'='*60}")
    print(f"LEAD HARVESTER (Parallelized)")
    print(f"Parallel workers: {workers}")
    print(f"Timeout per batch: {timeout}s")
    print(f"{'='*60}")
    print(f"Keywords: {len(keywords)}")
    print(f"Already seen: {len(seen_channels)} channels")
    print(f"Channel stats: {'DISABLED (fast mode)' if skip_stats else f'ENABLED ({workers} parallel, {timeout}s timeout)'}")
    print(f"{'='*60}\n")

    for i, keyword in enumerate(keywords):
        print(f"[{i+1}/{len(keywords)}] Searching: '{keyword}'...")
        
        try:
            with Spinner(f"  Searching YouTube for '{keyword}'..."):
                videos = list(scrapetube.get_search(keyword, limit=MAX_VIDEOS_PER_KEYWORD, sort_by="upload_date"))
            print(f"  Found {len(videos)} videos")
            
            # First pass: extract basic info and filter
            candidates = []
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
                
                # Extract channel URL
                try:
                    channel_handle = video["ownerText"]["runs"][0]["navigationEndpoint"]["browseEndpoint"].get("canonicalBaseUrl", "")
                except:
                    channel_handle = ""
                
                candidates.append({
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "channel_handle": channel_handle,
                    "video": video,
                    "title": title,
                    "description": description
                })
                
                # Mark as seen to avoid duplicates within same keyword
                seen_channels.add(channel_id)
            
            if not candidates:
                print(f"  → 0 new leads (all filtered)\n")
                mark_keyword_used(keyword)
                continue
            
            print(f"  Candidates after filter: {len(candidates)}")
            
            # Second pass: fetch channel stats in parallel (if enabled)
            channel_stats_map = {}
            if not skip_stats:
                channel_ids = [c["channel_id"] for c in candidates]
                print(f"  Fetching stats for {len(channel_ids)} channels ({workers} parallel)...")
                
                # Process in batches
                for batch_start in range(0, len(channel_ids), workers):
                    batch_ids = channel_ids[batch_start:batch_start + workers]
                    batch_results = fetch_channel_stats_parallel(batch_ids, timeout=timeout, max_workers=workers)
                    channel_stats_map.update(batch_results)
                    
                    # Small delay between batches to avoid rate limits
                    if batch_start + workers < len(channel_ids):
                        time.sleep(DELAY_BETWEEN_BATCHES)
            
            # Third pass: save leads
            keyword_leads = 0
            for candidate in candidates:
                channel_id = candidate["channel_id"]
                channel_name = candidate["channel_name"]
                video = candidate["video"]
                
                # Get stats (if fetched)
                ch_stats = channel_stats_map.get(channel_id, {})
                subscriber_count = ch_stats.get("subscriber_count")
                channel_description = ch_stats.get("channel_description", "")
                stats_available = ch_stats.get("stats_available", False)
                
                # Check subscriber tier
                sub_tier, _ = get_subscriber_tier(subscriber_count)
                
                # Only skip if we KNOW they're too small
                if sub_tier == "too_small":
                    stats["skipped_too_small"] += 1
                    continue
                
                stats["by_tier"][sub_tier] = stats["by_tier"].get(sub_tier, 0) + 1
                
                # Try to extract email from channel description
                email = extract_email(channel_description)
                
                # Build lead document
                lead = {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "channel_url": f"https://youtube.com{candidate['channel_handle']}" if candidate['channel_handle'] else f"https://youtube.com/channel/{channel_id}",
                    "email": email,
                    
                    # Source video info
                    "source_video": {
                        "video_id": video.get("videoId"),
                        "title": candidate["title"],
                        "description": candidate["description"],
                        "view_count": video.get("viewCountText", {}).get("simpleText", ""),
                        "published_time": video.get("publishedTimeText", {}).get("simpleText", ""),
                    },
                    
                    # Channel stats
                    "subscriber_count": subscriber_count,
                    "subscriber_tier": sub_tier,
                    "channel_description": channel_description,
                    "stats_available": stats_available,
                    
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
    
    parser = argparse.ArgumentParser(description="Harvest YouTube leads (parallelized)")
    parser.add_argument("--limit", "-l", type=int, default=None, help="Limit keywords to process")
    parser.add_argument("--skip-stats", "-s", action="store_true", help="Skip channel stats (faster)")
    parser.add_argument("--parallel", "-p", type=int, default=PARALLEL_CHANNELS, help=f"Parallel channels (default: {PARALLEL_CHANNELS})")
    parser.add_argument("--timeout", "-t", type=int, default=CHANNEL_TIMEOUT, help=f"Timeout per batch (default: {CHANNEL_TIMEOUT}s)")
    
    args = parser.parse_args()
    
    harvest_leads(
        limit_keywords=args.limit,
        skip_stats=args.skip_stats,
        parallel_workers=args.parallel,
        channel_timeout=args.timeout
    )
