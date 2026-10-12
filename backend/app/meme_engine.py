import os
import json
import math
import struct
import wave
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import DATA_DIR

MEME_LIBRARY_DIR = DATA_DIR / "meme_library"
MEME_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
METADATA_FILE = MEME_LIBRARY_DIR / "metadata.json"

def _generate_wav(filepath: Path, duration_sec: float, sample_func) -> bool:
    """Generate high-quality 44.1kHz mono 16-bit PCM WAV file."""
    if filepath.exists() and filepath.stat().st_size > 500:
        return True
    
    sample_rate = 44100
    total_samples = int(sample_rate * duration_sec)
    
    try:
        with wave.open(str(filepath), 'wb') as wav_file:
            wav_file.setnchannels(1) # mono
            wav_file.setsampwidth(2) # 16-bit
            wav_file.setframerate(sample_rate)
            
            raw_data = bytearray()
            for i in range(total_samples):
                t = i / sample_rate
                val = sample_func(t, duration_sec)
                # Clamp -1.0 to 1.0
                clamped = max(-1.0, min(1.0, val))
                sample_int = int(clamped * 32767)
                raw_data.extend(struct.pack('<h', sample_int))
                
            wav_file.writeframes(raw_data)
        return True
    except Exception as e:
        print(f"[Warning] Failed to synthesize {filepath.name}: {e}")
        return False

def init_default_meme_assets():
    """
    Synthesize offline, royalty-free creator sound effects:
    1. Vine Boom / Dramatic Thump (sub-bass drop impact for shock & reveals)
    2. Whoosh Transition (air sweep for fast cuts and flashbacks)
    3. Record Scratch (vinyl halt for ironic reversals and fails)
    4. Crickets (rhythmic chirping for awkward pauses)
    5. Ding / Reveal Chime (crystal bell chime for insights and tips)
    """
    # 1. Vine Boom / Sub-bass Impact (1.1s)
    def vine_boom_gen(t, d):
        # decaying low-frequency sweep from 85Hz down to 35Hz with sub harmonics
        freq = 85.0 - (50.0 * (t / d))
        env = math.exp(-3.8 * t)
        sine1 = math.sin(2.0 * math.pi * freq * t)
        sub = math.sin(2.0 * math.pi * (freq * 0.5) * t) * 0.6
        # Initial punch transient
        punch = math.sin(2.0 * math.pi * 120.0 * t) * math.exp(-25.0 * t) * 0.8
        return (sine1 + sub + punch) * env * 0.95

    # 2. Whoosh / Transition Swish (0.45s)
    def whoosh_gen(t, d):
        # Bandpassed noise sweep centered at peak t=0.22
        center = d / 2.0
        env = math.exp(-((t - center) ** 2) / 0.015)
        # Pseudo-noise modulation with pitch glide
        noise = (math.sin(t * 12345.67) + math.sin(t * 54321.12) + math.sin(t * 9876.54)) / 3.0
        freq = 300.0 + 1200.0 * (t / d)
        tone = math.sin(2.0 * math.pi * freq * t) * 0.4
        return (noise * 0.7 + tone) * env * 0.85

    # 3. Record Scratch / Vinyl Stop (0.4s)
    def scratch_gen(t, d):
        freq = 2400.0 * math.exp(-14.0 * t) + 180.0
        tone = math.sin(2.0 * math.pi * freq * t)
        noise = (math.sin(t * 43219.8) + math.sin(t * 87654.3)) * 0.5
        env = math.exp(-6.5 * t)
        return (tone * 0.75 + noise * 0.25) * env * 0.85

    # 4. Awkward Crickets (1.2s)
    def crickets_gen(t, d):
        # 3 bursts of chirps at ~4500Hz
        burst_idx = int(t / 0.35)
        local_t = t - (burst_idx * 0.35)
        if local_t < 0.18:
            pulse = math.sin(2.0 * math.pi * 4500.0 * t) * math.sin(2.0 * math.pi * 65.0 * local_t)
            env = math.sin(math.pi * (local_t / 0.18))
            return pulse * env * 0.45
        return 0.0

    # 5. Ding / Bell Chime (0.8s)
    def ding_gen(t, d):
        env = math.exp(-4.2 * t)
        f1 = math.sin(2.0 * math.pi * 1760.0 * t) # A6
        f2 = math.sin(2.0 * math.pi * 3520.0 * t) * 0.4
        f3 = math.sin(2.0 * math.pi * 5280.0 * t) * 0.15
        return (f1 + f2 + f3) * env * 0.65

    assets = [
        ("vine_boom.wav", 1.1, vine_boom_gen, {
            "name": "Vine Boom / Dramatic Impact",
            "category": "shock",
            "description": "Deep sub-bass impact for shocking reveals, twists, and dramatic climaxes",
            "duration": 1.1,
            "volume": 0.85,
            "tags": ["shock", "twist", "reveal", "dramatic", "climax"]
        }),
        ("whoosh_transition.wav", 0.45, whoosh_gen, {
            "name": "Fast Whoosh Cut",
            "category": "transition",
            "description": "Clean kinetic whip-cut sound for scene switches, cold-opens, and flashbacks",
            "duration": 0.45,
            "volume": 0.65,
            "tags": ["transition", "cut", "flashback", "cold_open", "whip"]
        }),
        ("record_scratch.wav", 0.4, scratch_gen, {
            "name": "Record Scratch / Sudden Stop",
            "category": "fail",
            "description": "Sudden comedic halt for unexpected errors, awkward moments, and reversals",
            "duration": 0.4,
            "volume": 0.75,
            "tags": ["fail", "error", "reversal", "awkward", "comedy"]
        }),
        ("crickets_awkward.wav", 1.2, crickets_gen, {
            "name": "Awkward Silence Crickets",
            "category": "awkward_silence",
            "description": "Subtle comedic crickets for deadpan jokes and dead-air pauses",
            "duration": 1.2,
            "volume": 0.50,
            "tags": ["silence", "awkward", "pause", "deadpan", "humor"]
        }),
        ("ding_reveal.wav", 0.8, ding_gen, {
            "name": "Crystal Chime / Key Insight",
            "category": "insight",
            "description": "Bright crystal chime for important takeaways, tips, and triumphant reveals",
            "duration": 0.8,
            "volume": 0.60,
            "tags": ["insight", "tip", "win", "celebration", "discovery"]
        }),
    ]

    manifest = []
    for filename, dur, generator, meta in assets:
        target_path = MEME_LIBRARY_DIR / filename
        _generate_wav(target_path, dur, generator)
        meta["file_path"] = str(target_path)
        meta["filename"] = filename
        manifest.append(meta)

    # Save manifest if not exists or update
    METADATA_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

# Initialize default library on import
try:
    init_default_meme_assets()
except Exception as e:
    print(f"[Warning] Failed to initialize default meme assets: {e}")

def get_meme_library() -> List[Dict[str, Any]]:
    """Retrieve full list of active meme, reaction, and SFX assets."""
    if not METADATA_FILE.exists():
        init_default_meme_assets()
    try:
        data = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        # Verify file existence
        valid = []
        for item in data:
            if Path(item.get("file_path", "")).exists():
                valid.append(item)
        return valid
    except Exception:
        return []

def detect_meme_opportunities(
    text: str,
    duration: float,
    has_awkward_pause: bool = False,
    is_climax_shock: bool = False,
    is_funny_fail: bool = False,
    editing_personality: str = "retention",
    memes_enabled: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Contextually intelligent meme and reaction matcher.
    Checks semantic cues, speech sentiment, and editing style.
    Returns matched asset metadata and insertion treatment, or None if no meme is appropriate.
    """
    if not memes_enabled or editing_personality == "natural":
        return None

    library = get_meme_library()
    if not library:
        return None

    lower = text.lower()

    # Rule 1: Awkward silence / failed attempt
    if has_awkward_pause or any(w in lower for w in ["awkward", "crickets", "no response", "nobody said anything", "dead silence"]):
        match = next((a for a in library if a["category"] == "awkward_silence"), None)
        if match:
            return {
                "asset": match,
                "treatment": "awkward_pause_sfx",
                "label": "Awkward Silence Cue",
                "cue_time_offset": -0.2, # right as pause starts
                "confidence": 0.88
            }

    # Rule 2: Sudden reversal / mistake / comedic fail
    if is_funny_fail or any(w in lower for w in ["messed up", "terrible mistake", "huge mistake", "lost it all", "failed", "he knew", "disaster", "wrong"]):
        match = next((a for a in library if a["category"] == "fail"), None)
        if match:
            return {
                "asset": match,
                "treatment": "freeze_or_scratch",
                "label": "Ironic Reversal Cue",
                "cue_time_offset": 0.0,
                "confidence": 0.85
            }

    # Rule 3: Climax shock / dramatic reveal / insane outcome
    if is_climax_shock or any(w in lower for w in ["insane", "oh my god", "unbelievable", "boom", "cannot believe", "blew my mind", "shocked", "impossible"]):
        match = next((a for a in library if a["category"] == "shock"), None)
        if match:
            return {
                "asset": match,
                "treatment": "dramatic_punch_sfx",
                "label": "Dramatic Reveal Impact",
                "cue_time_offset": 0.0,
                "confidence": 0.92
            }

    # Rule 4: Key insight / educational takeaway / victory
    if any(w in lower for w in ["secret", "rule number", "key takeaway", "formula", "remember this", "we won", "finally did it"]):
        match = next((a for a in library if a["category"] == "insight"), None)
        if match:
            return {
                "asset": match,
                "treatment": "chime_highlight",
                "label": "Key Insight Bell",
                "cue_time_offset": 0.0,
                "confidence": 0.82
            }

    # Default: No meme (respects scene tone)
    return None
