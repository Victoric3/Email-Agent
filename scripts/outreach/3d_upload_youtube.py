#!/usr/bin/env python3
"""
Step 3d: Upload Videos to YouTube.

Uploads approved videos to YouTube as unlisted.
Uses 4 channels in round-robin to handle rate limits (6 uploads/day per channel).

Requirements:
- Google Cloud project with YouTube Data API v3 enabled
- OAuth credentials for each YouTube channel
- See getYoutubeCredentials.md for setup instructions

Environment Variables:
- YOUTUBE_CHANNELS: JSON array of channel configs with OAuth tokens
"""
import json
import os
import sys
import argparse
import requests
import time
from pathlib import Path
from datetime import datetime, timedelta
from itertools import cycle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_db, LeadStatus
from dotenv import load_dotenv

load_dotenv()

# Configuration
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
VIDEOS_PER_CHANNEL_PER_DAY = 5  # Stay under 6 to be safe
TOTAL_DAILY_LIMIT = 20  # 4 channels x 5 videos

# Directories
CREDENTIALS_DIR = Path(__file__).parent.parent.parent / "credentials"
CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_DOWNLOAD_DIR = Path(__file__).parent.parent.parent / "assets" / "videos_for_upload"
VIDEO_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Track daily uploads per channel
UPLOAD_TRACKER_FILE = Path(__file__).parent.parent.parent / "data" / "youtube_upload_tracker.json"


def load_youtube_channels():
    """
    Load YouTube channel configurations from environment.
    Expected format: JSON array of channel objects with OAuth tokens.
    """
    env_channels = os.getenv("YOUTUBE_CHANNELS")
    if not env_channels:
        print("⚠️ ERROR: YOUTUBE_CHANNELS not found in environment.")
        print("See getYoutubeCredentials.md for setup instructions.")
        sys.exit(1)
    
    try:
        channels = json.loads(env_channels)
        if not isinstance(channels, list) or len(channels) == 0:
            raise ValueError("YOUTUBE_CHANNELS must be a non-empty JSON array")
        return channels
    except Exception as e:
        print(f"⚠️ ERROR parsing YOUTUBE_CHANNELS: {e}")
        sys.exit(1)


def get_upload_tracker():
    """Load or initialize the upload tracker."""
    UPLOAD_TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    if UPLOAD_TRACKER_FILE.exists():
        with open(UPLOAD_TRACKER_FILE, 'r') as f:
            tracker = json.load(f)
    else:
        tracker = {"date": None, "channels": {}}
    
    # Reset if it's a new day
    today = datetime.now().strftime("%Y-%m-%d")
    if tracker.get("date") != today:
        tracker = {"date": today, "channels": {}}
        save_upload_tracker(tracker)
    
    return tracker


def save_upload_tracker(tracker):
    """Save the upload tracker."""
    with open(UPLOAD_TRACKER_FILE, 'w') as f:
        json.dump(tracker, f, indent=2)


def get_channel_uploads_today(tracker, channel_id):
    """Get number of uploads for a channel today."""
    return tracker.get("channels", {}).get(channel_id, 0)


def increment_channel_uploads(tracker, channel_id):
    """Increment upload count for a channel."""
    if "channels" not in tracker:
        tracker["channels"] = {}
    tracker["channels"][channel_id] = tracker["channels"].get(channel_id, 0) + 1
    save_upload_tracker(tracker)


def get_youtube_service(channel_config):
    """
    Get authenticated YouTube service for a channel.
    Uses stored OAuth tokens from environment.
    """
    channel_id = channel_config["channel_id"]
    
    # Build credentials from stored tokens
    creds_data = {
        "token": channel_config.get("access_token"),
        "refresh_token": channel_config.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": channel_config.get("client_id"),
        "client_secret": channel_config.get("client_secret"),
        "scopes": SCOPES
    }
    
    credentials = Credentials.from_authorized_user_info(creds_data, SCOPES)
    
    # Refresh if expired
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            # Note: In production, you'd want to update the stored token
            print(f"  Refreshed credentials for channel {channel_id[:8]}...")
        except Exception as e:
            print(f"  ⚠️ Failed to refresh credentials: {e}")
            return None
    
    try:
        return build('youtube', 'v3', credentials=credentials)
    except Exception as e:
        print(f"  ⚠️ Failed to build YouTube service: {e}")
        return None


def download_video_for_upload(s3_url, video_id):
    """
    Download video from S3 URL to local file for upload.
    Returns local path.
    """
    local_path = VIDEO_DOWNLOAD_DIR / f"{video_id}.mp4"
    
    if local_path.exists():
        print(f"    Video already downloaded: {local_path.name}")
        return local_path
    
    print(f"    Downloading video from S3...")
    try:
        resp = requests.get(s3_url, stream=True)
        resp.raise_for_status()
        
        with open(local_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return local_path
    except Exception as e:
        print(f"    Download failed: {e}")
        return None


def upload_to_youtube(youtube_service, video_path, title, description):
    """
    Upload video to YouTube as unlisted.
    Returns (video_id, video_url) on success.
    """
    body = {
        'snippet': {
            'title': title[:100],  # YouTube limit
            'description': description[:5000],  # YouTube limit
            'tags': ['education', 'animation', 'EulaIQ'],
            'categoryId': '27'  # Education
        },
        'status': {
            'privacyStatus': 'unlisted',
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(
        str(video_path),
        mimetype='video/mp4',
        resumable=True,
        chunksize=1024*1024  # 1MB chunks
    )
    
    try:
        request = youtube_service.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media
        )
        
        response = None
        print(f"    Uploading", end="", flush=True)
        
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(".", end="", flush=True)
        
        print(" Done!")
        
        video_id = response['id']
        video_url = f"https://youtu.be/{video_id}"
        
        return video_id, video_url
        
    except HttpError as e:
        print(f"\n    Upload failed: {e}")
        return None, None
    except Exception as e:
        print(f"\n    Upload error: {e}")
        return None, None


def select_channel_for_upload(channels, tracker):
    """
    Select the next channel to use for upload (round-robin with daily limits).
    Returns channel config or None if all channels are at limit.
    """
    for channel in channels:
        channel_id = channel["channel_id"]
        uploads_today = get_channel_uploads_today(tracker, channel_id)
        
        if uploads_today < VIDEOS_PER_CHANNEL_PER_DAY:
            return channel
    
    return None  # All channels at limit


def process_uploads(limit=None, dry_run=False):
    """
    Upload approved videos to YouTube.
    """
    db = get_db()
    channels = load_youtube_channels()
    tracker = get_upload_tracker()
    
    # Get leads ready for upload
    leads = db.get_leads_for_upload()
    
    if not leads:
        print("No videos approved for upload.")
        print("Run 3c_accept_videos.py first to approve videos.")
        return
    
    if limit:
        leads = leads[:limit]
    
    # Check daily capacity
    total_today = sum(tracker.get("channels", {}).values())
    remaining_capacity = TOTAL_DAILY_LIMIT - total_today
    
    print(f"Found {len(leads)} videos to upload")
    print(f"Daily capacity: {remaining_capacity}/{TOTAL_DAILY_LIMIT} remaining")
    print(f"Channels: {len(channels)}")
    print()
    
    if remaining_capacity <= 0:
        print("⚠️ Daily upload limit reached. Try again tomorrow.")
        return
    
    uploaded = 0
    failed = 0
    
    for i, lead in enumerate(leads, 1):
        if uploaded >= remaining_capacity:
            print(f"\n⚠️ Daily limit reached. {len(leads) - i + 1} videos remaining for tomorrow.")
            break
        
        channel_id = lead["channel_id"]
        creator_name = lead.get("creator_name", lead.get("channel_name", "Unknown"))
        video_title = lead.get("video_title", "Unknown Video")
        s3_url = lead.get("s3_video_url")
        
        print(f"[{i}/{len(leads)}] {creator_name}")
        print(f"  Title: {video_title}")
        
        if not s3_url:
            print("  ⚠️ No S3 URL found - skipping")
            failed += 1
            continue
        
        # Select a channel that hasn't hit daily limit
        yt_channel = select_channel_for_upload(channels, tracker)
        if not yt_channel:
            print("  ⚠️ All channels at daily limit")
            break
        
        print(f"  Using channel: {yt_channel.get('name', yt_channel['channel_id'][:8])}")
        
        if dry_run:
            print(f"  [DRY RUN] Would upload to YouTube")
            continue
        
        # Download video
        video_path = download_video_for_upload(s3_url, lead.get("eulaiq_video_id", channel_id[:8]))
        if not video_path:
            print("  ⚠️ Video download failed - skipping")
            failed += 1
            continue
        
        # Get YouTube service
        youtube_service = get_youtube_service(yt_channel)
        if not youtube_service:
            print("  ⚠️ Failed to authenticate with YouTube - skipping")
            failed += 1
            continue
        
        # Prepare description
        description = f"""Animation demo for {creator_name}

Original video: {lead.get('video_url', 'N/A')}

Created with EulaIQ - AI-powered educational animation
"""
        
        # Upload
        yt_video_id, yt_url = upload_to_youtube(
            youtube_service,
            video_path,
            f"[Demo] {video_title}",
            description
        )
        
        if yt_video_id:
            # Update database
            db.set_youtube_uploaded(
                channel_id=channel_id,
                youtube_video_id=yt_video_id,
                youtube_url=yt_url,
                channel_used=yt_channel["channel_id"]
            )
            
            # Update tracker
            increment_channel_uploads(tracker, yt_channel["channel_id"])
            
            uploaded += 1
            print(f"  ✅ Uploaded: {yt_url}")
        else:
            failed += 1
            print("  ❌ Upload failed")
        
        # Small delay between uploads
        if i < len(leads):
            time.sleep(2)
    
    print("\n" + "="*50)
    print("Upload Summary:")
    print(f"  ✅ Uploaded: {uploaded}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📊 Remaining today: {remaining_capacity - uploaded}")
    
    if uploaded > 0:
        print("\n📌 Next Step:")
        print("  Run: python 4_draft_emails.py")


def show_upload_status():
    """Show current upload status and capacity."""
    channels = load_youtube_channels()
    tracker = get_upload_tracker()
    
    print(f"📊 YouTube Upload Status - {tracker.get('date', 'N/A')}")
    print("="*50)
    
    total = 0
    for channel in channels:
        channel_id = channel["channel_id"]
        name = channel.get("name", channel_id[:12])
        uploads = get_channel_uploads_today(tracker, channel_id)
        total += uploads
        
        bar = "█" * uploads + "░" * (VIDEOS_PER_CHANNEL_PER_DAY - uploads)
        print(f"  {name}: [{bar}] {uploads}/{VIDEOS_PER_CHANNEL_PER_DAY}")
    
    print("="*50)
    print(f"  Total: {total}/{TOTAL_DAILY_LIMIT}")
    
    # Show leads ready for upload
    db = get_db()
    leads = db.get_leads_for_upload()
    print(f"\n  Videos waiting: {len(leads)}")


def show_uploaded():
    """Show videos that have been uploaded to YouTube."""
    db = get_db()
    leads = db.get_uploaded_leads()
    
    if not leads:
        print("No videos have been uploaded yet.")
        return
    
    from tabulate import tabulate
    
    table_data = []
    for lead in leads:
        table_data.append([
            lead.get("creator_name", "")[:15],
            lead.get("youtube_url", "")[:40],
            lead.get("youtube_channel_used", "")[:10] + "...",
            lead.get("uploaded_at", "")[:10] if lead.get("uploaded_at") else "-"
        ])
    
    headers = ["Creator", "YouTube URL", "Channel", "Uploaded"]
    print(tabulate(table_data, headers=headers, tablefmt="simple"))
    print(f"\nTotal: {len(leads)} videos uploaded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload approved videos to YouTube")
    parser.add_argument("--limit", type=int, help="Limit number of videos to upload")
    parser.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    parser.add_argument("--status", action="store_true", help="Show upload status and capacity")
    parser.add_argument("--uploaded", action="store_true", help="List uploaded videos")
    
    args = parser.parse_args()
    
    if args.status:
        show_upload_status()
    elif args.uploaded:
        show_uploaded()
    else:
        process_uploads(limit=args.limit, dry_run=args.dry_run)
