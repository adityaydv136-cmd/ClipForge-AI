from pathlib import Path
from app.ffmpeg_utils import render_vertical_clip
from app.renderer import generate_clip_subtitles

p = Path("tests")
sample = p / "sample.mp4"
ass_path = p / "test_ass.ass"
out_mp4 = p / "test_ass_out.mp4"

words_data = [
    {"start": 0.0, "end": 4.0, "words": [
        {"word": "TESTING", "start": 0.5, "end": 1.5},
        {"word": "VIRAL", "start": 1.5, "end": 2.5},
        {"word": "CAPTIONS", "start": 2.5, "end": 3.5}
    ]}
]

sub = generate_clip_subtitles(0.0, 5.0, words_data, ass_path, style="hormozi_yellow")
print("Generated sub:", sub, "exists:", ass_path.exists())

success = render_vertical_clip(
    source_video=sample,
    start_time=0.0,
    duration=5.0,
    output_path=out_mp4,
    subtitle_path=ass_path
)

print("Render result:", success, "out exists:", out_mp4.exists(), "size:", out_mp4.stat().st_size if out_mp4.exists() else 0)
