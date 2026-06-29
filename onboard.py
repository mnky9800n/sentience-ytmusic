"""
Sentience Music Memory — one-off onboarding script.

Grabs your liked songs from YouTube Music and writes them as a memory
into Sentience (https://api.sentience.com).

Run it once:

    uv run onboard.py

It will walk you through everything it needs.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv
from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth import OAuthCredentials
from ytmusicapi.auth.oauth.token import RefreshingToken
from ytmusicapi.constants import YTM_BASE_API

load_dotenv()  # pull SENTIENCE_API_KEY (and optional OAuth client) from .env

HERE = Path(__file__).parent
OAUTH_TOKEN_FILE = HERE / "oauth.json"          # stores the refreshing token
OAUTH_CLIENT_FILE = HERE / "oauth_client.json"  # stores client_id / client_secret
LIKED_BACKUP_FILE = HERE / "liked_songs.json"

SENTIENCE_MEMORIES_URL = "https://api.sentience.com/v1/memories"

# --------------------------------------------------------------------------- #
# Embedded Google OAuth client.
#
# Fill these in once (or set the env vars) so the person running the demo just
# clicks their Google account — no Cloud Console step. Create the client at
# console.cloud.google.com as type "TVs and Limited Input devices", with the
# YouTube Data API v3 enabled.
# --------------------------------------------------------------------------- #
EMBEDDED_CLIENT_ID = os.environ.get("YTM_OAUTH_CLIENT_ID", "")
EMBEDDED_CLIENT_SECRET = os.environ.get("YTM_OAUTH_CLIENT_SECRET", "")


# --------------------------------------------------------------------------- #
# small console helpers
# --------------------------------------------------------------------------- #
def banner(text: str) -> None:
    line = "=" * len(text)
    print(f"\n{line}\n{text}\n{line}")


def step(text: str) -> None:
    print(f"\n>>> {text}")


def prompt(text: str) -> str:
    return input(f"{text}\n  ").strip()


# --------------------------------------------------------------------------- #
# YouTube Music
# --------------------------------------------------------------------------- #
def get_oauth_client() -> tuple[str, str]:
    """Get the Google OAuth client_id / client_secret.

    Priority: embedded constants / env vars -> saved file -> interactive prompt.
    For the demo, fill in EMBEDDED_CLIENT_* so this returns immediately.
    """
    if EMBEDDED_CLIENT_ID and EMBEDDED_CLIENT_SECRET:
        return EMBEDDED_CLIENT_ID, EMBEDDED_CLIENT_SECRET

    if OAUTH_CLIENT_FILE.exists():
        cfg = json.loads(OAUTH_CLIENT_FILE.read_text())
        if cfg.get("client_id") and cfg.get("client_secret"):
            return cfg["client_id"], cfg["client_secret"]

    step("Set up a Google OAuth client (one time)")
    print(
        """  No embedded OAuth client found. Create a free one of type
  "TVs and Limited Input devices":

    1. Go to https://console.cloud.google.com -> create/select a project.
    2. APIs & Services -> Library -> enable "YouTube Data API v3".
    3. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID.
    4. Application type: "TVs and Limited Input devices".
    5. Copy the resulting Client ID and Client secret below.
"""
    )
    client_id = prompt("Paste your OAuth Client ID:")
    client_secret = prompt("Paste your OAuth Client secret:")
    if not client_id or not client_secret:
        sys.exit("Both Client ID and Client secret are required. Aborting.")

    OAUTH_CLIENT_FILE.write_text(
        json.dumps({"client_id": client_id, "client_secret": client_secret}, indent=2)
    )
    print(f"  Saved OAuth client to {OAUTH_CLIENT_FILE.name}")
    return client_id, client_secret


def device_login(credentials: OAuthCredentials) -> dict:
    """Run Google's device flow, auto-polling until the user approves.

    Opens the browser straight to the consent screen with the code pre-filled,
    so the user only clicks their Google account and approves — no code typing
    and no 'press Enter' afterward.
    """
    code = credentials.get_code()
    user_code = code["user_code"]
    url = f"{code['verification_url']}?user_code={user_code}"

    print("\n  Opening your browser to sign in with Google...")
    print(f"  If it doesn't open, go to: {url}")
    print(f"  (confirmation code, pre-filled: {user_code})\n")
    webbrowser.open(url)

    interval = int(code.get("interval", 5))
    expires_in = int(code.get("expires_in", 1800))
    waited = 0
    print("  Waiting for you to approve in the browser", end="", flush=True)
    while waited < expires_in:
        time.sleep(interval)
        waited += interval
        token = credentials.token_from_code(code["device_code"])
        if "access_token" in token:
            print("  approved!")
            return token
        error = token.get("error")
        if error in ("authorization_pending", None):
            print(".", end="", flush=True)
            continue
        if error == "slow_down":
            interval += 5
            print(".", end="", flush=True)
            continue
        print()
        sys.exit(f"  Google auth failed: {error}")
    sys.exit("\n  Timed out waiting for Google approval.")


def ensure_youtube_auth() -> YTMusic:
    """Get an authenticated YTMusic client via OAuth, reusing saved auth."""
    client_id, client_secret = get_oauth_client()
    credentials = OAuthCredentials(client_id=client_id, client_secret=client_secret)

    if OAUTH_TOKEN_FILE.exists():
        reuse = prompt(
            f"Found existing YouTube auth at {OAUTH_TOKEN_FILE.name}. Reuse it? [Y/n]"
        )
        if reuse.lower() not in {"n", "no"}:
            return _tv_client(credentials)

    step("Connect your YouTube Music account")
    raw_token = device_login(credentials)

    refresh_expires_in = raw_token.get("refresh_token_expires_in", raw_token["expires_in"])
    token = RefreshingToken(
        credentials=credentials,
        access_token=raw_token["access_token"],
        refresh_token=raw_token["refresh_token"],
        scope=raw_token["scope"],
        token_type=raw_token["token_type"],
        expires_in=refresh_expires_in,
    )
    token.update(raw_token)
    token.local_cache = OAUTH_TOKEN_FILE  # writes oauth.json
    print(f"  Saved YouTube auth to {OAUTH_TOKEN_FILE.name}")
    return _tv_client(credentials)


def _tv_client(credentials: OAuthCredentials) -> YTMusic:
    """Build a YTMusic client whose InnerTube context is the TV client.

    OAuth tokens are issued to a "TVs and Limited Input devices" client, and
    YouTube's InnerTube API rejects them under the default web (WEB_REMIX)
    context with HTTP 400. Forcing the TVHTML5 client context makes the token
    accepted. We then read the liked playlist directly (see fetch_liked_songs),
    because the library's response parsers expect the web-client shape.
    """
    yt = YTMusic(str(OAUTH_TOKEN_FILE), oauth_credentials=credentials)
    yt.context["context"]["client"]["clientName"] = "TVHTML5"
    yt.context["context"]["client"]["clientVersion"] = "7.20240101.16.00"
    return yt


def _tv_browse(yt: YTMusic, body_extra: dict) -> dict:
    """POST an InnerTube browse request with the client context merged in."""
    body = {**body_extra}
    body.update(yt.context)
    resp = yt._session.post(
        YTM_BASE_API + "browse" + yt.params, json=body, headers=yt.headers
    )
    if resp.status_code != 200:
        raise RuntimeError(f"YouTube browse failed ({resp.status_code}): {resp.text[:300]}")
    return json.loads(resp.text)


def _parse_tile(tile: dict) -> dict | None:
    """Turn a TV-client tileRenderer into a simple track dict."""
    meta = tile.get("metadata", {}).get("tileMetadataRenderer", {})
    runs = meta.get("title", {}).get("runs", [])
    title = runs[0]["text"] if runs else None
    if not title:
        return None

    lines = meta.get("lines", [])
    artist = None
    if lines:
        items = lines[0].get("lineRenderer", {}).get("items", [])
        if items:
            artist = items[0].get("lineItemRenderer", {}).get("text", {}).get("simpleText")
    if artist and artist.endswith(" - Topic"):
        artist = artist[: -len(" - Topic")]

    return {
        "title": title,
        "videoId": tile.get("contentId"),
        "artists": [{"name": artist}] if artist else [],
        "album": None,
    }


def fetch_liked_songs(yt: YTMusic, limit: int = 5000) -> list[dict]:
    step("Fetching your liked songs from YouTube Music...")

    resp = _tv_browse(yt, {"browseId": "VLLM"})
    plvr = (
        resp["contents"]["tvBrowseRenderer"]["content"]["tvSurfaceContentRenderer"]
        ["content"]["twoColumnRenderer"]["rightColumn"]["playlistVideoListRenderer"]
    )
    raw_tiles = list(plvr.get("contents", []))
    conts = plvr.get("continuations")
    token = conts[0]["nextContinuationData"]["continuation"] if conts else None

    while token and len(raw_tiles) < limit:
        page = _tv_browse(yt, {"continuation": token})
        cc = page.get("continuationContents", {}).get("playlistVideoListContinuation", {})
        raw_tiles.extend(cc.get("contents", []))
        conts = cc.get("continuations")
        token = conts[0]["nextContinuationData"]["continuation"] if conts else None
        print(f"  ...fetched {len(raw_tiles)} so far", end="\r", flush=True)

    tracks = [t for tile in raw_tiles if (t := _parse_tile(tile.get("tileRenderer", {})))]
    tracks = tracks[:limit]
    print(f"  Got {len(tracks)} liked songs." + " " * 20)
    LIKED_BACKUP_FILE.write_text(json.dumps(tracks, indent=2, ensure_ascii=False))
    print(f"  Saved a local backup to {LIKED_BACKUP_FILE.name}")
    return tracks


def format_track(track: dict) -> str:
    title = track.get("title", "Unknown title")
    artists = ", ".join(a["name"] for a in (track.get("artists") or []) if a.get("name"))
    album = (track.get("album") or {}).get("name") if track.get("album") else None
    parts = [title]
    if artists:
        parts.append(f"by {artists}")
    if album:
        parts.append(f"({album})")
    return " ".join(parts)


def build_memory_content(tracks: list[dict]) -> str:
    today = dt.date.today().isoformat()
    header = (
        f"My liked songs on YouTube Music — {len(tracks)} tracks, "
        f"captured {today}. This is a snapshot of the music I love:\n"
    )
    lines = [f"{i}. {format_track(t)}" for i, t in enumerate(tracks, start=1)]
    return header + "\n".join(lines)


# --------------------------------------------------------------------------- #
# Sentience
# --------------------------------------------------------------------------- #
def get_sentience_key() -> str:
    step("Connect your Sentience account")
    key = os.environ.get("SENTIENCE_API_KEY", "").strip()
    if key:
        print(f"  Using SENTIENCE_API_KEY from environment ({key[:9]}...).")
        return key

    print(
        "  Grab an API key from your Sentience settings (it starts with 'sent_')."
    )
    key = prompt("Paste your Sentience API key:")
    if not key.startswith("sent_"):
        cont = prompt("  That doesn't look like a 'sent_' key. Continue anyway? [y/N]")
        if cont.lower() not in {"y", "yes"}:
            sys.exit("Aborting.")
    return key


def write_memory(api_key: str, content: str) -> dict:
    step("Writing your music memory to Sentience...")
    resp = requests.post(
        SENTIENCE_MEMORIES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"content": content},
        timeout=30,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"status_code": resp.status_code, "text": resp.text}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    banner("Sentience Music Memory")
    print(
        "This one-off script reads your YouTube Music liked songs and saves\n"
        "them as a memory in Sentience. Let's get the two connections set up."
    )

    api_key = get_sentience_key()
    yt = ensure_youtube_auth()

    tracks = fetch_liked_songs(yt)
    if not tracks:
        sys.exit("No liked songs found, nothing to save.")

    content = build_memory_content(tracks)
    print("\n  Preview of the memory to be written:\n")
    preview = content if len(content) < 800 else content[:800] + "\n  ...(truncated preview)"
    print("\n".join("  " + line for line in preview.splitlines()))

    confirm = prompt(f"\nWrite this memory ({len(tracks)} songs) to Sentience? [Y/n]")
    if confirm.lower() in {"n", "no"}:
        sys.exit("Aborting without writing.")

    result = write_memory(api_key, content)
    banner("Done!")
    print(f"Memory written. Sentience responded:\n{json.dumps(result, indent=2)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")
    except requests.HTTPError as e:
        sys.exit(f"\nSentience API error: {e}\nResponse: {e.response.text}")
