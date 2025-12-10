#!/usr/bin/env python3
"""
Export Audios for Manual Video Generation.

Downloads/Trims audio for all APPROVED leads into a dated folder.
"""
import os
import sys
import shutil
import subprocess
import re
from pathlib import Path
from datetime import datetime
import yt_dlp

# Add parent directory to path to import db_client
sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_db, LeadStatus

# Configuration
AUDIO_DIR = Path(__file__).parent.parent.parent / "assets" / "audio_cache"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

EXPORT_BASE_DIR = Path(__file__).parent.parent.parent / "audios"
EXPORT_BASE_DIR.mkdir(parents=True, exist_ok=True)

TRIM_DURATION = 300  # 5 minutes

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def download_audio(video_url, video_id):
    """Download audio from YouTube video using yt-dlp."""
    # We download the best audio (likely m4a or webm) and let trim_audio handle the MP3 conversion
    # This avoids double conversion and potential ffmpeg issues within yt-dlp
    
    # Check if any file with this video_id exists
    for existing in AUDIO_DIR.glob(f"{video_id}.*"):
        return existing

    print(f"    Downloading audio from {video_url}...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(AUDIO_DIR / f"{video_id}.%(ext)s"),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
            info = ydl.extract_info(video_url, download=True)
            if not info:
                return None
            # Find the downloaded file
            ext = info.get('ext', 'm4a')
            downloaded_path = AUDIO_DIR / f"{video_id}.{ext}"
            if downloaded_path.exists():
                return downloaded_path
            # Fallback search
            for f in AUDIO_DIR.glob(f"{video_id}.*"):
                return f
            return None
    except Exception as e:
        print(f"    Download failed: {e}")
        return None

def trim_audio(input_path, output_path, duration=TRIM_DURATION):
    """
    Trim audio to first N seconds using ffmpeg.
    """
    if output_path.exists():
        return output_path
    
    # Force re-encoding to MP3 to handle WAV inputs and ensure compatibility
    cmd = [
        'ffmpeg', '-y',
        '-i', str(input_path),
        '-t', str(duration),
        '-acodec', 'libmp3lame',
        '-q:a', '2',
        '-loglevel', 'error',
        str(output_path)
    ]
    
    try:
        subprocess.run(cmd, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"    Trim failed: {e}")
        return None

def main():
    db = get_db()
    leads = list(db.get_leads_by_status(LeadStatus.APPROVED))
    
    if not leads:
        print("No APPROVED leads found.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    export_dir = EXPORT_BASE_DIR / today
    export_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Found {len(leads)} approved leads.")
    print(f"Exporting audios to: {export_dir}")
    
    for i, lead in enumerate(leads, 1):
        channel_name = lead.get("channel_name", "Unknown")
        safe_name = sanitize_filename(channel_name)
        print(f"[{i}/{len(leads)}] Processing {channel_name}...")
        
        # Determine source audio
        local_audio = lead.get("local_audio_path")
        
        # Handle nested source_video structure
        source_video = lead.get("source_video", {})
        video_id = lead.get("video_id") or source_video.get("video_id")
        video_url = lead.get("video_url")
        
        if not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        source_path = None
        
        if local_audio and os.path.exists(local_audio):
            print(f"    Using local audio: {local_audio}")
            source_path = Path(local_audio)
        elif video_url and video_id:
            source_path = download_audio(video_url, video_id)
        else:
            print("    ⚠️ No audio source available (no local file or video URL)")
            continue
            
        if not source_path or not source_path.exists():
            print("    ⚠️ Source audio not found")
            continue
            
        # Trim and export
        dest_filename = f"{safe_name}.mp3"
        dest_path = export_dir / dest_filename
        
        if trim_audio(source_path, dest_path):
            print(f"    ✅ Exported: {dest_filename}")
        else:
            print("    ❌ Failed to export")

if __name__ == "__main__":
    main()
