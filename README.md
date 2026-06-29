# Sentience Music Memory

A one-off script that reads your **liked songs from YouTube Music** and saves
them as a single **memory in [Sentience](https://sentience.company)**, a
snapshot of your music taste that your Sentience can remember.

Runs locally on your own machine with your own accounts. Nothing is shared
with anyone else.

## What you need

- [uv](https://docs.astral.sh/uv/) (Python runner)
- A **Sentience API key** (starts with `sent_`), from your Sentience settings
- A free **Google OAuth client** you create yourself (one time, ~2 minutes)

## 1. Get the code and add your Sentience key

```bash
git clone https://github.com/mnky9800n/sentience-ytmusic.git && cd sentience-music-memory
```

Create a `.env` file with your Sentience key:

```
SENTIENCE_API_KEY=sent_your_key_here
```

## 2. Create your own Google OAuth client (one time)

YouTube Music has no public API, so the script signs in with Google on your
behalf. You make your own OAuth client so you are never relying on anyone
else's, and you are the only person who can use it.

In <https://console.cloud.google.com>:

1. Create (or pick) a project.
2. **APIs & Services -> Library** -> enable **YouTube Data API v3**.
3. **APIs & Services -> OAuth consent screen**:
   - User type: **External**, keep it in **Testing** status.
   - Add the scope `https://www.googleapis.com/auth/youtube`.
   - Under **Test users**, add your own Google account (the one whose liked
     songs you want).
4. **APIs & Services -> Credentials -> Create Credentials -> OAuth client ID**:
   - Application type: **TVs and Limited Input devices**.
   - Copy the **Client ID** and **Client secret**.

You can either paste those when the script asks, or add them to `.env`:

```
YTM_OAUTH_CLIENT_ID=...apps.googleusercontent.com
YTM_OAUTH_CLIENT_SECRET=GOCSPX-...
```

## 3. Run it

```bash
uv run onboard.py
```

A browser opens to Google sign-in. Pick your account, click **Allow** (you will
see an "unverified app" warning because your app is in Testing; click
**Advanced -> continue**, it is your own app). The script then fetches all your
liked songs and writes one memory to Sentience.

No codes to type, no "press Enter", pick your Google identity and it is done.

## Notes

- The liked list comes back **newest-liked first**. YouTube does not expose the
  date you liked each song, so order is your only recency signal.
- Titles come straight from YouTube, so some carry suffixes like
  "(Official Video)". Artist names have " - Topic" stripped.
- Google access tokens last about an hour; the script refreshes automatically
  using your client id/secret, so keep those available on later runs.

## What it leaves behind (all gitignored)

## requirements
   - requests>=2.34.2
   - ytmusicapi>=1.12.1

- `oauth.json` — your refreshing OAuth token, reused on later runs.
- `oauth_client.json` — your client id/secret, only if entered interactively.
- `liked_songs.json` — a local backup of the raw fetched tracks.
- `.env` — your secrets.
