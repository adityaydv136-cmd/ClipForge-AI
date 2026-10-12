import os
import io
from pathlib import Path
from typing import List, Dict, Any, Optional
import av
import numpy as np
import faster_whisper.audio
from faster_whisper import WhisperModel
from .config import DEFAULT_WHISPER_MODEL

# Compatibility patch for PyAV 14+ / 19+ (where metadata_errors argument was removed)
def _compatible_decode_audio(input_file, sampling_rate=16000, split_stereo=False):
    resampler = av.audio.resampler.AudioResampler(
        format="s16",
        layout="mono" if not split_stereo else "stereo",
        rate=sampling_rate,
    )
    raw_buffer = io.BytesIO()
    dtype = None
    try:
        container = av.open(input_file, mode="r")
    except TypeError:
        container = av.open(input_file, mode="r", metadata_errors="ignore")

    with container:
        frames = container.decode(audio=0)
        frames = faster_whisper.audio._ignore_invalid_frames(frames)
        frames = faster_whisper.audio._group_frames(frames, 500000)
        frames = faster_whisper.audio._resample_frames(frames, resampler)
        for frame in frames:
            array = frame.to_ndarray()
            dtype = array.dtype
            raw_buffer.write(array)

    audio = np.frombuffer(raw_buffer.getbuffer(), dtype=dtype)
    audio = audio.astype(np.float32) / 32768.0
    if split_stereo:
        audio = audio.reshape(-1, 2)
        return audio[:, 0], audio[:, 1]
    return audio

faster_whisper.audio.decode_audio = _compatible_decode_audio
try:
    import faster_whisper.transcribe
    faster_whisper.transcribe.decode_audio = _compatible_decode_audio
except Exception:
    pass

# Global model cache to avoid re-initializing weights per job
_CACHED_MODEL: Optional[WhisperModel] = None
_CACHED_MODEL_SIZE: Optional[str] = None

def get_whisper_model(model_size: str = DEFAULT_WHISPER_MODEL) -> WhisperModel:
    global _CACHED_MODEL, _CACHED_MODEL_SIZE
    if _CACHED_MODEL is None or _CACHED_MODEL_SIZE != model_size:
        # Uses CPU with int8 quantization for ultra-fast, lightweight inference without GPU requirement
        _CACHED_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=4)
        _CACHED_MODEL_SIZE = model_size
    return _CACHED_MODEL

def transcribe_audio(
    audio_path: Path,
    model_size: str = DEFAULT_WHISPER_MODEL,
    progress_callback: Optional[callable] = None
) -> List[Dict[str, Any]]:
    """
    Transcribe speech using faster-whisper.
    Returns structured list of segments with word-level timestamps:
    [
      {
        "id": 0,
        "start": 0.5,
        "end": 4.2,
        "text": "Here is the biggest secret to getting things done.",
        "words": [{"word": "Here", "start": 0.5, "end": 0.8}, ...]
      }
    ]
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = get_whisper_model(model_size)
    if progress_callback:
        progress_callback(5.0, "Loading speech model and analyzing audio streams...")

    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        word_timestamps=True,
        vad_filter=True, # Voice Activity Detection filter
        vad_parameters=dict(min_silence_duration_ms=500)
    )

    total_duration = info.duration or 1.0
    parsed_segments = []

    for i, seg in enumerate(segments):
        words = []
        if seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": round(w.probability, 3)
                })

        parsed_segments.append({
            "id": i,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": words
        })

        if progress_callback and total_duration > 0:
            current_pct = min(95.0, (seg.end / total_duration) * 90.0 + 5.0)
            progress_callback(current_pct, f"Transcribing audio ({int(seg.end)}s / {int(total_duration)}s)...")

    return parsed_segments
