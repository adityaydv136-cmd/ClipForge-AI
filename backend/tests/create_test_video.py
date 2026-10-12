import sys
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import FFMPEG_PATH

def generate_test_video(output_mp4: Path, duration_seconds: int = 50):
    """
    Generate a synthetic test video with real spoken speech using Windows Speech Synthesizer
    and FFmpeg test video patterns.
    """
    speech_wav = output_mp4.parent / "test_speech.wav"
    
    # 1. Synthesize real speech using PowerShell System.Speech
    ps_script = f"""
    Add-Type -AssemblyName System.Speech
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SetOutputToWaveFile('{str(speech_wav).replace(chr(92), "/")}')
    $s.Speak('Welcome to ClipForge. Here is the biggest secret to getting things done. The first rule is to eliminate all distractions. What if you could double your productivity in one day? The truth is, consistency always beats temporary motivation. That is why following a simple system creates massive results. Stop overthinking and start executing right now.')
    $s.Dispose()
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)
    
    # 2. Use FFmpeg to generate 1920x1080 video with the speech audio
    ffmpeg = FFMPEG_PATH or "ffmpeg"
    cmd = [
        ffmpeg,
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration_seconds}:size=1920x1080:rate=30",
        "-i", str(speech_wav),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(output_mp4)
    ]
    subprocess.run(cmd, check=True)
    if speech_wav.exists():
        speech_wav.unlink()

    print(f"✅ Generated test video at: {output_mp4} (size: {output_mp4.stat().st_size} bytes)")
    return output_mp4

if __name__ == "__main__":
    test_dir = Path(__file__).resolve().parent
    test_dir.mkdir(exist_ok=True)
    generate_test_video(test_dir / "synthetic_sample.mp4", 45)
