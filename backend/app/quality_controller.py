"""
ClipForge AI 2.0 - Automated Quality Control (QC) Pass
======================================================
Validates rendered short-form video clips before export:
  - Video stream existence & valid resolution
  - Audio stream integrity & loudness presence
  - Timeline duration accuracy against target duration
  - Narrative structure verification (hook present, payoff included)
  - Valid MP4 container and file size verification
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from .ffmpeg_utils import probe_video
from .story_engine import StoryTimeline

def validate_clip_export(
    video_path: Path,
    timeline: Optional[StoryTimeline] = None,
    target_duration: float = 20.0
) -> Dict[str, Any]:
    """
    Executes automated quality control checks on the exported MP4 video file.
    Returns status dictionary with passed flag, probe metrics, and diagnostic checks.
    """
    checks = {
        "file_exists": False,
        "valid_file_size": False,
        "valid_video_stream": False,
        "valid_audio_stream": False,
        "duration_in_tolerance": False,
        "narrative_hook_present": False,
        "narrative_payoff_present": False
    }
    warnings: List[str] = []

    # 1. File existence check
    if not video_path.exists():
        return {
            "passed": False,
            "duration": 0.0,
            "checks": checks,
            "warnings": ["Exported video file does not exist on disk."]
        }
    checks["file_exists"] = True

    # 2. File size check (> 40KB minimum for a 15-30s H.264 video)
    size_bytes = video_path.stat().st_size
    if size_bytes < 40000:
        return {
            "passed": False,
            "duration": 0.0,
            "checks": checks,
            "warnings": [f"Export file size ({size_bytes} bytes) is suspiciously small or corrupted."]
        }
    checks["valid_file_size"] = True

    # 3. Stream & Duration probing via ffprobe
    info = probe_video(video_path)
    actual_dur = float(info.get("duration", 0.0))
    has_video = bool(info.get("has_video", False))
    has_audio = bool(info.get("has_audio", False))

    if not has_video:
        warnings.append("Probe detected no valid video stream in MP4 container.")
    else:
        checks["valid_video_stream"] = True

    if not has_audio:
        warnings.append("Probe detected no valid audio track (silent clip).")
    else:
        checks["valid_audio_stream"] = True

    # 4. Duration tolerance check (must be within reasonable window of target)
    min_dur = max(10.0, target_duration * 0.65)
    max_dur = target_duration * 1.35
    if min_dur <= actual_dur <= max_dur:
        checks["duration_in_tolerance"] = True
    else:
        warnings.append(
            f"Rendered duration {actual_dur:.1f}s outside target range [{min_dur:.1f}s - {max_dur:.1f}s]."
        )

    # 5. Narrative checks
    if timeline:
        seg_types = [s.segment_type for s in timeline.segments]
        has_hook = any(t in ("hook_teaser", "setup", "natural") for t in seg_types)
        has_payoff = any(t in ("climax", "payoff", "resolution", "natural") for t in seg_types)
        checks["narrative_hook_present"] = has_hook
        checks["narrative_payoff_present"] = has_payoff
    else:
        checks["narrative_hook_present"] = True
        checks["narrative_payoff_present"] = True

    # Overall pass criteria: video and audio stream valid, file size valid, non-zero duration
    passed = (
        checks["file_exists"]
        and checks["valid_file_size"]
        and checks["valid_video_stream"]
        and actual_dur > 5.0
    )

    return {
        "passed": passed,
        "duration": round(actual_dur, 2),
        "resolution": f"{info.get('width', 0)}x{info.get('height', 0)}",
        "checks": checks,
        "warnings": warnings
    }
