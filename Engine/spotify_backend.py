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
        "user-read-email",
        "user-library-read",
        "user-library-modify",
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-public",
        "playlist-modify-private",
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


def play_uri(uri: str) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    target_uri = str(uri or "").strip()
    if not target_uri:
        return {"ok": False, "message": "Spotify URI is empty."}

    try:
        device, device_message = _ensure_playback_device(client)
        if device is None:
            return {"ok": False, "message": device_message}

        device_id = device.get("id")
        if target_uri.startswith("spotify:track:"):
            client.start_playback(device_id=device_id, uris=[target_uri])
            message = "Playing selected track."
        elif target_uri.startswith("spotify:playlist:") or target_uri.startswith("spotify:album:"):
            client.start_playback(device_id=device_id, context_uri=target_uri)
            message = "Playing selected collection."
        else:
            return {"ok": False, "message": "Unsupported Spotify URI format."}

        db.log_event("info", f"Spotify play via URI: {target_uri}", source="spotify")
        return {"ok": True, "message": message, "state": get_player_state()}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to play Spotify URI: {exc}"}


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
        
        try:
            client.volume(volume, device_id=device.get("id"))
            db.log_event("info", f"Spotify volume set to {volume}%.", source="spotify")
            return {"ok": True, "message": f"Volume set to {volume}.", "state": get_player_state()}
        except Exception as vol_exc:
            # Volume control may not be supported on all devices (web player)
            db.log_event("warning", f"Volume control not available: {vol_exc}", source="spotify")
            return {"ok": False, "message": "Volume control not supported on this device. Try using a native Spotify client.", "state": get_player_state()}
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


def _get_playlist_tracks(client: spotipy.Spotify, playlist_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch tracks from a specific playlist."""
    try:
        results = client.playlist_tracks(playlist_id, limit=limit)
        tracks = []
        for item in results.get("items", []):
            track = item.get("track", {})
            if track and track.get("uri"):
                tracks.append({
                    "name": track.get("name", "Unknown"),
                    "artist": ", ".join(a.get("name", "Unknown") for a in track.get("artists", [])),
                    "uri": track.get("uri", ""),
                    "id": track.get("id", ""),
                })
        return tracks
    except Exception:
        return []


def _match_emotion_to_playlists(playlists: list[dict[str, Any]], emotion_keywords: list[str]) -> list[dict[str, Any]]:
    """Filter playlists by matching emotion keywords in name and description."""
    matched = []
    emotion_keywords_lower = [kw.lower() for kw in emotion_keywords]
    
    for playlist in playlists:
        name = str(playlist.get("name", "")).lower()
        description = str(playlist.get("description", "")).lower()
        combined_text = f"{name} {description}"
        
        if any(keyword in combined_text for keyword in emotion_keywords_lower):
            matched.append(playlist)
    
    return matched


def play_emotion_based_playlist(emotion_label: str, emotion_keywords: list[str]) -> dict[str, Any]:
    """
    Play a random track from user's playlists matching the detected emotion.
    Falls back to generic search if no matching playlists found.
    """
    import random
    
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    try:
        device, device_message = _ensure_playback_device(client)
        if device is None:
            return {"ok": False, "message": device_message}

        device_id = device.get("id")
        
        # Fetch user playlists
        playlists_result = get_user_playlists(limit=50)
        playlists = playlists_result.get("playlists", [])
        
        if not playlists:
            return {"ok": False, "message": f"No playlists found. Cannot play {emotion_label} music."}
        
        # Match playlists to emotion
        matched_playlists = _match_emotion_to_playlists(playlists, emotion_keywords)
        
        if not matched_playlists:
            # Fallback: if no keyword-matching playlists, suggest using all playlists or search
            return {
                "ok": False,
                "message": f"No {emotion_label} playlists found. Try creating a playlist with '{emotion_keywords[0]}' in the name.",
                "fallback": True,
            }
        
        # Select a random playlist from matched
        selected_playlist = random.choice(matched_playlists)
        playlist_id = selected_playlist.get("id")
        playlist_name = selected_playlist.get("name", "Unknown Playlist")
        
        # Get tracks from selected playlist
        tracks = _get_playlist_tracks(client, playlist_id, limit=30)
        
        if not tracks:
            return {
                "ok": False,
                "message": f"Playlist '{playlist_name}' has no playable tracks.",
            }
        
        # Select a random track
        selected_track = random.choice(tracks)
        track_uri = selected_track.get("uri")
        track_name = selected_track.get("name", "Unknown Track")
        artist_name = selected_track.get("artist", "Unknown Artist")
        
        # Play the track
        client.start_playback(device_id=device_id, uris=[track_uri])
        
        message = f"Playing '{track_name}' by {artist_name} from '{playlist_name}' playlist."
        db.log_event("info", message, source="spotify")
        
        return {
            "ok": True,
            "message": message,
            "playlist_name": playlist_name,
            "track_name": track_name,
            "artist_name": artist_name,
            "state": get_player_state(),
        }
    except Exception as exc:
        return {"ok": False, "message": f"Unable to play emotion-based music: {exc}"}


def get_user_profile() -> dict[str, Any]:
    """Fetch and return current Spotify user profile information."""
    client = _get_client()
    if client is None:
        return {"connected": False, "message": "Spotify is not configured.", "user": None}

    try:
        user = client.current_user()
        return {
            "connected": True,
            "message": "User profile loaded.",
            "user": {
                "display_name": user.get("display_name") or user.get("id") or "Unknown User",
                "email": user.get("email", ""),
                "followers": user.get("followers", {}).get("total", 0),
                "premium": user.get("product") == "premium" if user.get("product") else False,
                "id": user.get("id", ""),
                "external_urls": user.get("external_urls", {}),
                "images": user.get("images", []),
            },
        }
    except Exception as exc:
        return {"connected": False, "message": f"Unable to fetch user profile: {exc}", "user": None}


def get_user_playlists(limit: int = 20) -> dict[str, Any]:
    """Fetch and return current user's playlists."""
    client = _get_client()
    if client is None:
        return {"connected": False, "message": "Spotify is not configured.", "playlists": []}

    try:
        result = client.current_user_playlists(limit=limit)
        playlists = []
        for item in result.get("items", []):
            playlists.append({
                "id": item.get("id", ""),
                "name": item.get("name", "Untitled"),
                "description": item.get("description", ""),
                "tracks_total": item.get("tracks", {}).get("total", 0),
                "image": item.get("images", [{}])[0].get("url", "") if item.get("images") else "",
                "uri": item.get("uri", ""),
                "external_urls": item.get("external_urls", {}),
            })
        return {"connected": True, "message": f"Loaded {len(playlists)} playlists.", "playlists": playlists}
    except Exception as exc:
        return {"connected": False, "message": f"Unable to fetch playlists: {exc}", "playlists": []}


def get_user_saved_tracks(limit: int = 20) -> dict[str, Any]:
    """Fetch and return current user's saved (liked) tracks."""
    client = _get_client()
    if client is None:
        return {"connected": False, "message": "Spotify is not configured.", "tracks": []}

    try:
        result = client.current_user_saved_tracks(limit=limit)
        tracks = []
        for item in result.get("items", []):
            track = item.get("track", {})
            artists = track.get("artists", [])
            album = track.get("album", {})
            images = album.get("images", []) if album else []
            tracks.append({
                "id": track.get("id", ""),
                "name": track.get("name", "Untitled"),
                "artists": ", ".join(artist.get("name", "Unknown") for artist in artists),
                "album": album.get("name", "Unknown Album") if album else "Unknown Album",
                "duration_ms": track.get("duration_ms", 0),
                "image": images[0].get("url", "") if images and isinstance(images[0], dict) else "",
                "uri": track.get("uri", ""),
                "external_urls": track.get("external_urls", {}),
            })
        return {"connected": True, "message": f"Loaded {len(tracks)} saved tracks.", "tracks": tracks}
    except Exception as exc:
        return {"connected": False, "message": f"Unable to fetch saved tracks: {exc}", "tracks": []}


def get_recently_played(limit: int = 20) -> dict[str, Any]:
    """Fetch and return recently played tracks."""
    client = _get_client()
    if client is None:
        return {"connected": False, "message": "Spotify is not configured.", "tracks": []}

    try:
        result = client.current_user_recently_played(limit=limit)
        tracks = []
        for item in result.get("items", []):
            track = item.get("track", {})
            artists = track.get("artists", [])
            album = track.get("album", {})
            images = album.get("images", []) if album else []
            tracks.append({
                "id": track.get("id", ""),
                "name": track.get("name", "Untitled"),
                "artists": ", ".join(artist.get("name", "Unknown") for artist in artists),
                "album": album.get("name", "Unknown Album") if album else "Unknown Album",
                "duration_ms": track.get("duration_ms", 0),
                "image": images[0].get("url", "") if images and isinstance(images[0], dict) else "",
                "played_at": item.get("played_at", ""),
                "uri": track.get("uri", ""),
            })
        return {"connected": True, "message": f"Loaded {len(tracks)} recently played tracks.", "tracks": tracks}
    except Exception as exc:
        return {"connected": False, "message": f"Unable to fetch recently played tracks: {exc}", "tracks": []}


def search_spotify(query: str, limit: int = 8) -> dict[str, Any]:
    """Search Spotify for tracks matching the query."""
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured.", "tracks": []}

    try:
        result = client.search(q=query, type="track", limit=limit)
        tracks = []
        for item in result.get("tracks", {}).get("items", []):
            artists = item.get("artists", [])
            album = item.get("album", {})
            images = album.get("images", []) if album else []
            tracks.append({
                "id": item.get("id", ""),
                "name": item.get("name", "Untitled"),
                "artist": ", ".join(artist.get("name", "Unknown") for artist in artists),
                "artists": ", ".join(artist.get("name", "Unknown") for artist in artists),
                "album": album.get("name", "Unknown Album") if album else "Unknown Album",
                "duration_ms": item.get("duration_ms", 0),
                "image": images[0].get("url", "") if images and isinstance(images[0], dict) else "https://picsum.photos/40/40?random=" + str(hash(query)),
                "uri": item.get("uri", ""),
            })
        return {"ok": True, "message": f"Found {len(tracks)} tracks.", "tracks": tracks}
    except Exception as exc:
        return {"ok": False, "message": f"Search failed: {exc}", "tracks": []}


def get_playlist_tracks(playlist_uri: str, limit: int = 50) -> dict[str, Any]:
    """
    Fetch all tracks from a specific playlist given its URI.
    """
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured.", "tracks": []}

    try:
        # Extract playlist ID from URI (format: spotify:playlist:ID)
        playlist_id = playlist_uri.split(":")[-1] if ":" in playlist_uri else playlist_uri
        
        result = client.playlist_tracks(playlist_id, limit=limit)
        tracks = []
        
        for item in result.get("items", []):
            track = item.get("track", {})
            if not track:
                continue
                
            artists = track.get("artists", [])
            album = track.get("album", {})
            images = album.get("images", []) if album else []
            
            tracks.append({
                "id": track.get("id", ""),
                "name": track.get("name", "Untitled"),
                "artist": ", ".join(artist.get("name", "Unknown") for artist in artists),
                "artists": ", ".join(artist.get("name", "Unknown") for artist in artists),
                "album": album.get("name", "Unknown Album") if album else "Unknown Album",
                "duration_ms": track.get("duration_ms", 0),
                "image": images[0].get("url", "") if images and isinstance(images[0], dict) else "https://picsum.photos/56/56?random=" + str(hash(track.get("id", ""))),
                "uri": track.get("uri", ""),
            })
        
        return {"ok": True, "message": f"Loaded {len(tracks)} tracks from playlist.", "tracks": tracks}
    except Exception as exc:
        return {"ok": False, "message": f"Unable to fetch playlist tracks: {exc}", "tracks": []}


def seek_track(position_ms: int) -> dict[str, Any]:
    """
    Seek to a specific position in the currently playing track.
    """
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Spotify is not configured."}

    try:
        device, device_message = _ensure_playback_device(client)
        if device is None:
            return {"ok": False, "message": device_message}

        position_ms = max(0, int(position_ms))
        client.seek_track(position_ms, device_id=device.get("id"))
        
        return {
            "ok": True,
            "message": f"Seeked to {position_ms}ms.",
            "state": get_player_state(),
        }
    except Exception as exc:
        return {"ok": False, "message": f"Unable to seek track: {exc}"}

