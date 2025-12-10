#!/usr/bin/env python3
"""
Test EulaIQ API with a single audio file to verify authentication and upload.
"""
import json
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# EulaIQ API Config
API_BASE_URL = "https://api.eulaiq.com/api/v1"

# Load accounts
env_accounts = os.getenv("EULAIQ_ACCOUNTS")
if env_accounts:
    ACCOUNTS = json.loads(env_accounts)
else:
    print("❌ No EULAIQ_ACCOUNTS found in environment")
    sys.exit(1)

# Use first account for test
account = ACCOUNTS[0]


def login(account):
    """Login and return Bearer token."""
    print(f"Logging in as {account['identity']}...")
    payload = {
        "identity": account["identity"],
        "password": account["password"],
        "ipAddress": "192.168.1.0",
        "device": {
            "userAgent": "EulaIQ-Test/1.0",
            "platform": "Windows",
            "deviceType": "script"
        }
    }
    
    try:
        resp = requests.post(f"{API_BASE_URL}/auth/login", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token")
        print(f"✅ Login successful, token: {token[:20]}...")
        return token
    except requests.exceptions.HTTPError as e:
        try:
            error_detail = e.response.json()
            print(f"❌ Login failed: {e.response.status_code} - {error_detail}")
        except:
            print(f"❌ Login failed: {e}")
        return None
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return None


def test_upload(token, audio_path):
    """Test uploading audio file to create video."""
    url = f"{API_BASE_URL}/video/createFromAudio"
    headers = {"Authorization": f"Bearer {token}"}
    
    video_options = {
        "mode": "dark",
        "aspectRatio": "16:9",
        "quality": "h",
        "frameRate": 30,
        "additionalInstructions": "Create a high-quality educational animation."
    }
    
    print(f"\nTesting upload: {audio_path.name}")
    print(f"File size: {audio_path.stat().st_size / 1024 / 1024:.2f} MB")
    
    try:
        with open(audio_path, 'rb') as f:
            files = {'audioFile': (audio_path.name, f, 'audio/mpeg')}
            data = {
                'title': 'Test Video - Linear Equations',
                'description': 'Test upload for API verification',
                'videoOptions': json.dumps(video_options)
            }
            
            print(f"Uploading to {url}...")
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=120)
            
            print(f"Response status: {resp.status_code}")
            print(f"Response headers: {dict(resp.headers)}")
            
            resp.raise_for_status()
            result = resp.json()
            print(f"✅ Upload successful!")
            print(f"Response: {json.dumps(result, indent=2)}")
            
            video_id = result.get("data", {}).get("videoId")
            if video_id:
                print(f"\n✅ Video ID: {video_id}")
            return video_id
            
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP Error: {e.response.status_code}")
        print(f"Response body: {e.response.text}")
        try:
            error_detail = e.response.json()
            print(f"Error JSON: {json.dumps(error_detail, indent=2)}")
        except:
            pass
        return None
    except Exception as e:
        print(f"\n❌ Upload failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Test with the first audio file
    audio_dir = Path(__file__).parent.parent.parent / "audios"
    test_file = audio_dir / "Linear Equations Made EASY! A Visual Guide To Algebra Fundamentals.wav"
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        sys.exit(1)
    
    # First, convert to MP3 if needed (EulaIQ might not accept WAV)
    trimmed_dir = Path(__file__).parent.parent.parent / "assets" / "audio_trimmed"
    trimmed_dir.mkdir(parents=True, exist_ok=True)
    mp3_file = trimmed_dir / "test_linear_equations.mp3"
    
    if not mp3_file.exists():
        print(f"Converting {test_file.name} to MP3...")
        import subprocess
        cmd = [
            'ffmpeg', '-i', str(test_file),
            '-t', '60',  # Just 1 minute for testing
            '-acodec', 'libmp3lame', '-q:a', '2',
            '-y', str(mp3_file)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ FFmpeg conversion failed: {result.stderr}")
            sys.exit(1)
        print(f"✅ Converted to: {mp3_file}")
    
    # Login
    token = login(account)
    if not token:
        sys.exit(1)
    
    # Test upload
    video_id = test_upload(token, mp3_file)
    
    if video_id:
        print(f"\n✅ Test completed successfully!")
        print(f"Video ID: {video_id}")
    else:
        print(f"\n❌ Test failed")
        sys.exit(1)
