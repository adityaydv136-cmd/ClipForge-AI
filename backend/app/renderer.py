import os
import re
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional

SUBTITLE_THEMES = {
    "hormozi_yellow": {
        "name": "Viral Gold (Hormozi / MrBeast)",
        "highlight_ass": "&H001FE8FF&", # #FFE81F (Yellow/Amber)
        "secondary_ass": "&H00FFFFFF&", # Crisp White
    },
    "neon_green": {
        "name": "Cyber Lime (High Energy)",
        "highlight_ass": "&H0032FF00&", # #00FF32 (Electric Green)
        "secondary_ass": "&H00FFFFFF&",
    },
    "electric_cyan": {
        "name": "Electric Cyan (Tech & Modern)",
        "highlight_ass": "&H00FFE500&", # #00E5FF (Electric Cyan)
        "secondary_ass": "&H00FFFFFF&",
    },
    "sunset_orange": {
        "name": "Sunset Flame (Warm & Vibrant)",
        "highlight_ass": "&H00006DFF&", # #FF6D00 (Flame Orange)
        "secondary_ass": "&H00FFFFFF&",
    },
    "pink_fuchsia": {
        "name": "Neon Fuchsia (Punchy & Bold)",
        "highlight_ass": "&H00FF00EA&", # #EA00FF (Neon Pink)
        "secondary_ass": "&H00FFFFFF&",
    },
}

def format_ass_timestamp(seconds: float) -> str:
    """Format seconds to h:mm:ss.cc for ASS subtitles."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

def format_srt_timestamp(seconds: float) -> str:
    """Format seconds to 00:00:00,000 for SRT."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def clean_word(word: str) -> str:
    """Clean word text for punchy uppercase shorts typography."""
    w = re.sub(r'[\r\n\t]+', '', word)
    w = re.sub(r'[^\w\s\'!?-]', '', w).strip()
    return w.upper()

def generate_clip_subtitles(
    clip_start: float,
    clip_end: float,
    segments: List[Dict[str, Any]],
    output_ass_path: Path,
    style: str = "hormozi_yellow",
    position: str = "bottom",
    font_size_mode: str = "large",
    aspect_ratio: str = "9:16"
) -> Optional[Path]:
    """
    Generate professional, viral creator-style ASS captions:
    - Bold, punchy typography (Arial Black / Impact)
    - 2-3 word rapid rhythmic pacing
    - High-contrast 8px black outline + 4px drop shadow for 100% legibility
    - Active spoken word pop in viral accent color (Hormozi Gold / Neon Green / Electric Cyan)
    - Safe margins and dynamic positioning (bottom / center / top)
    """
    theme = SUBTITLE_THEMES.get(style, SUBTITLE_THEMES["hormozi_yellow"])
    hi_col = theme["highlight_ass"]
    sec_col = theme["secondary_ass"]

    all_words = []
    for seg in segments:
        words = seg.get("words", [])
        if words:
            for w in words:
                if clip_start <= w["end"] and w["start"] <= clip_end:
                    cw = clean_word(w.get("word", ""))
                    if cw:
                        all_words.append({
                            "word": cw,
                            "start": max(clip_start, float(w["start"])),
                            "end": min(clip_end, float(w["end"]))
                        })
        else:
            seg_start = max(clip_start, float(seg["start"]))
            seg_end = min(clip_end, float(seg["end"]))
            if seg_start < seg_end:
                words_list = [clean_word(x) for x in seg.get("text", "").split()]
                words_list = [x for x in words_list if x]
                if words_list:
                    dur_per = (seg_end - seg_start) / len(words_list)
                    for idx, txt in enumerate(words_list):
                        w_s = seg_start + (idx * dur_per)
                        w_e = w_s + dur_per
                        all_words.append({"word": txt, "start": w_s, "end": w_e})

    if not all_words:
        return None

    # Group into short, punchy 2-3 word chunks (ideal viral creator rhythm)
    chunk_size = 3
    dialogue_events = []
    total_words = len(all_words)
    clip_duration = clip_end - clip_start

    i = 0
    while i < total_words:
        # Form chunk of 2-3 words, breaking on pauses > 0.4s
        chunk = [all_words[i]]
        j = i + 1
        while j < total_words and len(chunk) < chunk_size:
            gap = all_words[j]["start"] - chunk[-1]["end"]
            if gap > 0.4:
                break
            chunk.append(all_words[j])
            j += 1
        i = j

        # Ensure valid chunk timing relative to clip start
        c_start = max(0.0, chunk[0]["start"] - clip_start)
        c_end = max(c_start + 0.3, chunk[-1]["end"] - clip_start)
        c_end = min(clip_duration, c_end)
        if c_start >= c_end:
            continue

        # Generate active-word pop events for each word in this chunk
        for k, current_word in enumerate(chunk):
            w_start = max(c_start, current_word["start"] - clip_start)
            # End when next word starts, or at chunk end
            if k < len(chunk) - 1:
                w_end = max(w_start + 0.15, chunk[k + 1]["start"] - clip_start)
            else:
                w_end = c_end

            w_end = min(clip_duration, max(w_start + 0.15, w_end))
            if w_start >= w_end:
                continue

            # Build formatted dialogue line: active word highlighted in theme color, rest in crisp white
            formatted_words = []
            for m, w_item in enumerate(chunk):
                txt = w_item["word"]
                if m == k:
                    # Highlighted active word
                    formatted_words.append(f"{{\\c{hi_col}}}{txt}{{\\c{sec_col}}}")
                else:
                    formatted_words.append(txt)

            line_text = " ".join(formatted_words)
            start_str = format_ass_timestamp(w_start)
            end_str = format_ass_timestamp(w_end)

            dialogue_events.append(
                f"Dialogue: 0,{start_str},{end_str},ViralShorts,,0,0,0,,{line_text}"
            )

    if not dialogue_events:
        return None

    # Compute dynamic resolution, margin and alignment
    if aspect_ratio == "1:1":
        res_x, res_y = 1080, 1080
        base_size = 70
        margin_bottom = 120
        margin_center = 480
        margin_top = 80
    elif aspect_ratio == "16:9":
        res_x, res_y = 1920, 1080
        base_size = 62
        margin_bottom = 100
        margin_center = 480
        margin_top = 70
    else:  # 9:16 vertical
        res_x, res_y = 1080, 1920
        base_size = 80
        margin_bottom = 420
        margin_center = 880
        margin_top = 220

    if font_size_mode == "huge":
        calc_fontsize = int(base_size * 1.18)
    elif font_size_mode == "compact":
        calc_fontsize = int(base_size * 0.84)
    else:
        calc_fontsize = base_size

    if position == "top":
        alignment = 8  # Top-center
        margin_v = margin_top
    elif position == "center":
        alignment = 5  # Mid-center
        margin_v = 0
    else:
        alignment = 2  # Bottom-center
        margin_v = margin_bottom

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralShorts,Arial Black,{calc_fontsize},{sec_col},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,4,{alignment},40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(dialogue_events) + "\n"

    output_ass_path.parent.mkdir(parents=True, exist_ok=True)
    output_ass_path.write_text(ass_content, encoding="utf-8")
    return output_ass_path

def generate_clip_srt(
    clip_start: float,
    clip_end: float,
    segments: List[Dict[str, Any]],
    output_srt_path: Path
) -> Optional[Path]:
    """Generate standard clean SRT file for export/download."""
    all_words = []
    for seg in segments:
        words = seg.get("words", [])
        if words:
            for w in words:
                if clip_start <= w["end"] and w["start"] <= clip_end:
                    cw = clean_word(w.get("word", ""))
                    if cw:
                        all_words.append({
                            "word": cw,
                            "start": max(clip_start, float(w["start"])),
                            "end": min(clip_end, float(w["end"]))
                        })
        else:
            seg_start = max(clip_start, float(seg["start"]))
            seg_end = min(clip_end, float(seg["end"]))
            if seg_start < seg_end:
                words_list = [clean_word(x) for x in seg.get("text", "").split()]
                words_list = [x for x in words_list if x]
                if words_list:
                    dur_per = (seg_end - seg_start) / len(words_list)
                    for idx, txt in enumerate(words_list):
                        w_s = seg_start + (idx * dur_per)
                        w_e = w_s + dur_per
                        all_words.append({"word": txt, "start": w_s, "end": w_e})

    if not all_words:
        return None

    chunk_size = 3
    srt_entries = []
    entry_idx = 1
    clip_duration = clip_end - clip_start

    for i in range(0, len(all_words), chunk_size):
        chunk = all_words[i:i + chunk_size]
        rel_start = max(0.0, chunk[0]["start"] - clip_start)
        rel_end = max(rel_start + 0.3, chunk[-1]["end"] - clip_start)
        rel_end = min(clip_duration, rel_end)

        phrase = " ".join(w["word"] for w in chunk).strip()
        if not phrase:
            continue

        srt_entries.append(
            f"{entry_idx}\n"
            f"{format_srt_timestamp(rel_start)} --> {format_srt_timestamp(rel_end)}\n"
            f"{phrase}\n"
        )
        entry_idx += 1

    if not srt_entries:
        return None

    output_srt_path.parent.mkdir(parents=True, exist_ok=True)
    output_srt_path.write_text("\n".join(srt_entries), encoding="utf-8")
    return output_srt_path

def sanitize_filename(name: str) -> str:
    """Strip illegal characters for cross-platform safe filenames."""
    s = re.sub(r'[\\/*?:"<>|]', "", name)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:40] or "clip"

def create_project_zip(
    project_id: str,
    project_title: str,
    clips: List[Dict[str, Any]],
    output_zip_path: Path
) -> Path:
    """Package all generated MP4 files into a single downloadable ZIP archive."""
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)
    clean_title = sanitize_filename(project_title)

    with zipfile.ZipFile(str(output_zip_path), "w", zipfile.ZIP_DEFLATED) as zip_file:
        for idx, clip in enumerate(clips, 1):
            clip_file = Path(clip["file_path"])
            if clip_file.exists():
                dur = int(clip.get("duration", 20))
                clip_title = sanitize_filename(clip.get("title", f"Clip_{idx}"))
                arcname = f"ClipForge_{idx}_{dur}s_{clip_title}.mp4"
                zip_file.write(str(clip_file), arcname=arcname)

    return output_zip_path
