import sys
import os
import zipfile
import shutil
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import FFMPEG_PATH, FFPROBE_PATH, PROJECTS_DIR
from app.ffmpeg_utils import probe_video, extract_audio, render_vertical_clip, generate_thumbnail
from app.transcriber import transcribe_audio
from app.scene_analyzer import detect_scene_changes, analyze_visual_energy
from app.highlight_detector import find_best_highlights
from app.renderer import generate_clip_srt, create_project_zip
from app.database import init_db, save_project, save_clip, get_project, get_all_projects
from app.downloader import is_valid_youtube_url, get_video_metadata

def run_all_tests():
    print("[1/9] Checking Environment and Binaries...")
    assert FFMPEG_PATH is not None, "FFmpeg binary must be detected"
    print(f"  -> FFmpeg detected: {FFMPEG_PATH}")
    print(f"  -> FFprobe detected: {FFPROBE_PATH}")

    # 1. Probe synthetic video
    sample_video = backend_dir / "tests" / "synthetic_sample.mp4"
    assert sample_video.exists(), f"Sample video {sample_video} not found"
    
    print("[2/9] Probing sample video streams...")
    probe = probe_video(sample_video)
    print(f"  -> Duration: {probe['duration']}s, Size: {probe['width']}x{probe['height']}, FPS: {probe['fps']}")
    assert probe["has_video"], "Must have video stream"
    assert probe["has_audio"], "Must have audio stream"
    assert probe["duration"] > 10, "Duration should be > 10s"

    # 2. Extract audio
    print("[3/9] Extracting audio track to 16kHz mono WAV...")
    temp_wav = backend_dir / "tests" / "test_audio.wav"
    extracted = extract_audio(sample_video, temp_wav)
    assert extracted and temp_wav.exists(), "Audio extraction must succeed"
    print(f"  -> Extracted WAV size: {temp_wav.stat().st_size} bytes")

    # 3. Transcribe audio with faster-whisper
    print("[4/9] Transcribing speech using local faster-whisper model...")
    segments = transcribe_audio(temp_wav, model_size="base")
    print(f"  -> Transcribed {len(segments)} speech segments:")
    full_text = " ".join(s["text"] for s in segments)
    print(f"  -> Transcript snippet: {full_text[:100]}...")
    assert len(segments) > 0, "Must detect speech segments"
    assert any("secret" in s["text"].lower() or "rule" in s["text"].lower() or "focus" in s["text"].lower() for s in segments), "Expected speech words in transcript"

    # 4. OpenCV scene cuts and motion analysis
    print("[5/9] Analyzing visual energy and scene boundaries with OpenCV...")
    scene_cuts = detect_scene_changes(sample_video)
    motion_profile = analyze_visual_energy(sample_video, probe["duration"])
    print(f"  -> Detected {len(scene_cuts)} scene cuts, {len(motion_profile)} motion points")

    # 5. Highlight detection
    print("[6/9] Running AI highlight detector...")
    highlights = find_best_highlights(
        segments=segments,
        total_duration=probe["duration"],
        target_durations=[20.0],
        max_clips=2,
        scene_cuts=scene_cuts,
        motion_scores=motion_profile
    )
    print(f"  -> Generated {len(highlights)} candidate shorts:")
    for h in highlights:
        print(f"     * Title: '{h['title']}', Duration: {h['duration']}s, Score: {h['score']}%")
    assert len(highlights) > 0, "Must produce at least one highlight candidate"

    # 6. Render vertical short with subtitles
    print("[7/9] Rendering 9:16 vertical short using FFmpeg...")
    test_clip_out = backend_dir / "tests" / "test_rendered_short.mp4"
    test_srt = backend_dir / "tests" / "test_subs.srt"
    
    first_h = highlights[0]
    generate_clip_srt(first_h["start"], first_h["end"], first_h.get("segments", []), test_srt)
    
    rendered = render_vertical_clip(
        source_video=sample_video,
        start_time=first_h["start"],
        duration=first_h["duration"],
        output_path=test_clip_out,
        subtitle_path=test_srt
    )
    assert rendered and test_clip_out.exists(), "Rendered MP4 file must exist"
    print(f"  -> Rendered clip size: {test_clip_out.stat().st_size} bytes")

    # Probe rendered clip to verify aspect ratio and streams
    clip_probe = probe_video(test_clip_out)
    print(f"  -> Rendered format: {clip_probe['width']}x{clip_probe['height']}, Duration: {clip_probe['duration']}s")
    assert clip_probe["width"] == 1080 and clip_probe["height"] == 1920, "Output must be 1080x1920 vertical format"
    assert clip_probe["has_video"] and clip_probe["has_audio"], "Output must contain synchronized audio and video"

    # 7. Test ZIP packaging
    print("[8/9] Testing ZIP archive creation...")
    test_zip_out = backend_dir / "tests" / "test_archive.zip"
    dummy_clips = [{
        "file_path": str(test_clip_out),
        "duration": first_h["duration"],
        "title": first_h["title"]
    }]
    create_project_zip("test_proj", "Sample Video", dummy_clips, test_zip_out)
    assert test_zip_out.exists(), "ZIP archive must be created"
    with zipfile.ZipFile(str(test_zip_out), "r") as zf:
        file_list = zf.namelist()
        print(f"  -> ZIP archive contains: {file_list}")
        assert len(file_list) == 1, "ZIP must contain rendered clip"
        assert file_list[0].endswith(".mp4"), "Contained file must be MP4"

    # 8. Test Database persistence
    print("[9/12] Verifying SQLite persistence and YouTube URL validator...")
    init_db()
    save_project({
        "id": "test_e2e_01",
        "title": "E2E Automated Test Project",
        "source_type": "upload",
        "duration": 45.0,
        "status": "completed",
        "stage": "completed",
        "progress": 100,
        "status_message": "All done",
        "editing_personality": "retention",
        "memes_enabled": True
    })
    save_clip({
        "id": "clip_e2e_01",
        "project_id": "test_e2e_01",
        "title": first_h["title"],
        "start_time": first_h["start"],
        "end_time": first_h["end"],
        "duration": first_h["duration"],
        "score": first_h["score"],
        "summary": "Sample highlight summary",
        "file_path": str(test_clip_out),
        "aspect_ratio": "9:16",
        "editing_personality": "retention",
        "story_structure": {"structure": "Hook -> Context -> Climax"},
        "qc_passed": True
    })

    retrieved = get_project("test_e2e_01")
    assert retrieved is not None, "Project must be retrievable from SQLite"
    assert len(retrieved["clips"]) == 1, "Clips relationship must persist"
    assert retrieved["clips"][0]["title"] == first_h["title"]
    assert retrieved["clips"][0]["editing_personality"] == "retention"

    # Test YouTube validation
    assert is_valid_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "Standard watch URL must be valid"
    assert is_valid_youtube_url("https://youtu.be/dQw4w9WgXcQ"), "Short youtu.be URL must be valid"
    assert is_valid_youtube_url("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "Shorts URL must be valid"
    assert not is_valid_youtube_url("https://example.com/not-youtube"), "Non-YouTube URL must be invalid"

    # 9. ClipForge 2.0 Story Engine across 5 Personalities
    print("[10/12] Testing ClipForge 2.0 Story Engine across all 5 Personalities...")
    from app.story_engine import build_story_timeline
    for personality in ["retention", "funny", "storytelling", "educational", "natural"]:
        tl = build_story_timeline(
            candidate=first_h,
            all_source_segments=segments,
            target_duration=20.0,
            personality=personality,
            memes_enabled=True
        )
        assert len(tl.segments) >= 1, f"Personality {personality} must generate timeline segments"
        assert tl.total_duration > 0, f"Personality {personality} must have positive duration"
        print(f"  -> Personality '{personality}': {len(tl.segments)} segments, dur={tl.total_duration:.1f}s, structure={tl.story_breakdown.get('structure')}")

    # 10. Multi-segment Timeline Composer Render with Camera Zoom & SFX
    print("[11/12] Testing Multi-Segment Timeline Composer rendering...")
    from app.timeline_composer import compose_story_clip
    retention_timeline = build_story_timeline(
        candidate=first_h,
        all_source_segments=segments,
        target_duration=20.0,
        personality="retention",
        memes_enabled=True
    )
    test_composite_mp4 = backend_dir / "tests" / "test_composite_short.mp4"
    comp_rendered = compose_story_clip(
        source_video=sample_video,
        timeline=retention_timeline,
        output_path=test_composite_mp4,
        all_source_segments=segments,
        subtitle_style="hormozi_yellow",
        subtitles_enabled=True,
        aspect_ratio="9:16",
        audio_boost=True
    )
    assert comp_rendered and test_composite_mp4.exists(), "Composite short must render successfully"
    comp_probe = probe_video(test_composite_mp4)
    print(f"  -> Composite Short rendered: {comp_probe['width']}x{comp_probe['height']}, Duration={comp_probe['duration']}s, Size={test_composite_mp4.stat().st_size} bytes")
    assert comp_probe["has_video"] and comp_probe["has_audio"], "Composite video must have synchronized A/V"

    # 11. Automated Quality Control Pass
    print("[12/12] Testing Automated Quality Control (QC) Pass...")
    from app.quality_controller import validate_clip_export
    qc_res = validate_clip_export(test_composite_mp4, retention_timeline, 20.0)
    print(f"  -> QC Result: passed={qc_res['passed']}, duration={qc_res['duration']}s, checks={qc_res['checks']}")
    assert qc_res["passed"], f"QC checks must pass on rendered short! Warnings: {qc_res['warnings']}"

    # Clean up temporary test files
    if temp_wav.exists(): temp_wav.unlink()
    if test_srt.exists(): test_srt.unlink()
    if test_zip_out.exists(): test_zip_out.unlink()
    if test_composite_mp4.exists(): test_composite_mp4.unlink()

    print("\n==========================================================================")
    print(">>> ALL 12 CLIPFORGE 2.0 END-TO-END VERIFICATION CHECKS PASSED SUCCESSFULLY! <<<")
    print("==========================================================================\n")

if __name__ == "__main__":
    run_all_tests()
