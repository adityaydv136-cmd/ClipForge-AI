import asyncio
import os
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from .config import PROJECTS_DIR
from .database import (
    save_project, update_project_status, save_clip, get_project
)
from .ffmpeg_utils import (
    probe_video, extract_audio, render_vertical_clip, generate_thumbnail
)
from .downloader import download_video, SourceRestrictedError
from .transcriber import transcribe_audio
from .scene_analyzer import detect_scene_changes, analyze_visual_energy, analyze_visuals
from .highlight_detector import find_best_highlights
from .renderer import generate_clip_subtitles, generate_clip_srt, create_project_zip
from .story_engine import build_story_timeline
from .timeline_composer import compose_story_clip
from .quality_controller import validate_clip_export

# Active event queues for SSE subscribers per project: project_id -> set of asyncio.Queue
_PROJECT_SUBSCRIBERS: Dict[str, List[asyncio.Queue]] = {}
# Active cancellation flags
_CANCEL_FLAGS: Dict[str, bool] = {}

def subscribe_project_events(project_id: str) -> asyncio.Queue:
    queue = asyncio.Queue()
    if project_id not in _PROJECT_SUBSCRIBERS:
        _PROJECT_SUBSCRIBERS[project_id] = []
    _PROJECT_SUBSCRIBERS[project_id].append(queue)
    return queue

def unsubscribe_project_events(project_id: str, queue: asyncio.Queue):
    if project_id in _PROJECT_SUBSCRIBERS:
        try:
            _PROJECT_SUBSCRIBERS[project_id].remove(queue)
            if not _PROJECT_SUBSCRIBERS[project_id]:
                del _PROJECT_SUBSCRIBERS[project_id]
        except ValueError:
            pass

async def emit_project_event(project_id: str, event_data: Dict[str, Any]):
    queues = _PROJECT_SUBSCRIBERS.get(project_id, [])
    for q in list(queues):
        try:
            await q.put(event_data)
        except Exception:
            pass

def cancel_project_processing(project_id: str) -> bool:
    _CANCEL_FLAGS[project_id] = True
    return True

def is_project_cancelled(project_id: str) -> bool:
    return _CANCEL_FLAGS.get(project_id, False)

async def process_project_pipeline(project_id: str):
    """
    Main asynchronous processing pipeline running in background worker.
    """
    _CANCEL_FLAGS[project_id] = False
    project = get_project(project_id)
    if not project:
        return

    project_dir = PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = project_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    source_path = project_dir / "source.mp4"
    loop = asyncio.get_running_loop()

    async def update_stage(stage: str, progress: int, msg: str):
        update_project_status(project_id, "processing", stage, progress, msg)
        await emit_project_event(project_id, {
            "type": "progress",
            "project_id": project_id,
            "status": "processing",
            "stage": stage,
            "progress": progress,
            "message": msg
        })

    try:
        # STAGE 1: Checking source
        await update_stage("checking_source", 5, "Checking video source and accessibility...")

        if is_project_cancelled(project_id):
            update_project_status(project_id, "cancelled", "checking_source", 0, "Cancelled by user")
            await emit_project_event(project_id, {"type": "cancelled", "message": "Job was cancelled."})
            return

        if project["source_type"] == "url":
            source_url = project["source_url"]
            needs_download = not source_path.exists() or source_path.stat().st_size == 0
            if not needs_download:
                # Validate existing cached file
                cached_info = probe_video(source_path)
                if cached_info.get("duration", 0) <= 0:
                    try:
                        source_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    needs_download = True

            if needs_download:
                await update_stage("checking_source", 10, "Accessing YouTube media stream...")
                
                def dl_progress(pct, text):
                    asyncio.run_coroutine_threadsafe(
                        emit_project_event(project_id, {
                            "type": "progress",
                            "project_id": project_id,
                            "status": "processing",
                            "stage": "checking_source",
                            "progress": 5 + int(pct * 0.15),
                            "message": text
                        }),
                        loop
                    )

                # Run download in thread to keep event loop responsive
                dl_info = await loop.run_in_executor(
                    None, lambda: download_video(source_url, source_path, dl_progress)
                )
                
                # Update title and thumbnail if empty
                if not project.get("title") or project["title"] == "Untitled Project":
                    project["title"] = dl_info.get("title", "YouTube Video")
                    project["thumbnail_url"] = dl_info.get("thumbnail_url")
                    project["duration"] = dl_info.get("duration", 0)
                    save_project(project)
        else:
            # Uploaded video is already saved at source_path
            if not source_path.exists():
                raise FileNotFoundError("Uploaded video file was not found on server.")

        # Probe video
        info = probe_video(source_path)
        total_duration = info["duration"]
        if total_duration <= 0:
            raise ValueError("Unable to read valid video streams from source file.")

        project["duration"] = total_duration
        save_project(project)

        # STAGE 2: Extracting audio
        if is_project_cancelled(project_id):
            update_project_status(project_id, "cancelled", "extracting_audio", 0, "Cancelled by user")
            return

        audio_wav = project_dir / "audio.wav"
        if not audio_wav.exists() or audio_wav.stat().st_size == 0:
            await update_stage("extracting_audio", 25, "Extracting audio track for transcription...")
            extracted = await loop.run_in_executor(None, lambda: extract_audio(source_path, audio_wav))
            if not extracted or not audio_wav.exists():
                raise RuntimeError("Audio extraction failed. Video might be silent or audio stream corrupted.")
        else:
            await update_stage("extracting_audio", 25, "Audio track verified...")

        # STAGE 3: Transcribing speech
        if is_project_cancelled(project_id):
            update_project_status(project_id, "cancelled", "transcribing_speech", 0, "Cancelled by user")
            return

        await update_stage("transcribing_speech", 35, "Transcribing speech using faster-whisper...")

        def transcribe_cb(pct, text):
            asyncio.run_coroutine_threadsafe(
                emit_project_event(project_id, {
                    "type": "progress",
                    "project_id": project_id,
                    "status": "processing",
                    "stage": "transcribing_speech",
                    "progress": 35 + int(pct * 0.25),
                    "message": text
                }),
                loop
            )

        segments = await loop.run_in_executor(
            None, lambda: transcribe_audio(audio_wav, progress_callback=transcribe_cb)
        )

        # STAGE 4: Analyzing highlights & Scene detection
        if is_project_cancelled(project_id):
            update_project_status(project_id, "cancelled", "analyzing_highlights", 0, "Cancelled by user")
            return

        await update_stage("analyzing_highlights", 62, "Analyzing visual dynamics and scene cuts...")

        def visual_progress(pct, text):
            asyncio.run_coroutine_threadsafe(
                emit_project_event(project_id, {
                    "type": "progress",
                    "project_id": project_id,
                    "status": "processing",
                    "stage": "analyzing_highlights",
                    "progress": 62 + int(pct * 6.0),
                    "message": text
                }),
                loop
            )

        try:
            scene_cuts, motion_profile = await loop.run_in_executor(
                None, lambda: analyze_visuals(source_path, total_duration, progress_cb=visual_progress, max_samples=25)
            )
        except Exception as e:
            print(f"[Warning] Visual analysis fallback: {e}")
            scene_cuts, motion_profile = [], []

        await update_stage("analyzing_highlights", 70, "Scoring viral hooks and thought boundaries...")

        # Parse duration and clips options
        dur_opt = project.get("duration_option", "20")
        if dur_opt == "20":
            target_durations = [20.0]
        elif dur_opt == "30":
            target_durations = [30.0]
        else: # "both"
            target_durations = [20.0, 30.0]

        num_opt = project.get("num_clips_option", "3")
        if num_opt == "auto":
            max_clips = 4
        else:
            try:
                max_clips = int(num_opt)
            except ValueError:
                max_clips = 3

        selected_highlights = find_best_highlights(
            segments=segments,
            total_duration=total_duration,
            target_durations=target_durations,
            max_clips=max_clips,
            scene_cuts=scene_cuts,
            motion_scores=motion_profile
        )

        if not selected_highlights:
            raise RuntimeError("Could not identify highlight candidates of requested length.")

        # STAGE 5: Rendering shorts (ClipForge 2.0 Narrative Story Architecture)
        total_clips = len(selected_highlights)
        rendered_clips = []
        editing_personality = project.get("editing_personality", "retention")
        memes_enabled = bool(project.get("memes_enabled", True))
        sub_style = project.get("subtitle_style", "hormozi_yellow")
        subtitles_enabled = bool(project.get("subtitles_enabled", True))

        for idx, highlight in enumerate(selected_highlights, 1):
            if is_project_cancelled(project_id):
                update_project_status(project_id, "cancelled", "rendering_shorts", 0, "Cancelled by user")
                return

            render_pct = 75 + int((idx - 1) / total_clips * 20.0)
            clip_dur_label = f"{int(highlight['duration'])}s"
            await update_stage("rendering_shorts", render_pct, f"Structuring & Rendering Short {idx} of {total_clips} ({clip_dur_label} • {editing_personality.title()})...")

            clip_id = str(uuid.uuid4())
            clip_mp4 = clips_dir / f"clip_{idx}.mp4"
            clip_thumb = clips_dir / f"clip_{idx}_thumb.jpg"
            temp_srt = clips_dir / f"clip_{idx}.srt"

            # 1. Build complete multi-stage story timeline (Hook, Context, Buildup, Flashback, Climax, Payoff)
            story_timeline = build_story_timeline(
                candidate=highlight,
                all_source_segments=segments,
                target_duration=highlight.get("target_duration", 20.0),
                personality=editing_personality,
                memes_enabled=memes_enabled
            )

            # 2. Render composite short using multi-segment timeline composer with camera zoom, SFX & burned subtitles
            render_success = await loop.run_in_executor(
                None,
                lambda: compose_story_clip(
                    source_video=source_path,
                    timeline=story_timeline,
                    output_path=clip_mp4,
                    all_source_segments=segments,
                    subtitle_style=sub_style,
                    subtitles_enabled=subtitles_enabled,
                    aspect_ratio="9:16",
                    audio_boost=True
                )
            )

            if not render_success or not clip_mp4.exists():
                # Emergency fallback: standard vertical cut
                render_success = await loop.run_in_executor(
                    None,
                    lambda: render_vertical_clip(
                        source_video=source_path,
                        start_time=highlight["start"],
                        duration=highlight["duration"],
                        output_path=clip_mp4,
                        subtitle_path=None
                    )
                )

            if render_success and clip_mp4.exists():
                # Also save standard SRT alongside for optional user export
                try:
                    generate_clip_srt(
                        clip_start=highlight["start"],
                        clip_end=highlight["end"],
                        segments=highlight.get("segments", []),
                        output_srt_path=temp_srt
                    )
                except Exception:
                    pass

                # 3. Quality Control (QC) Pass
                qc_report = validate_clip_export(
                    video_path=clip_mp4,
                    timeline=story_timeline,
                    target_duration=highlight.get("target_duration", 20.0)
                )

                # 4. Generate thumbnail
                await loop.run_in_executor(
                    None,
                    lambda: generate_thumbnail(clip_mp4, min(1.0, highlight["duration"] / 2.0), clip_thumb)
                )

                clip_data = {
                    "id": clip_id,
                    "project_id": project_id,
                    "title": highlight["title"],
                    "start_time": highlight["start"],
                    "end_time": highlight["end"],
                    "duration": qc_report.get("duration", highlight["duration"]),
                    "score": highlight["score"],
                    "summary": highlight.get("text", "")[:120],
                    "file_path": str(clip_mp4),
                    "thumbnail_path": str(clip_thumb) if clip_thumb.exists() else None,
                    "aspect_ratio": "9:16",
                    "hook_tag": highlight.get("hook_tag", "🔥 Viral Hook"),
                    "hook_category": highlight.get("hook_category", "Curiosity Gap"),
                    "retention_3s": highlight.get("retention_3s_pct", 92.0),
                    "editing_personality": editing_personality,
                    "story_structure": story_timeline.to_dict(),
                    "qc_passed": qc_report.get("passed", True),
                }
                save_clip(clip_data)
                rendered_clips.append(clip_data)

                # Emit immediate clip ready event!
                await emit_project_event(project_id, {
                    "type": "clip_ready",
                    "project_id": project_id,
                    "clip": clip_data,
                    "clip_index": idx,
                    "total_clips": total_clips
                })

        if not rendered_clips:
            raise RuntimeError("Rendering failed for all selected highlights.")

        # STAGE 6: Preparing downloads (ZIP archive)
        await update_stage("preparing_downloads", 96, "Packaging clips into Download All ZIP archive...")
        zip_path = project_dir / f"{project_id}_shorts.zip"
        
        await loop.run_in_executor(
            None,
            lambda: create_project_zip(project_id, project.get("title", "ClipForge"), rendered_clips, zip_path)
        )

        # STAGE 7: Completed
        update_project_status(
            project_id=project_id,
            status="completed",
            stage="completed",
            progress=100,
            message=f"Successfully generated {len(rendered_clips)} shorts!",
            zip_path=str(zip_path)
        )

        await emit_project_event(project_id, {
            "type": "completed",
            "project_id": project_id,
            "status": "completed",
            "stage": "completed",
            "progress": 100,
            "message": f"Successfully generated {len(rendered_clips)} shorts!",
            "clips_count": len(rendered_clips),
            "zip_url": f"/api/projects/{project_id}/download-all"
        })

    except SourceRestrictedError as sre:
        err_msg = str(sre)
        update_project_status(project_id, "failed", "failed", 0, err_msg)
        await emit_project_event(project_id, {
            "type": "error",
            "project_id": project_id,
            "status": "failed",
            "error_type": "permission_or_restricted",
            "message": err_msg
        })
    except PermissionError as pe:
        err_msg = f"File access error on Windows: {str(pe)}. If this folder is synced by OneDrive, please allow sync or retry."
        update_project_status(project_id, "failed", "failed", 0, err_msg)
        await emit_project_event(project_id, {
            "type": "error",
            "project_id": project_id,
            "status": "failed",
            "error_type": "processing_error",
            "message": err_msg
        })
    except Exception as e:
        err_msg = str(e)
        update_project_status(project_id, "failed", "failed", 0, err_msg)
        await emit_project_event(project_id, {
            "type": "error",
            "project_id": project_id,
            "status": "failed",
            "error_type": "processing_error",
            "message": err_msg
        })
