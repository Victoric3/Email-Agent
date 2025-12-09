#!/usr/bin/env python3
"""
Helper script to get YouTube OAuth refresh tokens.

Run this once for each YouTube channel to obtain refresh tokens.
The tokens are saved to a JSON file that you can copy to your .env.
"""
import os
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Scopes needed for uploading and fetching channel info
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly'
]

# Paths
CREDENTIALS_DIR = Path(__file__).parent.parent.parent / "credentials"
CLIENT_SECRET_FILE = CREDENTIALS_DIR / "client_secret.json"
TOKENS_FILE = CREDENTIALS_DIR / "youtube_tokens.json"


def get_channel_info(credentials):
    """Get the channel ID and name for the authenticated user."""
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        response = youtube.channels().list(
            part='snippet',
            mine=True
        ).execute()
        
        if response.get('items'):
            channel = response['items'][0]
            return {
                'channel_id': channel['id'],
                'name': channel['snippet']['title']
            }
    except Exception as e:
        print(f"Warning: Could not fetch channel info: {e}")
    
    return {'channel_id': 'UNKNOWN', 'name': 'UNKNOWN'}


def authorize_channel():
    """Run OAuth flow for a single channel."""
    
    # Check for client secret file
    if not CLIENT_SECRET_FILE.exists():
        print(f"❌ Client secret file not found: {CLIENT_SECRET_FILE}")
        print("\nTo get this file:")
        print("1. Go to Google Cloud Console → APIs & Services → Credentials")
        print("2. Create OAuth 2.0 Client ID (Desktop app)")
        print("3. Download JSON and save as: credentials/client_secret.json")
        return None
    
    print("\n🔐 YouTube Authorization")
    print("="*50)
    print("A browser window will open. Sign in with the Google account")
    print("that owns the YouTube channel you want to add.")
    print("="*50)
    
    try:
        # Run OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET_FILE),
            SCOPES
        )
        
        credentials = flow.run_local_server(
            port=8080,
            prompt='consent',
            access_type='offline'  # This ensures we get a refresh token
        )
        
        # Get channel info
        channel_info = get_channel_info(credentials)
        
        # Build token data
        token_data = {
            'channel_id': channel_info['channel_id'],
            'name': channel_info['name'],
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'refresh_token': credentials.refresh_token,
            'access_token': credentials.token
        }
        
        return token_data
        
    except Exception as e:
        print(f"❌ Authorization failed: {e}")
        return None


def load_existing_tokens():
    """Load existing tokens from file."""
    if TOKENS_FILE.exists():
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_tokens(tokens):
    """Save tokens to file."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)


def main():
    print("\n" + "="*60)
    print("YouTube OAuth Token Generator")
    print("="*60)
    
    # Load existing tokens
    tokens = load_existing_tokens()
    
    print(f"\nCurrently have {len(tokens)} channel(s) configured.")
    
    if tokens:
        print("\nExisting channels:")
        for i, t in enumerate(tokens, 1):
            print(f"  {i}. {t.get('name', 'Unknown')} ({t.get('channel_id', 'Unknown')[:12]}...)")
    
    print("\nOptions:")
    print("  [a] Add a new channel")
    print("  [r] Remove a channel")
    print("  [e] Export for .env")
    print("  [q] Quit")
    
    while True:
        choice = input("\nChoice: ").lower().strip()
        
        if choice == 'q':
            break
        
        elif choice == 'a':
            token_data = authorize_channel()
            
            if token_data:
                # Check if channel already exists (only if we have a valid ID)
                if token_data['channel_id'] != 'UNKNOWN':
                    existing = [t for t in tokens if t['channel_id'] == token_data['channel_id']]
                    if existing:
                        print(f"\n⚠️ Channel {token_data['name']} already exists. Updating...")
                        tokens = [t for t in tokens if t['channel_id'] != token_data['channel_id']]
                
                # If ID is UNKNOWN, we just append it (user can fix later or retry)
                # But better to warn them
                if token_data['channel_id'] == 'UNKNOWN':
                    print("\n⚠️ Warning: Could not identify channel ID. Token saved as UNKNOWN.")
                    print("   You might need to manually edit the .env file later.")
                
                tokens.append(token_data)
                save_tokens(tokens)
                
                print(f"\n✅ Added channel: {token_data['name']}")
                print(f"   Channel ID: {token_data['channel_id']}")
                print(f"   Total channels: {len(tokens)}")
        
        elif choice == 'r':
            if not tokens:
                print("No channels to remove.")
                continue
            
            print("\nSelect channel to remove:")
            for i, t in enumerate(tokens, 1):
                print(f"  {i}. {t.get('name', 'Unknown')}")
            
            try:
                idx = int(input("Number: ")) - 1
                if 0 <= idx < len(tokens):
                    removed = tokens.pop(idx)
                    save_tokens(tokens)
                    print(f"✅ Removed: {removed.get('name')}")
            except (ValueError, IndexError):
                print("Invalid selection.")
        
        elif choice == 'e':
            if not tokens:
                print("No channels configured. Add channels first.")
                continue
            
            # Format for .env
            env_value = json.dumps(tokens)
            
            print("\n" + "="*60)
            print("Add this to your .env file:")
            print("="*60)
            print(f"\nYOUTUBE_CHANNELS={env_value}")
            print("\n" + "="*60)
            
            # Also save to a separate file for easy copying
            env_export_file = CREDENTIALS_DIR / "youtube_channels_env.txt"
            with open(env_export_file, 'w') as f:
                f.write(f"YOUTUBE_CHANNELS={env_value}\n")
            
            print(f"\nAlso saved to: {env_export_file}")
        
        else:
            print("Invalid choice. Use: a, r, e, or q")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
