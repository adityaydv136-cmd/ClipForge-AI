import re
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import yt_dlp
from .ffmpeg_utils import get_ffmpeg_bin
from .config import COOKIES_PATH, BASE_DIR

YOUTUBE_URL_PATTERNS = [
    r'^(https?://)?(www\.)?(youtube\.com/watch\?v=[\w-]{11})',
    r'^(https?://)?(www\.)?(youtube\.com/shorts/[\w-]{11})',
    r'^(https?://)?(www\.)?(youtu\.be/[\w-]{11})',
    r'^(https?://)?(www\.)?(m\.youtube\.com/watch\?v=[\w-]{11})',
]

def is_valid_youtube_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return any(re.match(pattern, url) for pattern in YOUTUBE_URL_PATTERNS)

def extract_video_id(url: str) -> Optional[str]:
    """Extract standard 11-character YouTube video ID."""
    if not url:
        return None
    patterns = [
        r'(?:v=|\/shorts\/|\/embed\/|youtu\.be\/|\/v\/)([\w-]{11})',
        r'([\w-]{11})'
    ]
    for pattern in patterns:
        m = re.search(pattern, url.strip())
        if m:
            return m.group(1)
    return None

def get_active_cookies_file() -> Optional[Path]:
    """Find valid cookies.txt if provided by user."""
    candidates = [
        COOKIES_PATH,
        BASE_DIR / "cookies.txt",
        Path.cwd() / "cookies.txt",
    ]
    for p in candidates:
        if p.exists() and p.is_file() and p.stat().st_size > 10:
            return p
    return None

def get_video_metadata(url: str) -> Dict[str, Any]:
    """
    Extract title, author, and thumbnail without download.
    Uses official YouTube oEmbed API as primary non-blocking source to completely bypass
    bot verification challenges and access restriction false-positives.
    """
    if not is_valid_youtube_url(url):
        return {
            "is_valid": False,
            "error": "Please enter a valid YouTube URL (e.g., https://www.youtube.com/watch?v=... or https://youtu.be/...)"
        }

    video_id = extract_video_id(url)
    default_thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None

    # Step 1: Use YouTube official oEmbed API (instant, never triggers bot detection)
    try:
        oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json"
        req = urllib.request.Request(
            oembed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return {
                    "is_valid": True,
                    "title": data.get("title") or f"YouTube Video ({video_id})",
                    "duration": 0.0,  # Exact duration is probed upon stream download
                    "thumbnail_url": data.get("thumbnail_url") or default_thumb,
                    "author": data.get("author_name") or "YouTube Creator",
                    "error": None
                }
    except Exception:
        # Fallback to secondary extractors if oEmbed has network hiccup
        pass

    # Step 2: Try yt-dlp flat extraction with active cookies if available
    cookie_file = get_active_cookies_file()
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'js_runtimes': {'node': {}},
    }
    if cookie_file:
        ydl_opts['cookiefile'] = str(cookie_file)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                title = info.get('title') or (f"YouTube Video ({video_id})" if video_id else "YouTube Video")
                duration = float(info.get('duration') or 0.0)
                thumbnail = info.get('thumbnail') or default_thumb
                uploader = info.get('uploader') or info.get('channel') or "YouTube Creator"
                return {
                    "is_valid": True,
                    "title": title,
                    "duration": duration,
                    "thumbnail_url": thumbnail,
                    "author": uploader,
                    "error": None
                }
    except Exception:
        pass

    # Step 3: Reliable fallback for valid URL format - never block the user upfront
    if video_id:
        return {
            "is_valid": True,
            "title": f"YouTube Video ({video_id})",
            "duration": 0.0,
            "thumbnail_url": default_thumb,
            "author": "YouTube Creator",
            "error": None
        }

    return {
        "is_valid": False,
        "error": "Could not verify YouTube video. Please check the URL or upload your file directly."
    }

class SourceRestrictedError(Exception):
    """Raised when media stream access requires bot verification or cookies."""
    pass

def download_video(url: str, output_path: Path, progress_callback: Optional[Callable[[float, str], None]] = None) -> Dict[str, Any]:
    """
    Download video stream using yt-dlp to output_path.
    Uses a temporary directory outside OneDrive to avoid Windows WinError 32 file lock conflicts.
    Supports cookie files and Node.js JS runtime.
    Progress is reported via progress_callback(percentage, status_text).
    """
    import tempfile
    import shutil
    import time

    if not is_valid_youtube_url(url):
        raise ValueError("Invalid YouTube URL.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="clipforge_dl_", ignore_cleanup_errors=True) as tmpdir:
        tmp_dir = Path(tmpdir)
        temp_template = str(tmp_dir / "media.%(ext)s")

        def ytdl_hook(d):
            if d['status'] == 'downloading' and progress_callback:
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                if total > 0:
                    pct = min(100.0, (downloaded / total) * 100.0)
                    progress_callback(pct, f"Downloading video stream ({pct:.1f}%)...")
            elif d['status'] == 'finished' and progress_callback:
                progress_callback(100.0, "Video download finished. Processing streams...")

        cookie_file = get_active_cookies_file()

        ydl_opts = {
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/bestvideo[height<=1080]+bestaudio/best',
            'outtmpl': temp_template,
            'merge_output_format': 'mp4',
            'ffmpeg_location': get_ffmpeg_bin(),
            'quiet': True,
            'no_warnings': True,
            'windowsfilenames': True,
            'continuedl': True,
            'socket_timeout': 45,
            'retries': 15,
            'fragment_retries': 15,
            'file_access_retries': 5,
            'http_chunk_size': 10485760,
            'overwrites': False,
            'progress_hooks': [ytdl_hook],
            'js_runtimes': {'node': {}},
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'mweb', 'web', 'android']
                }
            }
        }

        if cookie_file:
            ydl_opts['cookiefile'] = str(cookie_file)

        max_download_attempts = 3
        last_exception = None

        for attempt_idx in range(max_download_attempts):
            try:
                if attempt_idx > 0 and progress_callback:
                    progress_callback(10.0, f"Network hiccup encountered. Resuming download (attempt {attempt_idx + 1}/{max_download_attempts})...")
                    time.sleep(2 * attempt_idx)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    title = info.get('title', 'YouTube Video')
                    duration = float(info.get('duration') or 0.0)
                    thumbnail = info.get('thumbnail')
                    
                    # Find output in temp directory
                    matches = [f for f in tmp_dir.glob("media.*") if not f.name.endswith(".part")]
                    if not matches:
                        matches = [f for f in tmp_dir.glob("*.*") if not f.name.endswith(".part") and f.suffix in [".mp4", ".mkv", ".webm"]]
                    if not matches:
                        raise RuntimeError("Downloaded file not found in temporary workspace.")
                    
                    downloaded_file = matches[0]

                # Copy to output_path with retry logic in case of Windows file locks
                copy_succeeded = False
                last_err = None
                for attempt in range(10):
                    try:
                        if output_path.exists():
                            try:
                                output_path.unlink()
                            except (PermissionError, OSError):
                                time.sleep(0.5)
                                continue
                        shutil.copy2(downloaded_file, output_path)
                        copy_succeeded = True
                        break
                    except (PermissionError, OSError) as pe:
                        last_err = pe
                        time.sleep(0.5 * (attempt + 1))

                if not copy_succeeded:
                    try:
                        shutil.copyfile(downloaded_file, output_path)
                    except Exception:
                        if last_err:
                            raise last_err
                        raise

                return {
                    "title": title,
                    "duration": duration,
                    "thumbnail_url": thumbnail,
                    "path": output_path
                }
            except yt_dlp.utils.DownloadError as e:
                err_str = str(e)
                last_exception = e
                if any(term in err_str.lower() for term in ["sign in", "bot", "login_required", "confirm you're not a bot"]):
                    raise SourceRestrictedError(
                        "YouTube Bot Verification: YouTube requires session verification for this video stream. "
                        "You can import your YouTube cookies.txt in Settings, or upload your video file directly to generate shorts instantly."
                    )
                if any(term in err_str.lower() for term in ["drm", "private", "members-only", "copyright"]):
                    raise SourceRestrictedError(
                        "Access Restricted: This YouTube video is private or DRM-protected. Please upload a video file you own directly."
                    )

                is_retryable = any(term in err_str.lower() for term in ["timed out", "read operation", "connection reset", "connection aborted", "remotely closed"])
                if is_retryable and attempt_idx < max_download_attempts - 1:
                    continue
                break
            except Exception as e:
                last_exception = e
                if attempt_idx < max_download_attempts - 1:
                    continue
                break

        if last_exception:
            err_str = str(last_exception)
            if any(term in err_str.lower() for term in ["timed out", "read operation"]):
                raise RuntimeError(
                    "Download timed out: The connection to YouTube stalled or timed out while downloading the media stream. "
                    "Please try again, or upload your video file directly for instant offline generation."
                )
            raise RuntimeError(f"Download failed: {err_str}")
        raise RuntimeError("Download failed due to an unknown network error.")
