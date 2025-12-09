#!/usr/bin/env python3
"""
Step 3b: Generate Dual Video Assets.

For each approved lead:
1. Download audio from YouTube
2. Trim to first 5 minutes using ffmpeg
3. Generate 2 videos simultaneously for comparison
4. Store both URLs for manual selection

Requires: ffmpeg installed and in PATH
"""
import json
import os
import time
import subprocess
import datetime
import requests
import yt_dlp
from pathlib import Path
from itertools import cycle
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))  # Add scripts/ to path

from db_client import get_db, LeadStatus

# Configuration
AUDIO_DIR = Path(__file__).parent.parent.parent / "assets" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

TRIMMED_AUDIO_DIR = Path(__file__).parent.parent.parent / "assets" / "audio_trimmed"
TRIMMED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# EulaIQ API Config
API_BASE_URL = "https://api.eulaiq.com/api/v1"
RENDER_API_URL = "https://render.eulaiq.com"

# Audio trim duration (5 minutes = 300 seconds)
TRIM_DURATION = 300

# Load EulaIQ accounts from environment
env_accounts = os.getenv("EULAIQ_ACCOUNTS")
if env_accounts:
    try:
        ACCOUNTS = json.loads(env_accounts)
        if not isinstance(ACCOUNTS, list):
            raise ValueError("EULAIQ_ACCOUNTS must be a JSON list of account objects")
    except Exception as e:
        print(f"⚠️ Could not parse EULAIQ_ACCOUNTS env var: {e}")
        ACCOUNTS = []
else:
    ACCOUNTS = []

if not ACCOUNTS:
    print("⚠️ ERROR: No EulaIQ accounts found. Define EULAIQ_ACCOUNTS in your environment or .env")
    sys.exit(1)

# We need at least 2 accounts for generating 2 videos simultaneously
if len(ACCOUNTS) < 2:
    print("⚠️ WARNING: Less than 2 EulaIQ accounts. Will use same account for both videos.")

# Cache for auth tokens
auth_tokens = {}


def get_auth_token(account):
    """Login and return Bearer token for the given account."""
    email = account["identity"]
    if email in auth_tokens:
        return auth_tokens[email]
    
    print(f"    Logging in as {email}...")
    payload = {
        "identity": email,
        "password": account["password"],
        "ipAddress": "192.168.1.0",
        "device": {
            "userAgent": "EulaIQ-Outreach-Bot/1.0",
            "platform": "Windows",
            "deviceType": "script"
        }
    }
    
    try:
        resp = requests.post(f"{API_BASE_URL}/auth/login", json=payload)
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token")
        auth_tokens[email] = token
        return token
    except Exception as e:
        print(f"    Login failed for {email}: {e}")
        return None


def download_audio(video_url, video_id):
    """Download audio from YouTube video using yt-dlp."""
    output_path = AUDIO_DIR / f"{video_id}.mp3"
    
    if output_path.exists():
        print(f"    Audio already exists: {output_path.name}")
        return output_path

    print(f"    Downloading audio...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': str(AUDIO_DIR / video_id),
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
            ydl.download([video_url])
        return output_path
    except Exception as e:
        print(f"    Download failed: {e}")
        return None


def trim_audio(input_path, video_id, duration=TRIM_DURATION):
    """
    Trim audio to first N seconds using ffmpeg.
    Returns path to trimmed file.
    """
    output_path = TRIMMED_AUDIO_DIR / f"{video_id}_5min.mp3"
    
    if output_path.exists():
        print(f"    Trimmed audio already exists: {output_path.name}")
        return output_path
    
    print(f"    Trimming to {duration//60} minutes...")
    
    try:
        # ffmpeg -i input.mp3 -t 300 -c copy output.mp3
        cmd = [
            'ffmpeg',
            '-i', str(input_path),
            '-t', str(duration),
            '-c', 'copy',
            '-y',  # Overwrite without asking
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"    ffmpeg error: {result.stderr}")
            return None
        
        return output_path
    except FileNotFoundError:
        print("    ❌ ffmpeg not found! Please install ffmpeg and add to PATH.")
        return None
    except Exception as e:
        print(f"    Trim failed: {e}")
        return None


def generate_video(audio_path, title, token, label=""):
    """Upload audio and trigger video generation."""
    url = f"{API_BASE_URL}/video/createFromAudio"
    headers = {"Authorization": f"Bearer {token}"}
    
    video_options = {
        "mode": "dark",
        "aspectRatio": "16:9",
        "quality": "h",
        "frameRate": 30,
        "additionalInstructions": "Create a high-quality educational animation with clear diagrams and formulas."
    }
    
    try:
        with open(audio_path, 'rb') as f:
            files = {'audioFile': (audio_path.name, f, 'audio/mpeg')}
            data = {
                'title': f"{title} {label}".strip(),
                'description': f"Animation for: {title}",
                'videoOptions': json.dumps(video_options)
            }
            
            resp = requests.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            result = resp.json()
            return result.get("data", {}).get("videoId")
    except Exception as e:
        print(f"    Generation trigger failed: {e}")
        return None


def poll_status(video_id, token, max_wait=1800):
    """Poll video status until completed (max 30 min)."""
    url = f"{API_BASE_URL}/video/status/video/{video_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                status = data.get("status")
                
                if status == "completed":
                    return data.get("videoUrl")  # S3 URL
                elif status == "failed":
                    return None
                
            time.sleep(30)
        except Exception as e:
            time.sleep(30)
    
    return None


def register_player_link(title, s3_url, creator_name):
    """Register the S3 URL to get a branded player link."""
    url = f"{RENDER_API_URL}/video/register"
    payload = {
        "title": title,
        "s3_url": s3_url,
        "creator": creator_name
    }
    
    try:
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("player_url")
    except Exception as e:
        print(f"    Player registration failed: {e}")
        return s3_url  # Fallback to S3 URL


def generate_single_video(audio_path, title, creator_name, account, label):
    """
    Generate a single video (used for parallel generation).
    Returns dict with video info or None on failure.
    """
    token = get_auth_token(account)
    if not token:
        return None
    
    # Trigger generation
    video_id = generate_video(audio_path, title, token, label)
    if not video_id:
        return None
    
    # Poll for completion
    s3_url = poll_status(video_id, token)
    if not s3_url:
        return None
    
    # Register branded link
    branded_url = register_player_link(f"{title} {label}", s3_url, creator_name)
    
    return {
        "eulaiq_video_id": video_id,
        "s3_url": s3_url,
        "branded_player_url": branded_url
    }


def generate_dual_videos(audio_path, title, creator_name):
    """
    Generate 2 videos in parallel using different accounts.
    Returns (video_a_info, video_b_info) tuple.
    """
    # Use first 2 accounts (or same account twice if only 1)
    account_a = ACCOUNTS[0]
    account_b = ACCOUNTS[1] if len(ACCOUNTS) > 1 else ACCOUNTS[0]
    
    results: list[dict | None] = [None, None]
    
    print(f"    Generating 2 video options in parallel...")
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(generate_single_video, audio_path, title, creator_name, account_a, "(A)"): 0,
            executor.submit(generate_single_video, audio_path, title, creator_name, account_b, "(B)"): 1
        }
        
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                print(f"    Video {['A', 'B'][idx]} generation error: {e}")
    
    return results[0], results[1]


def process_leads(limit=None, test_mode=False):
    """
    Process approved leads: download audio, trim, generate 2 videos.
    """
    db = get_db()
    
    # Get approved leads
    leads = db.get_leads_by_status(LeadStatus.APPROVED)
    
    if not leads:
        print("No approved leads pending video generation.")
        print("Run 3a_review_leads.py first to approve leads.")
        return
    
    if limit:
        leads = leads[:limit]
    
    print(f"Found {len(leads)} approved leads to process.\n")
    
    for i, lead in enumerate(leads, 1):
        channel_id = lead["channel_id"]
        creator_name = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        video_title = lead.get("video_title", "Unknown Video")
        video_id = lead.get("video_id", channel_id[:8])
        video_url = lead.get("video_url", "")
        
        print(f"[{i}/{len(leads)}] {creator_name}")
        print(f"  Video: {video_title}")
        
        # Mark as generating
        db.update_lead_by_channel(channel_id, {"status": LeadStatus.ASSET_GENERATING})
        
        if test_mode:
            # TEST MODE: Skip real generation
            print("  [TEST MODE] Using mock URLs")
            video_a = {
                "eulaiq_video_id": f"test_a_{video_id[:8]}",
                "s3_url": f"https://eulaiq-renders.s3.amazonaws.com/test/{video_id}_a.mp4",
                "branded_player_url": f"https://render.eulaiq.com/player/test_a_{video_id[:8]}"
            }
            video_b = {
                "eulaiq_video_id": f"test_b_{video_id[:8]}",
                "s3_url": f"https://eulaiq-renders.s3.amazonaws.com/test/{video_id}_b.mp4",
                "branded_player_url": f"https://render.eulaiq.com/player/test_b_{video_id[:8]}"
            }
            db.set_dual_videos_generated(channel_id, video_a, video_b, "test_audio.mp3")
            print(f"  ✅ [MOCK] Dual videos ready for review\n")
            continue
        
        # 1. Download Audio
        audio_path = download_audio(video_url, video_id)
        if not audio_path or not audio_path.exists():
            print("  ⚠️ Skipping (Audio download failed)\n")
            db.update_lead_by_channel(channel_id, {"status": LeadStatus.APPROVED})
            continue
        
        # 2. Trim to 5 minutes
        trimmed_path = trim_audio(audio_path, video_id)
        if not trimmed_path or not trimmed_path.exists():
            print("  ⚠️ Skipping (Audio trim failed)\n")
            db.update_lead_by_channel(channel_id, {"status": LeadStatus.APPROVED})
            continue
        
        # 3. Generate 2 videos in parallel
        video_a, video_b = generate_dual_videos(trimmed_path, video_title, creator_name)
        
        if not video_a and not video_b:
            print("  ⚠️ Both video generations failed\n")
            db.update_lead_by_channel(channel_id, {"status": LeadStatus.APPROVED})
            continue
        
        # Handle partial success
        if not video_a:
            print("  ⚠️ Video A failed, using B only")
            video_a = video_b  # Use B for both
        if not video_b:
            print("  ⚠️ Video B failed, using A only")
            video_b = video_a  # Use A for both
        
        # 4. Store both videos
        db.set_dual_videos_generated(
            channel_id=channel_id,
            video_a=video_a,  # type: ignore[arg-type]
            video_b=video_b,  # type: ignore[arg-type]
            audio_path=str(trimmed_path)
        )
        
        print(f"  ✅ Dual videos ready for review:")
        if video_a and video_b:
            print(f"     A: {video_a['branded_player_url']}")
            print(f"     B: {video_b['branded_player_url']}")
        print()
    
    # Print summary
    stats = db.get_pipeline_stats()
    print("="*50)
    print("Video Generation Complete!")
    print(f"  Pending Review: {stats.get(LeadStatus.ASSET_PENDING_REVIEW, 0)}")
    print(f"  Still Approved: {stats.get(LeadStatus.APPROVED, 0)}")
    print("\n📌 Next Step:")
    print("  Run: python 3c_accept_videos.py")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate dual video assets for approved leads")
    parser.add_argument("--limit", type=int, help="Limit number of leads to process")
    parser.add_argument("--test-mode", action="store_true", help="Skip real generation, use mock URLs")
    args = parser.parse_args()
    
    process_leads(limit=args.limit, test_mode=args.test_mode)
