import asyncio
import json
import os
import uuid
import shutil
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form, Request, Header
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from ..config import PROJECTS_DIR, FFMPEG_PATH, FFPROBE_PATH, COOKIES_PATH
from ..models import (
    ProjectCreateRequest, MetadataRequest, MetadataResponse, ProjectResponse,
    CookieStatusResponse, ClipResponse, ClipEditRequest
)
from ..database import (
    save_project, get_project, get_all_projects, delete_project, update_project_status, get_db_connection
)
from ..downloader import is_valid_youtube_url, get_video_metadata, get_active_cookies_file
from ..pipeline import (
    process_project_pipeline, subscribe_project_events, unsubscribe_project_events,
    cancel_project_processing
)
from ..ffmpeg_utils import render_vertical_clip, generate_thumbnail
from ..renderer import generate_clip_subtitles, create_project_zip

router = APIRouter(prefix="/api", tags=["projects"])

@router.get("/cookies/status", response_model=CookieStatusResponse)
def get_cookie_status():
    cf = get_active_cookies_file()
    if cf and cf.exists():
        size = cf.stat().st_size
        return CookieStatusResponse(
            has_cookies=True,
            size_bytes=size,
            message="YouTube authentication cookies active (Netscape cookies.txt)."
        )
    return CookieStatusResponse(
        has_cookies=False,
        size_bytes=0,
        message="No cookies configured (running in anonymous stream mode)."
    )

@router.post("/cookies/upload", response_model=CookieStatusResponse)
async def upload_cookie_file(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded cookie file is empty.")
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIES_PATH.write_bytes(content)
    return CookieStatusResponse(
        has_cookies=True,
        size_bytes=len(content),
        message="Successfully installed YouTube cookies.txt file."
    )

@router.post("/cookies/text", response_model=CookieStatusResponse)
def save_cookie_text(data: dict):
    raw = data.get("content", "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Cookie content cannot be empty.")
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIES_PATH.write_text(raw, encoding="utf-8")
    return CookieStatusResponse(
        has_cookies=True,
        size_bytes=len(raw.encode("utf-8")),
        message="Successfully saved YouTube session cookies."
    )

@router.delete("/cookies", response_model=CookieStatusResponse)
def remove_cookie_file():
    if COOKIES_PATH.exists():
        try:
            COOKIES_PATH.unlink()
        except Exception:
            pass
    return CookieStatusResponse(
        has_cookies=False,
        size_bytes=0,
        message="Cookies removed. System returned to standard anonymous mode."
    )

@router.get("/health")
def health_check():
    """Verify environment health: FFmpeg, disk space, and working directories."""
    total, used, free = shutil.disk_usage(str(PROJECTS_DIR))
    free_gb = round(free / (1024 ** 3), 2)
    
    return {
        "status": "healthy",
        "ffmpeg_installed": FFMPEG_PATH is not None,
        "ffmpeg_path": FFMPEG_PATH,
        "ffprobe_path": FFPROBE_PATH,
        "free_disk_space_gb": free_gb,
        "engine": "local-whisper-ffmpeg-opencv"
    }

@router.post("/metadata", response_model=MetadataResponse)
def resolve_metadata(req: MetadataRequest):
    """Resolve video details before starting processing."""
    data = get_video_metadata(req.url)
    return MetadataResponse(
        title=data.get("title", ""),
        duration=data.get("duration", 0),
        thumbnail_url=data.get("thumbnail_url"),
        author=data.get("author"),
        is_valid=data.get("is_valid", False),
        error=data.get("error")
    )

@router.post("/projects", response_model=ProjectResponse)
async def create_project_from_url(req: ProjectCreateRequest, background_tasks: BackgroundTasks):
    """Initiate a video-to-shorts pipeline from a YouTube URL."""
    if not req.url or not is_valid_youtube_url(req.url):
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid YouTube URL (e.g., https://www.youtube.com/watch?v=... or https://youtu.be/...)"
        )

    project_id = str(uuid.uuid4())[:8]
    meta = get_video_metadata(req.url)
    
    if not meta.get("is_valid"):
        raise HTTPException(
            status_code=400,
            detail=meta.get("error", "Unable to access video. Upload a video file you own or have permission to use.")
        )

    project_data = {
        "id": project_id,
        "title": meta.get("title", "YouTube Video"),
        "source_url": req.url,
        "source_type": "url",
        "thumbnail_url": meta.get("thumbnail_url"),
        "duration": meta.get("duration", 0),
        "status": "processing",
        "stage": "checking_source",
        "progress": 5,
        "status_message": "Initializing highlight analysis...",
        "duration_option": req.duration_option,
        "num_clips_option": req.num_clips_option,
        "subtitles_enabled": req.subtitles_enabled,
        "subtitle_style": req.subtitle_style
    }

    save_project(project_data)
    
    # Spawn background processing task
    background_tasks.add_task(process_project_pipeline, project_id)

    saved = get_project(project_id)
    return saved

@router.post("/upload", response_model=ProjectResponse)
async def create_project_from_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    duration_option: str = Form("20"),
    num_clips_option: str = Form("3"),
    subtitles_enabled: bool = Form(True),
    subtitle_style: str = Form("hormozi_yellow")
):
    """Upload a local video file (MP4, MOV, WebM) directly."""
    allowed_exts = [".mp4", ".mov", ".mkv", ".webm", ".avi"]
    filename = file.filename or "video.mp4"
    ext = Path(filename).suffix.lower()
    
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported format {ext}. Please upload MP4, MOV, or WebM.")

    project_id = str(uuid.uuid4())[:8]
    project_dir = PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    source_path = project_dir / "source.mp4"

    # Save uploaded file safely
    with open(source_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    clean_title = Path(filename).stem.replace("_", " ").title()

    project_data = {
        "id": project_id,
        "title": clean_title,
        "source_url": None,
        "source_type": "upload",
        "thumbnail_url": None,
        "duration": 0,
        "status": "processing",
        "stage": "checking_source",
        "progress": 5,
        "status_message": "Uploaded video saved. Extracting audio...",
        "duration_option": duration_option,
        "num_clips_option": num_clips_option,
        "subtitles_enabled": subtitles_enabled,
        "subtitle_style": subtitle_style
    }

    save_project(project_data)
    background_tasks.add_task(process_project_pipeline, project_id)

    saved = get_project(project_id)
    return saved

@router.get("/projects", response_model=List[dict])
def list_projects():
    """List all projects for the 'My Clips' history drawer."""
    return get_all_projects()

@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project_details(project_id: str):
    """Retrieve full project details and generated clips."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.delete("/projects/{project_id}")
def delete_project_record(project_id: str):
    """Delete a project and its media files."""
    project_dir = PROJECTS_DIR / project_id
    if project_dir.exists():
        try:
            shutil.rmtree(project_dir)
        except Exception:
            pass
    delete_project(project_id)
    return {"success": True, "message": "Project removed."}

@router.post("/projects/{project_id}/cancel")
def cancel_project(project_id: str):
    """Cancel in-flight video processing."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    cancel_project_processing(project_id)
    update_project_status(project_id, "cancelled", "cancelled", 0, "Processing cancelled by user")
    return {"success": True, "message": "Job cancellation requested."}

@router.post("/projects/{project_id}/retry", response_model=ProjectResponse)
async def retry_project(project_id: str, background_tasks: BackgroundTasks):
    """Retry a failed or cancelled project."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_project_status(project_id, "processing", "checking_source", 5, "Retrying processing pipeline...")
    background_tasks.add_task(process_project_pipeline, project_id)
    return get_project(project_id)

@router.get("/projects/{project_id}/events")
async def project_events_stream(project_id: str, request: Request):
    """
    Server-Sent Events (SSE) stream for live real-time progress, stage transitions,
    and instantaneous clip-ready notifications.
    """
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    queue = subscribe_project_events(project_id)

    async def event_generator():
        try:
            # Yield initial current status immediately
            yield {
                "event": "status",
                "data": json.dumps({
                    "type": "initial",
                    "project_id": project_id,
                    "status": project["status"],
                    "stage": project["stage"],
                    "progress": project["progress"],
                    "message": project["status_message"],
                    "clips": project.get("clips", [])
                })
            }

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": "status",
                        "data": json.dumps(event_data) if isinstance(event_data, dict) else str(event_data)
                    }
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield {
                        "event": "ping",
                        "data": json.dumps({"time": "heartbeat"})
                    }
        finally:
            unsubscribe_project_events(project_id, queue)

    return EventSourceResponse(event_generator())

@router.get("/projects/{project_id}/clips/{clip_id}/stream")
def stream_clip_video(project_id: str, clip_id: str, request: Request):
    """
    Stream generated MP4 video with HTTP 206 Partial Content support
    for smooth scrubbing in the HTML5 video preview player.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clips WHERE id = ? AND project_id = ?", (clip_id, project_id))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")

    file_path = Path(row["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        # Parse range: bytes=start-end
        byte_range = range_header.replace("bytes=", "").split("-")
        start = int(byte_range[0])
        end = int(byte_range[1]) if byte_range[1] else file_size - 1
        length = end - start + 1

        def iterfile():
            with open(file_path, "rb") as f:
                f.seek(start)
                bytes_left = length
                chunk_size = 1024 * 1024 # 1MB
                while bytes_left > 0:
                    read_amount = min(chunk_size, bytes_left)
                    data = f.read(read_amount)
                    if not data:
                        break
                    bytes_left -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Type": "video/mp4",
        }
        return StreamingResponse(iterfile(), status_code=206, headers=headers)
    else:
        return FileResponse(file_path, media_type="video/mp4", filename=file_path.name)

@router.get("/projects/{project_id}/clips/{clip_id}/download")
def download_clip_video(project_id: str, clip_id: str):
    """Individual MP4 clip download."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clips WHERE id = ? AND project_id = ?", (clip_id, project_id))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")

    file_path = Path(row["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Clip file missing")

    dur = int(row["duration"])
    clean_title = "".join(c for c in row["title"] if c.isalnum() or c in (" ", "-", "_")).strip()
    download_filename = f"ClipForge_{dur}s_{clean_title.replace(' ', '_')}.mp4"

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=download_filename,
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'}
    )

@router.get("/projects/{project_id}/download-all")
def download_all_zip(project_id: str):
    """Download All ZIP archive containing all rendered MP4 clips."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    zip_path = Path(project.get("zip_path") or (PROJECTS_DIR / project_id / f"{project_id}_shorts.zip"))
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="ZIP archive not generated yet.")

    clean_name = "".join(c for c in project["title"] if c.isalnum() or c in (" ", "-", "_")).strip()
    zip_filename = f"ClipForge_{clean_name.replace(' ', '_')}_Shorts.zip"

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_filename,
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
    )

@router.post("/projects/{project_id}/clips/{clip_id}/rerender", response_model=ClipResponse)
async def rerender_clip(project_id: str, clip_id: str, req: ClipEditRequest):
    """
    Fine-tune and re-render an individual clip with custom start/end time,
    aspect ratio (9:16, 1:1, 16:9), subtitle style & position, and audio booster.
    """
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clips WHERE id = ? AND project_id = ?", (clip_id, project_id))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Clip not found")

    project_dir = PROJECTS_DIR / project_id
    source_path = project_dir / "source.mp4"
    if not source_path.exists():
        raise HTTPException(status_code=400, detail="Source video file not found for re-rendering")

    duration = max(2.5, req.end_time - req.start_time)
    clip_mp4 = Path(row["file_path"])
    clip_thumb = Path(row["thumbnail_path"]) if row["thumbnail_path"] else clip_mp4.parent / f"{clip_id}_thumb.jpg"

    # Subtitle generation if requested
    sub_path = None
    if req.subtitles_enabled:
        temp_ass = project_dir / f"rerender_{clip_id}.ass"
        audio_wav = project_dir / "audio.wav"
        segments = []
        if audio_wav.exists():
            try:
                from ..transcriber import transcribe_audio
                segments = transcribe_audio(audio_wav)
            except Exception:
                segments = []

        sub_path = generate_clip_subtitles(
            clip_start=req.start_time,
            clip_end=req.end_time,
            segments=segments,
            output_ass_path=temp_ass,
            style=req.subtitle_style,
            position=req.subtitle_position,
            font_size_mode=req.subtitle_size,
            aspect_ratio=req.aspect_ratio
        )

    # Render updated clip
    success = render_vertical_clip(
        source_video=source_path,
        start_time=req.start_time,
        duration=duration,
        output_path=clip_mp4,
        subtitle_path=sub_path,
        aspect_ratio=req.aspect_ratio,
        audio_boost=req.audio_boost
    )

    if not success or not clip_mp4.exists():
        # Fallback without subtitle filter
        success = render_vertical_clip(
            source_video=source_path,
            start_time=req.start_time,
            duration=duration,
            output_path=clip_mp4,
            subtitle_path=None,
            aspect_ratio=req.aspect_ratio,
            audio_boost=req.audio_boost
        )

    if not success or not clip_mp4.exists():
        raise HTTPException(status_code=500, detail="Re-rendering clip failed")

    # Re-generate thumbnail
    generate_thumbnail(clip_mp4, min(1.0, duration / 2.0), clip_thumb)

    # Update clip in database
    conn = get_db_connection()
    with conn:
        conn.execute("""
            UPDATE clips
            SET start_time = ?, end_time = ?, duration = ?, aspect_ratio = ?
            WHERE id = ? AND project_id = ?
        """, (req.start_time, req.end_time, duration, req.aspect_ratio, clip_id, project_id))
    conn.close()

    # Regenerate project ZIP
    updated_project = get_project(project_id)
    if updated_project and updated_project.get("clips"):
        zip_path = project_dir / f"{project_id}_shorts.zip"
        create_project_zip(project_id, updated_project.get("title", "ClipForge"), updated_project["clips"], zip_path)

    # Fetch updated clip
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clips WHERE id = ? AND project_id = ?", (clip_id, project_id))
    updated_row = dict(cursor.fetchone())
    conn.close()

    return updated_row
