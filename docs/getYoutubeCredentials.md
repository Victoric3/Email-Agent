# Getting YouTube API Credentials (Simple & Recommended)

This guide is a concise, step-by-step walkthrough to get OAuth tokens for multiple YouTube channels. The recommended path is to create a Desktop OAuth client and use the helper script `get_youtube_token.py`. If you already have Web credentials, a second path is described below.

Overview:
- We upload demos as unlisted videos, rotating across 4 channels to stay under the ~6-uploads/day limit per channel.
- Required: Google Cloud project, YouTube Data API enabled, OAuth client credentials, and one refresh token per channel.

Quick Recommendation: Use a Desktop OAuth client and `get_youtube_token.py`.

---

## Quick Steps (Recommended - easiest)
1. Create a Desktop OAuth client (Credentials → Create → OAuth client ID → Desktop app).
2. Save the JSON as `credentials/client_secret.json`.
3. Add your 4 channel Google accounts as “Test users” in the OAuth consent screen (if your app is not verified).
4. Run the helper and collect refresh tokens:
   ```bash
   cd scripts/outreach
   python get_youtube_token.py
   ```
   - Press `a` to add a channel and follow the browser OAuth flow (sign in to each channel account separately).
   - Repeat for each channel (4 times).
5. Add the exported `YOUTUBE_CHANNELS` JSON to `.env` (see `.env` example below).

Why this is best: Desktop clients let the helper script complete the OAuth flow (no web server needed). The helper also exports a ready-to-use `YOUTUBE_CHANNELS` JSON block.

---

## Option B: Use Existing Web OAuth Credentials (if you already have them)
If you already have a Web / Android client (like your `Web client 2`), you can reuse it, but make sure the redirect is configured and you request offline access to get a refresh token.

1. In Google Cloud Console → Credentials → open your Web client.
2. Add `http://localhost:8080` (or the redirect your helper uses) to the **Authorized redirect URIs**.
3. Ensure the OAuth consent screen includes the `youtube.upload` scope:
   - APIs & Services → OAuth consent screen → Edit App → Scopes → Add `https://www.googleapis.com/auth/youtube.upload`
4. Add the 4 channel emails under **Test users**, if your app is in testing mode.
5. Run the helper (it supports Web-client flows if redirect URI points to localhost):
   ```bash
   cd scripts/outreach
   python get_youtube_token.py
   ```
   - If for any reason the helper can’t start the web flow with your Web client, use OAuth Playground:
     - Go to https://developers.google.com/oauthplayground/
     - ⚙️ → Check “Use your own OAuth credentials” → Paste Client ID & Secret
     - Select `YouTube Data API v3` → `https://www.googleapis.com/auth/youtube.upload`
     - Click **Authorize APIs** → Sign in with the channel account → Click **Exchange authorization code for tokens** → Copy the refresh token

Notes:
- Ensure the web client uses `access_type=offline` and `prompt=consent` so Google issues a refresh token.
- If you don’t receive a refresh token (Google issues it only once per user-client pair), try `prompt=consent` or revoke previous grant and repeat the flow.

---

## The `.env` format (copy this exactly)
After you collect refresh tokens, add them to `.env` as one JSON value:
```env
YOUTUBE_CHANNELS=[{"channel_id":"UC_xxx1","name":"Channel 1","client_id":"YOUR_CLIENT_ID.apps.googleusercontent.com","client_secret":"YOUR_CLIENT_SECRET","refresh_token":"1//REFRESH_TOKEN_FOR_CHANNEL_1","access_token":""},{"channel_id":"UC_xxx2","name":"Channel 2","client_id":"YOUR_CLIENT_ID.apps.googleusercontent.com","client_secret":"YOUR_CLIENT_SECRET","refresh_token":"1//REFRESH_TOKEN_FOR_CHANNEL_2","access_token":""},...]
```

Tip: The helper will export the line into `credentials/youtube_channels_env.txt` for easy copy/paste.

---

## Test the configuration (quick)
1. Setup `.env` with the `YOUTUBE_CHANNELS` block.
2. Run:
```bash
python 3d_upload_youtube.py --status
```
You should see each channel and its daily capacity (uploads done today / uploads allowed).

---

## Troubleshooting (concise)
- Missing `youtube.upload` scope: Edit OAuth consent screen -> Scopes -> Add `https://www.googleapis.com/auth/youtube.upload`.
- No refresh token: Use `prompt=consent` or try OAuth Playground or revoke previous grant.
- OAuth Playground: Gear icon → Use your own credentials; select `youtube.upload` and exchange the code.
- "Access blocked": If unverified, add Google accounts as Test Users. If in Production, verify app or add app domain.

---

## Security
- Keep `client_secret.json` and `.env` private. Do not commit them.
- If a refresh token is leaked, revoke the OAuth grant at Google Account → Security → Third-party apps.

---

## Quick Reference Table
| What | Where |
|------|-------|
| Google Cloud Console | https://console.cloud.google.com/ |
| OAuth Playground | https://developers.google.com/oauthplayground/ |
| YouTube Studio | https://studio.youtube.com/ |
| Channel ID | YouTube Studio → Settings → Channel → Advanced |

