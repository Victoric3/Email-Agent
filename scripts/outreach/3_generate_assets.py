#!/usr/bin/env python3
"""
Step 3: Generate Video Assets.

Downloads audio from YouTube, generates animated videos via EulaIQ API,
and registers branded player links. Updates MongoDB with asset info.
"""
import json
import os
import time
import datetime
import requests
import yt_dlp
from pathlib import Path
from itertools import cycle
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))  # Add scripts/ to path

from db_client import get_db, LeadStatus

# Configuration
AUDIO_DIR = Path(__file__).parent.parent.parent / "assets" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# EulaIQ API Config
API_BASE_URL = "https://api.eulaiq.com/api/v1"
RENDER_API_URL = "https://render.eulaiq.com"

# Accounts for Round-Robin (30 videos/day each = 90 total)
# Prefer to load accounts from environment variable EULAIQ_ACCOUNTS as JSON.
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

# Fallback to hard-coded accounts only if env var not provided (not recommended)
if not ACCOUNTS:
    print("⚠️ ERROR: No EulaIQ accounts found. Define EULAIQ_ACCOUNTS in your environment or .env (see .env.example). Aborting.")
    sys.exit(1)

account_iterator = cycle(ACCOUNTS)

# Cache for auth tokens
auth_tokens = {}


def get_auth_token(account):
    """Login and return Bearer token for the given account."""
    email = account["identity"]
    if email in auth_tokens:
        return auth_tokens[email]
    
    print(f"  Logging in as {email}...")
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
        print(f"  Login failed for {email}: {e}")
        return None


def download_audio(video_url, video_id):
    """Download audio from YouTube video using yt-dlp."""
    output_path = AUDIO_DIR / f"{video_id}.mp3"
    
    if output_path.exists():
        print(f"  Audio already exists: {output_path.name}")
        return output_path

    print(f"  Downloading audio...")
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
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return output_path
    except Exception as e:
        print(f"  Download failed: {e}")
        return None


def generate_video(audio_path, title, token):
    """Upload audio and trigger video generation."""
    print(f"  Triggering generation...")
    
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
                'title': title,
                'description': f"Animation for: {title}",
                'videoOptions': json.dumps(video_options)
            }
            
            resp = requests.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            result = resp.json()
            return result.get("data", {}).get("videoId")
    except Exception as e:
        print(f"  Generation trigger failed: {e}")
        return None


def poll_status(video_id, token, max_wait=1800):
    """Poll video status until completed (max 30 min)."""
    url = f"{API_BASE_URL}/video/status/video/{video_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"  Polling status", end="", flush=True)
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                status = data.get("status")
                
                if status == "completed":
                    print(" ✅ Done!")
                    return data.get("videoUrl")  # S3 URL
                elif status == "failed":
                    print(" ❌ Failed!")
                    return None
                
            time.sleep(30)
            print(".", end="", flush=True)
        except Exception as e:
            print(f"\n  Polling error: {e}")
            time.sleep(30)
    
    print(" ⏰ Timeout!")
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
        print(f"  Player registration failed: {e}")
        return None


def process_assets(limit=None):
    """
    Process all qualified leads: download audio, generate video, register link.
    Updates MongoDB with results.
    """
    db = get_db()
    
    # Get leads that need asset generation
    leads = db.get_leads_by_status(LeadStatus.QUALIFIED)
    
    if not leads:
        print("No qualified leads pending asset generation.")
        return
    
    if limit:
        leads = leads[:limit]
    
    print(f"Found {len(leads)} leads to process.\n")
    
    for i, lead in enumerate(leads, 1):
        channel_id = lead["channel_id"]
        print(f"[{i}/{len(leads)}] {lead['creator_name']} - {lead['video_title']}")
        
        # Mark as generating
        db.update_lead_by_channel(channel_id, {"status": LeadStatus.ASSET_GENERATING})
        
        # 1. Download Audio
        audio_path = download_audio(lead["video_url"], lead["video_id"])
        if not audio_path or not audio_path.exists():
            print("  ⚠️ Skipping (Audio download failed)\n")
            db.update_lead_by_channel(channel_id, {"status": LeadStatus.QUALIFIED})  # Reset
            continue
        
        # 2. Get Account & Token (Round Robin)
        account = next(account_iterator)
        token = get_auth_token(account)
        if not token:
            print("  ⚠️ Skipping (Auth failed)\n")
            db.update_lead_by_channel(channel_id, {"status": LeadStatus.QUALIFIED})
            continue
        
        # 3. Generate Video
        eulaiq_video_id = generate_video(audio_path, lead["video_title"], token)
        if not eulaiq_video_id:
            print("  ⚠️ Skipping (Generation trigger failed)\n")
            db.update_lead_by_channel(channel_id, {"status": LeadStatus.QUALIFIED})
            continue
        
        # 4. Poll for Completion (S3 URL)
        s3_url = poll_status(eulaiq_video_id, token)
        if not s3_url:
            print("  ⚠️ Skipping (Rendering failed or timeout)\n")
            db.update_lead_by_channel(channel_id, {"status": LeadStatus.QUALIFIED})
            continue
        
        # 5. Register Branded Link
        branded_url = register_player_link(lead["video_title"], s3_url, lead["creator_name"])
        
        if branded_url:
            print(f"  🎬 Asset Ready: {branded_url}\n")
            db.set_asset_generated(
                channel_id=channel_id,
                branded_url=branded_url,
                s3_url=s3_url,
                eulaiq_video_id=eulaiq_video_id
            )
        else:
            # Even without branded URL, save the S3 URL
            print(f"  ⚠️ Using S3 URL directly (player registration failed)\n")
            db.set_asset_generated(
                channel_id=channel_id,
                branded_url=s3_url,  # Fallback to S3 URL
                s3_url=s3_url,
                eulaiq_video_id=eulaiq_video_id
            )
    
    # Print summary
    stats = db.get_pipeline_stats()
    print("="*50)
    print("Asset Generation Complete!")
    print(f"  Assets Generated: {stats.get(LeadStatus.ASSET_GENERATED, 0)}")
    print(f"  Still Pending: {stats.get(LeadStatus.QUALIFIED, 0)}")


def process_assets_test_mode(limit=None):
    """
    TEST MODE: Skip actual video generation, use mock URLs.
    For testing the email pipeline without consuming API credits.
    """
    db = get_db()
    
    leads = db.get_leads_by_status(LeadStatus.QUALIFIED)
    
    if not leads:
        print("No qualified leads pending asset generation.")
        return
    
    if limit:
        leads = leads[:limit]
    
    print(f"[TEST MODE] Found {len(leads)} leads to process.\n")
    
    for i, lead in enumerate(leads, 1):
        channel_id = lead["channel_id"]
        source_video = lead.get("source_video", {})
        video_id = source_video.get("video_id", channel_id[:8])
        video_title = source_video.get("title", "Unknown Video")
        creator_name = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        
        print(f"[{i}/{len(leads)}] {creator_name} - {video_title}")
        
        # Use a demo video link (real EulaIQ player link for testing)
        mock_branded_url = f"https://render.eulaiq.com/player/demo_{video_id[:8]}"
        mock_s3_url = f"https://eulaiq-renders.s3.amazonaws.com/test/{video_id}.mp4"
        
        db.set_asset_generated(
            channel_id=channel_id,
            branded_url=mock_branded_url,
            s3_url=mock_s3_url,
            eulaiq_video_id=f"test_{video_id[:12]}"
        )
        
        print(f"  🎬 [MOCK] Asset Ready: {mock_branded_url}\n")
    
    print("="*50)
    print("[TEST MODE] Asset Generation Complete!")
    stats = db.get_pipeline_stats()
    print(f"  Assets Generated: {stats.get(LeadStatus.ASSET_GENERATED, 0)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate video assets for qualified leads")
    parser.add_argument("--limit", type=int, help="Limit number of leads to process")
    parser.add_argument("--test-mode", action="store_true", help="Skip real generation, use mock URLs")
    args = parser.parse_args()
    
    if args.test_mode:
        process_assets_test_mode(limit=args.limit)
    else:
        process_assets(limit=args.limit)
