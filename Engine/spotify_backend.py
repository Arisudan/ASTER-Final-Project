from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth

from Engine import db

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"
SPOTIFY_CACHE_PATH = BASE_DIR / ".spotify_cache"
SPOTIFY_SCOPE = " ".join(
    [
        "streaming",
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-currently-playing",
        "user-read-private",
        "app-remote-control",
    ]
)

_lock = threading.Lock()
_client: Optional[spotipy.Spotify] = None
_auth_manager: Optional[SpotifyOAuth] = None


def _load_environment_file() -> None:
    if not ENV_FILE.exists():
        return

    try:
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        return


_load_environment_file()


@dataclass
class SpotifyTrack:
    title: str
    artist: str
    album: str
    image: str
    duration_ms: int
    progress_ms: int
    is_playing: bool
    device_name: str = ""
    shuffle_state: bool = False
    repeat_state: str = "off"
    uri: str = ""


def _configured() -> bool:
    return bool(os.getenv("SPOTIPY_CLIENT_ID") and os.getenv("SPOTIPY_CLIENT_SECRET"))


def _build_auth_manager() -> SpotifyOAuth:
    global _auth_manager
    if _auth_manager is not None:
        return _auth_manager

    _auth_manager = SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope=SPOTIFY_SCOPE,
        cache_handler=CacheFileHandler(cache_path=str(SPOTIFY_CACHE_PATH)),
        open_browser=True,
    )
    return _auth_manager


def _get_client() -> Optional[spotipy.Spotify]:
    global _client
    if not _configured():
        return None

    with _lock:
        if _client is None:
            _client = spotipy.Spotify(auth_manager=_build_auth_manager(), requests_timeout=15, retries=2)
        return _client


def _refresh_access_token() -> Optional[str]:
    auth_manager = _build_auth_manager()
    try:
        token_info = auth_manager.get_access_token(as_dict=True, check_cache=True)
        if isinstance(token_info, dict):
            token = token_info.get("access_token")
            if token:
                return str(token)
    except Exception:
        pass
    return None


def get_access_token() -> str:
    token = _refresh_access_token()
    return token or ""


def connect_spotify() -> dict[str, Any]:
    if not _configured():
        return {
            "ok": False,
            "message": "Spotify credentials are missing. Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET.",
        }

    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify client is unavailable."}

    try:
        user = client.current_user()
        db.log_event("info", f"Spotify connected for {user.get('display_name') or user.get('id') or 'unknown user'}", source="spotify")
        return {
            "ok": True,
            "message": f"Connected to Spotify as {user.get('display_name') or user.get('id') or 'user'}.",
            "token": get_access_token(),
        }
    except Exception as exc:
        db.log_event("warning", f"Spotify connection failed: {exc}", source="spotify")
        return {"ok": False, "message": f"Spotify connection failed: {exc}"}


def _available_devices(client: spotipy.Spotify) -> list[dict[str, Any]]:
    try:
        payload = client.devices()
        return list(payload.get("devices", []) or [])
    except Exception:
        return []


def _select_device(client: spotipy.Spotify) -> Optional[dict[str, Any]]:
    devices = _available_devices(client)
    if not devices:
        return None

    active = next((device for device in devices if device.get("is_active")), None)
    if active:
        return active

    preferred = next((device for device in devices if device.get("type") == "Computer"), None)
    return preferred or devices[0]


def _ensure_playback_device(client: spotipy.Spotify) -> tuple[Optional[dict[str, Any]], str]:
    device = _select_device(client)
    if device is None:
        return None, "No active Spotify device was found. Open Spotify on a device or use the Web Playback SDK first."
    return device, ""


def _search_track(client: spotipy.Spotify, query: str) -> Optional[dict[str, Any]]:
    try:
        payload = client.search(q=query, type="track", limit=1)
        tracks = payload.get("tracks", {}).get("items", [])
        if tracks:
            return tracks[0]
    except Exception:
        return None
    return None


def _normalize_track_payload(payload: dict[str, Any] | None) -> SpotifyTrack:
    if not payload:
        return SpotifyTrack(title="Nothing playing", artist="Spotify", album="", image="", duration_ms=0, progress_ms=0, is_playing=False)

    item = payload.get("item") or {}
    artists = item.get("artists", []) or []
    album = item.get("album", {}) or {}
    images = album.get("images", []) or []
    image = images[0]["url"] if images and isinstance(images[0], dict) and images[0].get("url") else ""

    return SpotifyTrack(
        title=item.get("name") or "Unknown Track",
        artist=", ".join(artist.get("name", "") for artist in artists if isinstance(artist, dict) and artist.get("name")) or "Unknown Artist",
        album=album.get("name") or "",
        image=image,
        duration_ms=int(item.get("duration_ms") or 0),
        progress_ms=int(payload.get("progress_ms") or 0),
        is_playing=bool(payload.get("is_playing")),
        device_name=payload.get("device", {}).get("name") or "",
        shuffle_state=bool(payload.get("shuffle_state")),
        repeat_state=str(payload.get("repeat_state") or "off"),
        uri=item.get("uri") or "",
    )


def get_current_track() -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {
            "connected": False,
            "message": "Spotify is not configured.",
            "track": asdict(
                SpotifyTrack(title="Spotify not configured", artist="Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET", album="", image="", duration_ms=0, progress_ms=0, is_playing=False)
            ),
        }

    try:
        payload = client.current_user_playing_track()
        track = _normalize_track_payload(payload)
        return {
            "connected": True,
            "message": "Spotify state loaded.",
            "track": asdict(track),
        }
    except Exception as exc:
        return {
            "connected": False,
            "message": f"Unable to fetch Spotify state: {exc}",
            "track": asdict(SpotifyTrack(title="Spotify unavailable", artist="Check Spotify login", album="", image="", duration_ms=0, progress_ms=0, is_playing=False)),
        }


def get_player_state() -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"connected": False, "message": "Spotify is not configured.", "track": asdict(SpotifyTrack(title="Spotify not configured", artist="", album="", image="", duration_ms=0, progress_ms=0, is_playing=False)), "devices": []}

    try:
        devices = _available_devices(client)
        payload = client.current_playback()
        track = _normalize_track_payload(payload)
        return {
            "connected": True,
            "message": "Spotify state loaded.",
            "track": asdict(track),
            "devices": devices,
        }
    except Exception as exc:
        return {"connected": False, "message": f"Unable to fetch Spotify state: {exc}", "track": asdict(SpotifyTrack(title="Spotify unavailable", artist="Check Spotify login", album="", image="", duration_ms=0, progress_ms=0, is_playing=False)), "devices": []}


def transfer_playback_to_device(device_id: str) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    target_device = str(device_id or "").strip()
    if not target_device:
        return {"ok": False, "message": "No Spotify device id was provided."}

    try:
        client.transfer_playback(device_id=target_device, force_play=False)
        return {"ok": True, "message": "Spotify playback transferred."}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to transfer playback: {exc}"}


def play_music(query: str | None = None) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    try:
        device, device_message = _ensure_playback_device(client)
        if device is None:
            return {"ok": False, "message": device_message}

        device_id = device.get("id")
        if query and str(query).strip():
            track = _search_track(client, str(query).strip())
            if track is None:
                return {"ok": False, "message": f'No Spotify track was found for "{query}".'}
            client.start_playback(device_id=device_id, uris=[track["uri"]])
            message = f'Playing {track.get("name", "track")} by {track.get("artists", [{}])[0].get("name", "Unknown Artist")}. '
        else:
            client.start_playback(device_id=device_id)
            message = "Resuming Spotify playback."

        db.log_event("info", message, source="spotify")
        return {"ok": True, "message": message, "state": get_player_state()}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to play music: {exc}"}


def pause_music() -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    try:
        client.pause_playback()
        db.log_event("info", "Spotify paused.", source="spotify")
        return {"ok": True, "message": "Paused Spotify playback.", "state": get_player_state()}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to pause music: {exc}"}


def next_track() -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    try:
        client.next_track()
        db.log_event("info", "Spotify skipped to next track.", source="spotify")
        return {"ok": True, "message": "Skipped to the next track.", "state": get_player_state()}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to skip track: {exc}"}


def previous_track() -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    try:
        client.previous_track()
        db.log_event("info", "Spotify went to previous track.", source="spotify")
        return {"ok": True, "message": "Went to the previous track.", "state": get_player_state()}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to go to previous track: {exc}"}


def set_volume(level: int | str) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    try:
        volume = max(0, min(100, int(float(level))))
        device, device_message = _ensure_playback_device(client)
        if device is None:
            return {"ok": False, "message": device_message}
        client.volume(volume, device_id=device.get("id"))
        db.log_event("info", f"Spotify volume set to {volume}%.", source="spotify")
        return {"ok": True, "message": f"Volume set to {volume}.", "state": get_player_state()}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to set volume: {exc}"}


def toggle_shuffle(enabled: bool) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    try:
        client.shuffle(bool(enabled))
        return {"ok": True, "message": f"Shuffle {'enabled' if enabled else 'disabled' }.", "state": get_player_state()}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to change shuffle: {exc}"}


def toggle_repeat(mode: str) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    repeat_mode = str(mode or "off").strip().lower()
    if repeat_mode not in {"off", "context", "track"}:
        repeat_mode = "off"

    try:
        client.repeat(repeat_mode)
        return {"ok": True, "message": f"Repeat set to {repeat_mode}.", "state": get_player_state()}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to change repeat mode: {exc}"}


def search_and_play(query: str) -> dict[str, Any]:
    return play_music(query)
