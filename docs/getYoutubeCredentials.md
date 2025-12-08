# Getting YouTube API Credentials

This guide explains how to set up YouTube API credentials for uploading videos to multiple channels.

## Overview

The pipeline uploads demo videos to YouTube as unlisted. To avoid rate limits (6 uploads/day per channel), we use 4 different YouTube channels in round-robin.

**You need:**
1. A Google Cloud Project with YouTube Data API v3 enabled
2. OAuth 2.0 credentials (one set works for all channels)
3. Refresh tokens for each of your 4 YouTube channels

---

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Name it something like `eulaiq-youtube-uploader`
4. Click **Create**

---

## Step 2: Enable YouTube Data API v3

1. In your project, go to **APIs & Services** → **Library**
2. Search for "YouTube Data API v3"
3. Click on it and click **Enable**

---

## Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** (unless you have Google Workspace)
3. Click **Create**
4. Fill in:
   - App name: `EulaIQ Video Uploader`
   - User support email: Your email
   - Developer contact: Your email
5. Click **Save and Continue**
6. On **Scopes** page, click **Add or Remove Scopes**
7. Find and select: `https://www.googleapis.com/auth/youtube.upload`
8. Click **Update** → **Save and Continue**
9. On **Test users** page, add the email addresses of your 4 YouTube channels
10. Click **Save and Continue** → **Back to Dashboard**

---

## Step 4: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: `EulaIQ Uploader`
5. Click **Create**
6. **Download JSON** - save as `client_secret.json` in the `credentials/` folder

---

## Step 5: Get Refresh Tokens for Each Channel

You need to run an authorization flow for each of your 4 YouTube channels. We provide a helper script.

### Run the helper script:

```bash
cd scripts/outreach
python get_youtube_token.py
```

This will:
1. Open a browser window
2. Ask you to sign in with your YouTube channel's Google account
3. Grant permission to upload videos
4. Save the refresh token

**Repeat this 4 times** - once for each YouTube channel, signing into a different Google account each time.

### Manual method (if helper doesn't work):

1. Use the [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)
2. Click the gear icon (⚙️) → Check "Use your own OAuth credentials"
3. Enter your Client ID and Client Secret from Step 4
4. In the left panel, find "YouTube Data API v3" → Select `youtube.upload`
5. Click **Authorize APIs**
6. Sign in with your YouTube channel's Google account
7. Click **Exchange authorization code for tokens**
8. Copy the **Refresh token**

---

## Step 6: Configure Environment Variables

Add the YouTube channels to your `.env` file:

```env
YOUTUBE_CHANNELS=[
  {
    "channel_id": "UC_CHANNEL_1_ID",
    "name": "Channel 1 Name",
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "client_secret": "YOUR_CLIENT_SECRET",
    "refresh_token": "1//REFRESH_TOKEN_FOR_CHANNEL_1",
    "access_token": ""
  },
  {
    "channel_id": "UC_CHANNEL_2_ID",
    "name": "Channel 2 Name",
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "client_secret": "YOUR_CLIENT_SECRET",
    "refresh_token": "1//REFRESH_TOKEN_FOR_CHANNEL_2",
    "access_token": ""
  },
  {
    "channel_id": "UC_CHANNEL_3_ID",
    "name": "Channel 3 Name",
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "client_secret": "YOUR_CLIENT_SECRET",
    "refresh_token": "1//REFRESH_TOKEN_FOR_CHANNEL_3",
    "access_token": ""
  },
  {
    "channel_id": "UC_CHANNEL_4_ID",
    "name": "Channel 4 Name",
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "client_secret": "YOUR_CLIENT_SECRET",
    "refresh_token": "1//REFRESH_TOKEN_FOR_CHANNEL_4",
    "access_token": ""
  }
]
```

**Notes:**
- `channel_id`: Your YouTube channel ID (find in YouTube Studio → Settings → Channel → Advanced settings)
- `client_id` and `client_secret`: Same for all channels (from Step 4)
- `refresh_token`: Unique per channel (from Step 5)
- `access_token`: Leave empty - it will be auto-generated

**Important:** Put the entire JSON on one line in your `.env` file, or use proper JSON escaping.

---

## Step 7: Find Your YouTube Channel IDs

For each channel:

1. Go to [YouTube Studio](https://studio.youtube.com/)
2. Click **Settings** (gear icon) → **Channel** → **Advanced settings**
3. Copy the **Channel ID** (starts with `UC`)

Or visit your channel page and look at the URL:
- `youtube.com/channel/UCxxxxxxxx` → Channel ID is `UCxxxxxxxx`

---

## Step 8: Test the Setup

```bash
python 3d_upload_youtube.py --status
```

This should show your 4 channels with upload capacity.

---

## Troubleshooting

### "Access blocked: This app's request is invalid"
- Make sure you added test users in the OAuth consent screen (Step 3)
- The test users must be the Google accounts that own the YouTube channels

### "The user has exceeded the number of videos they may upload"
- YouTube limits uploads to ~6 per day per channel
- Wait 24 hours or use another channel

### "Invalid credentials" or "Token has been expired or revoked"
- Re-run the token generation for that channel (Step 5)
- Make sure the refresh token is correctly copied

### "Quota exceeded"
- The YouTube Data API has a daily quota
- Default is 10,000 units/day; uploads cost 1,600 units each
- You can request quota increases in Google Cloud Console

---

## Security Notes

⚠️ **Keep your credentials secure:**

- Never commit `.env` or `client_secret.json` to git
- Both are already in `.gitignore`
- Refresh tokens give full access to upload - treat them like passwords
- If compromised, revoke access in Google Account → Security → Third-party apps

---

## Quick Reference

| What | Where |
|------|-------|
| Google Cloud Console | https://console.cloud.google.com/ |
| API Library | Console → APIs & Services → Library |
| OAuth Credentials | Console → APIs & Services → Credentials |
| OAuth Playground | https://developers.google.com/oauthplayground/ |
| YouTube Studio | https://studio.youtube.com/ |
| Channel ID | YouTube Studio → Settings → Channel → Advanced |
