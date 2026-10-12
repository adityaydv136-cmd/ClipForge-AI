from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np

def analyze_visuals(
    video_path: Path,
    total_duration: float,
    progress_cb = None,
    max_samples: int = 25
) -> Tuple[List[float], List[Dict[str, float]]]:
    """
    Fast, single-pass visual analysis that samples up to `max_samples` frames.
    Computes both scene cut timestamps and motion energy without freezing on long videos.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return [], []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    
    # Calculate step size to sample evenly across the duration
    if total_frames > 0:
        step = max(int(fps * 2), total_frames // max_samples)
    else:
        step = max(1, int(fps * 4))

    scene_cuts: List[float] = []
    motion_scores: List[Dict[str, float]] = []
    
    prev_hist = None
    prev_gray = None
    frame_idx = 0
    sampled_count = 0

    try:
        while frame_idx < total_frames and sampled_count < max_samples:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            # Downscale frame for ultra-fast processing
            small = cv2.resize(frame, (160, 90))
            timestamp = round(frame_idx / fps, 2)

            # 1. Scene cut detection (Hue-Saturation histogram)
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
            cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

            if prev_hist is not None:
                similarity = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                if similarity < 0.45:
                    scene_cuts.append(timestamp)
            prev_hist = hist

            # 2. Motion energy detection (Grayscale frame difference)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                motion_val = float(np.mean(diff))
                motion_scores.append({
                    "time": timestamp,
                    "motion": min(1.0, motion_val / 40.0)
                })
            prev_gray = gray

            sampled_count += 1
            frame_idx += step

            if progress_cb and max_samples > 0:
                pct = sampled_count / max_samples
                progress_cb(pct, f"Analyzing visual dynamics ({sampled_count}/{max_samples})...")
    except Exception as e:
        print(f"[Warning] Visual analysis interrupted: {e}")
    finally:
        cap.release()

    return scene_cuts, motion_scores

def detect_scene_changes(video_path: Path, threshold: float = 30.0, max_samples: int = 25) -> List[float]:
    """Compatibility wrapper for scene cuts detection."""
    cuts, _ = analyze_visuals(video_path, total_duration=0.0, max_samples=max_samples)
    return cuts

def analyze_visual_energy(video_path: Path, duration: float, max_samples: int = 25) -> List[Dict[str, float]]:
    """Compatibility wrapper for motion energy analysis."""
    _, motions = analyze_visuals(video_path, total_duration=duration, max_samples=max_samples)
    return motions

