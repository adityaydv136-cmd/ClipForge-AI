import subprocess
import json
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional
import cv2
from .config import FFMPEG_PATH, FFPROBE_PATH

def get_ffmpeg_bin() -> str:
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        return FFMPEG_PATH
    return "ffmpeg"

def get_ffprobe_bin() -> str:
    if FFPROBE_PATH and os.path.exists(FFPROBE_PATH):
        return FFPROBE_PATH
    return "ffprobe"

def probe_video(video_path: Path) -> Dict[str, Any]:
    """Inspect video duration, resolution, fps and streams."""
    ffprobe = get_ffprobe_bin()
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
        data = json.loads(result.stdout)
        
        duration = float(data.get("format", {}).get("duration", 0))
        video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
        
        width = int(video_stream.get("width", 0)) if video_stream else 0
        height = int(video_stream.get("height", 0)) if video_stream else 0
        
        # Calculate fps
        fps = 30.0
        if video_stream and "r_frame_rate" in video_stream:
            num, denom = video_stream["r_frame_rate"].split("/")
            if float(denom) > 0:
                fps = float(num) / float(denom)

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "has_audio": audio_stream is not None,
            "has_video": video_stream is not None
        }
    except Exception as e:
        # Fallback to OpenCV if ffprobe fails
        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            duration = (frame_count / fps) if fps > 0 else 0
            cap.release()
            return {
                "duration": duration,
                "width": width,
                "height": height,
                "fps": fps,
                "has_audio": True,
                "has_video": True
            }
        return {
            "duration": 0,
            "width": 0,
            "height": 0,
            "fps": 30.0,
            "has_audio": False,
            "has_video": False,
            "error": str(e)
        }

def extract_audio(video_path: Path, output_wav_path: Path) -> bool:
    """Extract audio track as 16kHz mono 16-bit PCM WAV for faster-whisper."""
    ffmpeg = get_ffmpeg_bin()
    cmd = [
        ffmpeg,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_wav_path)
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        return output_wav_path.exists() and output_wav_path.stat().st_size > 0
    except subprocess.CalledProcessError as e:
        print(f"Error extracting audio: {e.stderr.decode('utf-8', errors='ignore')}")
        return False

def generate_thumbnail(video_path: Path, timestamp: float, output_thumb_path: Path) -> bool:
    """Capture a clean frame thumbnail at timestamp."""
    ffmpeg = get_ffmpeg_bin()
    cmd = [
        ffmpeg,
        "-y",
        "-ss", str(max(0, timestamp)),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(output_thumb_path)
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=15)
        return output_thumb_path.exists()
    except Exception:
        return False

def render_vertical_clip(
    source_video: Path,
    start_time: float,
    duration: float,
    output_path: Path,
    subtitle_path: Optional[Path] = None,
    crop_mode: str = "fill",
    aspect_ratio: str = "9:16",
    audio_boost: bool = True
) -> bool:
    """
    Render video short using FFmpeg.
    - Aspect ratios: 9:16 (Vertical Shorts/TikTok), 1:1 (Square), 16:9 (Landscape)
    - Synchronized audio/video with optional audio loudness normalization
    - Optional burned-in subtitles with safe margins
    """
    import tempfile
    import shutil
    import time

    ffmpeg = get_ffmpeg_bin()
    
    # 1. Video aspect ratio filter graph
    if aspect_ratio == "1:1":
        video_filter = "crop=w='min(iw,ih)':h='min(iw,ih)':x='(iw-ow)/2':y='(ih-oh)/2',scale=1080:1080:flags=lanczos"
    elif aspect_ratio == "16:9":
        video_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    else:  # default 9:16 vertical
        video_filter = "crop=w='min(iw,ih*9/16)':h='min(ih,iw*16/9)':x='(iw-ow)/2':y='(ih-oh)/2',scale=1080:1920:flags=lanczos"
    
    # If subtitles requested, append subtitles filter
    if subtitle_path and subtitle_path.exists():
        sub_str = str(subtitle_path.resolve()).replace('\\', '/')
        sub_str = sub_str.replace(':', '\\:')
        video_filter += f",subtitles=filename='{sub_str}'"

    # 2. Audio filters: loudnorm for viral vocal punch
    audio_args = ["-c:a", "aac", "-b:a", "160k", "-ar", "44100"]
    if audio_boost:
        audio_args = ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11,volume=1.2"] + audio_args

    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Render to a temp file first to prevent Windows OneDrive locks
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_file:
        tmp_output = Path(tmp_file.name)

    cmd = [
        ffmpeg,
        "-y",
        "-ss", f"{max(0, start_time):.3f}",
        "-t", f"{max(1.0, duration):.3f}",
        "-i", str(source_video),
        "-vf", video_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
    ] + audio_args + [
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        str(tmp_output)
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=240)
        
        # Copy to destination with retry logic for Windows OneDrive file locks
        if tmp_output.exists() and tmp_output.stat().st_size > 0:
            for attempt in range(6):
                try:
                    if output_path.exists():
                        try:
                            output_path.unlink()
                        except (PermissionError, OSError):
                            time.sleep(0.3)
                    shutil.copy2(tmp_output, output_path)
                    break
                except (PermissionError, OSError):
                    time.sleep(0.4 * (attempt + 1))
            
            try:
                tmp_output.unlink(missing_ok=True)
            except Exception:
                pass
            return output_path.exists() and output_path.stat().st_size > 0
        return False
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg render error: {e.stderr}")
        try:
            tmp_output.unlink(missing_ok=True)
        except Exception:
            pass
        return False
