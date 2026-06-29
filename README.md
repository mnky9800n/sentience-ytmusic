# Sentience Music Memory

A one-off script that reads your **liked songs from YouTube Music** and saves
them as a **memory in [Sentience](https://api.sentience.com)**.

## Demo flow

```bash
uv run onboard.py
```

1. Paste your Sentience API key (`sent_...`).
2. The browser opens to a Google sign-in. Click your account, click Allow.
3. The script auto-detects approval, fetches your liked songs, and writes a
   single memory of your music to Sentience.

No codes to type, no "press Enter" — pick your Google identity and it's done.

## One-time setup (you, before the demo)

So the person clicking through never touches Google Cloud Console, embed an
OAuth client once. Create one at <https://console.cloud.google.com>:

- Enable **YouTube Data API v3** (APIs & Services -> Library).
- Credentials -> Create Credentials -> OAuth client ID.
- Application type: **TVs and Limited Input devices**.

Then provide the client to the script either way:

```bash
export YTM_OAUTH_CLIENT_ID="...apps.googleusercontent.com"
export YTM_OAUTH_CLIENT_SECRET="..."
```

or hardcode `EMBEDDED_CLIENT_ID` / `EMBEDDED_CLIENT_SECRET` near the top of
`onboard.py`. If neither is set, the script falls back to prompting for them.

> Note: while the OAuth app is unverified/in "Testing", add each Google account
> as a test user, and logins refresh roughly weekly. Fine for a demo.

## What it leaves behind

- `oauth.json` — the refreshing OAuth token, reused on later runs.
- `oauth_client.json` — only if you entered the client interactively.
- `liked_songs.json` — a local backup of the raw fetched tracks.

All contain account data, so they are gitignored.
