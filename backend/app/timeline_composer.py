"""
ClipForge AI 2.0 - Multi-Segment Timeline Composer
===================================================
Renders structured multi-segment narrative timelines using FFmpeg:
  - Cold-open teasers & reordered hooks
  - Smart flashback callbacks
  - Punch-in camera zooms on climaxes
  - Contextual SFX mixing (impacts, whooshes, chimes, awkward crickets)
  - Seamless composite timeline subtitle remapping
  - Automatic fallback to standard render if complex filter fails
"""

import subprocess
import tempfile
import shutil
import time
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

from .config import FFMPEG_PATH
from .ffmpeg_utils import get_ffmpeg_bin, render_vertical_clip, probe_video
from .story_engine import StoryTimeline, TimelineSegment
from .renderer import generate_clip_subtitles

def remap_subtitles_for_timeline(
    timeline: StoryTimeline,
    all_source_segments: List[Dict[str, Any]],
    output_ass_path: Path,
    style: str = "hormozi_yellow"
) -> Optional[Path]:
    """
    Remaps source transcript segments and word timestamps into the
    composite timeline coordinates (0.0 to timeline.total_duration).
    Also inserts visual badges like [ FLASHBACK ] or WAIT FOR IT...
    """
    composite_segments = []
    current_composite_time = 0.0

    for seg in timeline.segments:
        seg_start = seg.source_start
        seg_end = seg.source_end
        seg_dur = seg.duration
        comp_start = current_composite_time
        comp_end = current_composite_time + seg_dur

        # If segment has a badge label, insert a visual subtitle event
        if seg.badge_label:
            composite_segments.append({
                "start": comp_start,
                "end": min(comp_end, comp_start + 1.8),
                "text": seg.badge_label,
                "words": [{
                    "word": seg.badge_label,
                    "start": comp_start,
                    "end": min(comp_end, comp_start + 1.8)
                }]
            })

        # Find all source words that fall inside [seg_start, seg_end]
        for src_seg in all_source_segments:
            s_s = float(src_seg.get("start", 0))
            s_e = float(src_seg.get("end", 0))
            # Check overlap
            if s_e <= seg_start or s_s >= seg_end:
                continue

            # Remap words
            remapped_words = []
            for w in src_seg.get("words", []):
                w_s = float(w.get("start", s_s))
                w_e = float(w.get("end", s_e))
                if w_e <= seg_start or w_s >= seg_end:
                    continue
                # Calculate relative position
                rel_s = max(0.0, w_s - seg_start)
                rel_e = min(seg_dur, w_e - seg_start)
                remapped_words.append({
                    "word": w.get("word", ""),
                    "start": round(comp_start + rel_s, 2),
                    "end": round(comp_start + rel_e, 2)
                })

            if remapped_words:
                composite_segments.append({
                    "start": remapped_words[0]["start"],
                    "end": remapped_words[-1]["end"],
                    "text": " ".join(w["word"] for w in remapped_words),
                    "words": remapped_words
                })

        current_composite_time += seg_dur

    if not composite_segments:
        return None

    # Generate ASS subtitles using composite coordinates
    return generate_clip_subtitles(
        clip_start=0.0,
        clip_end=timeline.total_duration,
        segments=composite_segments,
        output_ass_path=output_ass_path,
        style=style
    )

def compose_story_clip(
    source_video: Path,
    timeline: StoryTimeline,
    output_path: Path,
    all_source_segments: List[Dict[str, Any]],
    subtitle_style: str = "hormozi_yellow",
    subtitles_enabled: bool = True,
    aspect_ratio: str = "9:16",
    audio_boost: bool = True
) -> bool:
    """
    Renders the composite story timeline using FFmpeg.
    If timeline only has 1 segment and no SFX, uses standard single-cut renderer.
    If multi-segment, builds filter_complex concatenation with SFX mixing.
    Guarantees automatic fallback to single-cut render on any error.
    """
    # 1. Single-segment fast path
    if len(timeline.segments) <= 1 and not timeline.sfx_cues:
        seg = timeline.segments[0] if timeline.segments else None
        start = seg.source_start if seg else 0.0
        dur = seg.duration if seg else timeline.target_duration
        
        sub_ass = None
        if subtitles_enabled:
            temp_ass = output_path.parent / f"temp_{output_path.stem}.ass"
            sub_ass = generate_clip_subtitles(
                clip_start=start,
                clip_end=start + dur,
                segments=all_source_segments,
                output_ass_path=temp_ass,
                style=subtitle_style
            )

        return render_vertical_clip(
            source_video=source_video,
            start_time=start,
            duration=dur,
            output_path=output_path,
            subtitle_path=sub_ass,
            aspect_ratio=aspect_ratio,
            audio_boost=audio_boost
        )

    # 2. Multi-segment narrative rendering
    ffmpeg = get_ffmpeg_bin()
    temp_dir = Path(tempfile.gettempdir())
    tmp_output = temp_dir / f"clipforge_comp_{output_path.stem}_{int(time.time()*1000)}.mp4"
    temp_ass = output_path.parent / f"temp_{output_path.stem}.ass"

    try:
        # Prepare subtitles
        sub_file = None
        if subtitles_enabled:
            sub_file = remap_subtitles_for_timeline(
                timeline=timeline,
                all_source_segments=all_source_segments,
                output_ass_path=temp_ass,
                style=subtitle_style
            )

        # Build FFmpeg command inputs
        cmd = [ffmpeg, "-y", "-i", str(source_video)]

        # Additional audio inputs for SFX
        sfx_inputs = []
        for sfx in timeline.sfx_cues:
            sfx_path = Path(sfx.get("sfx_path", ""))
            if sfx_path.exists() and sfx_path.stat().st_size > 100:
                cmd.extend(["-i", str(sfx_path)])
                sfx_inputs.append(sfx)

        # Build filter_complex
        filter_parts = []
        n_segs = len(timeline.segments)
        
        # Trim and transform each segment to uniform canvas with setsar=1
        for i, seg in enumerate(timeline.segments):
            s_start = f"{seg.source_start:.3f}"
            s_dur = f"{seg.duration:.3f}"
            
            # Base video trim
            v_filters = [f"trim=start={s_start}:duration={s_dur}", "setpts=PTS-STARTPTS"]

            # Aspect ratio formatting with punch-in zoom support
            if aspect_ratio == "1:1":
                if seg.zoom_effect:
                    v_filters.append("crop=w='min(iw,ih)/1.18':h='min(iw,ih)/1.18':x='(iw-ow)/2':y='(ih-oh)/2',scale=1080:1080:flags=lanczos,setsar=1")
                else:
                    v_filters.append("crop=w='min(iw,ih)':h='min(iw,ih)':x='(iw-ow)/2':y='(ih-oh)/2',scale=1080:1080:flags=lanczos,setsar=1")
            elif aspect_ratio == "16:9":
                if seg.zoom_effect:
                    v_filters.append("crop=w='iw/1.18':h='ih/1.18':x='(iw-ow)/2':y='(ih-oh)/2',scale=1920:1080:flags=lanczos,setsar=1")
                else:
                    v_filters.append("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1")
            else: # 9:16 vertical
                if seg.zoom_effect:
                    v_filters.append("crop=w='min(iw,ih*9/16)/1.18':h='min(ih,iw*16/9)/1.18':x='(iw-ow)/2':y='(ih-oh)/2',scale=1080:1920:flags=lanczos,setsar=1")
                else:
                    v_filters.append("crop=w='min(iw,ih*9/16)':h='min(ih,iw*16/9)':x='(iw-ow)/2':y='(ih-oh)/2',scale=1080:1920:flags=lanczos,setsar=1")
            
            filter_parts.append(f"[0:v]{','.join(v_filters)}[v{i}];")
            
            # Audio trim with resampling for seamless seamless cuts
            filter_parts.append(
                f"[0:a]atrim=start={s_start}:duration={s_dur},asetpts=PTS-STARTPTS,aresample=async=1000[a{i}];"
            )

        # Concat video & audio segments (interleaved [v0][a0][v1][a1]...)
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n_segs))
        filter_parts.append(f"{concat_inputs}concat=n={n_segs}:v=1:a=1[vcat][acat];")

        # Subtitle overlay on concatenated video if present
        if sub_file and sub_file.exists():
            sub_str = str(sub_file.resolve()).replace('\\', '/').replace(':', '\\:')
            filter_parts.append(f"[vcat]subtitles=filename='{sub_str}'[vfinal];")
            v_out_tag = "[vfinal]"
        else:
            v_out_tag = "[vcat]"

        # SFX mixing into audio
        if sfx_inputs:
            # We have additional audio inputs starting from index 1
            sfx_labels = []
            for idx, sfx in enumerate(sfx_inputs, 1):
                delay_ms = int(max(0.0, sfx.get("time_offset", 0.0)) * 1000)
                vol = float(sfx.get("volume", 0.8))
                filter_parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms},volume={vol}[sfx{idx}];")
                sfx_labels.append(f"[sfx{idx}]")

            all_audio = f"[acat]{''.join(sfx_labels)}"
            n_audio = 1 + len(sfx_labels)
            amix_out = "amix=inputs={n}:duration=first:dropout_transition=2".format(n=n_audio)
            if audio_boost:
                filter_parts.append(f"{all_audio}{amix_out},loudnorm=I=-16:TP=-1.5:LRA=11,volume=1.15[afinal];")
            else:
                filter_parts.append(f"{all_audio}{amix_out}[afinal];")
            a_out_tag = "[afinal]"
        else:
            if audio_boost:
                filter_parts.append(f"[acat]loudnorm=I=-16:TP=-1.5:LRA=11,volume=1.15[afinal];")
                a_out_tag = "[afinal]"
            else:
                a_out_tag = "[acat]"

        # Complete filter complex string (remove trailing semicolon if present)
        full_filter = "".join(filter_parts).rstrip(";")

        cmd.extend([
            "-filter_complex", full_filter,
            "-map", v_out_tag,
            "-map", a_out_tag,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "160k",
            "-ar", "44100",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            str(tmp_output)
        ])

        # Execute FFmpeg multi-segment render
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if res.returncode == 0 and tmp_output.exists() and tmp_output.stat().st_size > 50000:
            # Safely copy to destination with retry for OneDrive locks
            output_path.parent.mkdir(parents=True, exist_ok=True)
            for attempt in range(6):
                try:
                    if output_path.exists():
                        output_path.unlink()
                    shutil.copy2(tmp_output, output_path)
                    break
                except (PermissionError, OSError):
                    time.sleep(0.4 * (attempt + 1))
            
            try:
                tmp_output.unlink(missing_ok=True)
            except Exception:
                pass
            return output_path.exists() and output_path.stat().st_size > 0
        else:
            print(f"[Warning] Multi-segment composite render failed: {res.stderr[-500:]}")
            # Fall back to single-cut continuous render
            raise RuntimeError("Composite filter failed, triggering graceful fallback")

    except Exception as e:
        print(f"[Warning] Falling back to standard render due to: {e}")
        try:
            tmp_output.unlink(missing_ok=True)
        except Exception:
            pass

        # GRACEFUL FALLBACK: Render continuous candidate window without crashing
        first_seg = timeline.segments[0] if timeline.segments else None
        last_seg = timeline.segments[-1] if timeline.segments else None
        fb_start = first_seg.source_start if first_seg else 0.0
        fb_end = last_seg.source_end if last_seg else (fb_start + timeline.target_duration)
        fb_dur = min(timeline.target_duration, fb_end - fb_start)

        sub_ass = None
        if subtitles_enabled:
            temp_ass = output_path.parent / f"temp_{output_path.stem}.ass"
            sub_ass = generate_clip_subtitles(
                clip_start=fb_start,
                clip_end=fb_start + fb_dur,
                segments=all_source_segments,
                output_ass_path=temp_ass,
                style=subtitle_style
            )

        return render_vertical_clip(
            source_video=source_video,
            start_time=fb_start,
            duration=fb_dur,
            output_path=output_path,
            subtitle_path=sub_ass,
            aspect_ratio=aspect_ratio,
            audio_boost=audio_boost
        )
