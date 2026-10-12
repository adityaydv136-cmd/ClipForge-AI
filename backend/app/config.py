import os
import shutil
import glob
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
CACHE_DIR = DATA_DIR / "cache"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "clipforge.db"
COOKIES_PATH = DATA_DIR / "cookies.txt"

# Discover FFmpeg and FFprobe binaries
def find_ffmpeg_bins():
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    if not ffmpeg_path or not ffprobe_path:
        # Check WinGet Gyan package directory
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            gyan_matches = glob.glob(
                os.path.join(local_app_data, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "**", "ffmpeg.exe"),
                recursive=True
            )
            if gyan_matches:
                bin_dir = os.path.dirname(gyan_matches[0])
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                ffmpeg_path = shutil.which("ffmpeg")
                ffprobe_path = shutil.which("ffprobe")

    # If still not found, check imageio_ffmpeg
    if not ffmpeg_path:
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass

    return ffmpeg_path, ffprobe_path

FFMPEG_PATH, FFPROBE_PATH = find_ffmpeg_bins()

# Default settings
DEFAULT_WHISPER_MODEL = "base"  # "tiny", "base", "small"
DEFAULT_DURATION_OPTION = "20"  # "20", "30", "both"
DEFAULT_NUM_CLIPS = "3"         # "3", "5", "10", "auto"
ENABLE_SUBTITLES = True
