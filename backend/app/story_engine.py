"""
ClipForge AI 2.0 - Story & Narrative Analysis Engine
=====================================================
Analyzes source transcript, acoustic dynamics, and scene cues to construct
mini-stories for viral short-form video (TikTok, YouTube Shorts, Reels).

Every clip follows a structured narrative arc:
  1. Hook (Cold-open payoff preview or dynamic speech hook)
  2. Context / Setup (Minimum necessary background)
  3. Buildup (Rising anticipation / tighter pacing)
  4. Smart Flashback (Optional callback to earlier context in source video)
  5. Payoff / Climax (The core punchline, reveal, or high-energy moment)
  6. Ending Beat (Natural closing or takeaway)
"""

import re
import math
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from .meme_engine import detect_meme_opportunities

@dataclass
class TimelineSegment:
    segment_type: str        # 'hook_teaser', 'setup', 'flashback', 'buildup', 'climax', 'payoff', 'resolution', 'natural'
    source_start: float      # Start time in source video
    source_end: float        # End time in source video
    duration: float          # Duration of this segment
    label: str               # e.g., "🔥 Cold Open Teaser", "Context", "[ FLASHBACK ]"
    zoom_effect: bool = False # Subtle punch-in zoom (climax)
    badge_label: Optional[str] = None # Visual badge overlay, e.g. "FLASHBACK" or "WAIT FOR IT"

@dataclass
class StoryTimeline:
    title: str
    target_duration: float
    total_duration: float
    personality: str
    hook_type: str
    segments: List[TimelineSegment] = field(default_factory=list)
    sfx_cues: List[Dict[str, Any]] = field(default_factory=list)
    story_breakdown: Dict[str, Any] = field(default_factory=dict)
    transcript_text: str = ""
    score: float = 85.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "target_duration": self.target_duration,
            "total_duration": round(self.total_duration, 2),
            "personality": self.personality,
            "hook_type": self.hook_type,
            "segments": [asdict(s) for s in self.segments],
            "sfx_cues": self.sfx_cues,
            "story_breakdown": self.story_breakdown,
            "score": round(self.score, 1)
        }

# ==============================================================================
# Narrative Cue Detectors
# ==============================================================================

CURIOSITY_QUESTIONS = [
    r"\b(why (is it that|do so many|would anyone|does nobody))\b",
    r"\b(how (to actually|i managed to|did this even|do you get))\b",
    r"\b(what (if i told you|happens when|nobody realizes|is the real))\b",
    r"\b(did you know (that|about|how)?)\b",
    r"\b(have you ever (wondered|seen|tried|thought))\b"
]

CLIMAX_INDICATORS = [
    r"\b(boom|and then|all of a sudden|suddenly|turns out|it actually worked)\b",
    r"\b(unbelievable|cannot believe|look at that|and that'?s how|we did it)\b",
    r"\b(biggest mistake|disaster|lost everything|messed up)\b",
    r"\b(insane|blew my mind|shocked|crazy)\b"
]

FLASHBACK_TRIGGERS = [
    r"\b(remember when|like i said earlier|as we saw before|back at the beginning)\b",
    r"\b(the prediction was|he said it wouldn'?t|they said it was impossible)\b",
    r"\b(earlier (we|i) thought|at first (we|i))\b"
]

def find_earlier_context_callback(
    all_segments: List[Dict[str, Any]],
    current_start: float,
    current_text: str
) -> Optional[Dict[str, Any]]:
    """
    Smart Flashback Search:
    Scans footage preceding current_start to find a relevant setup or prediction
    that makes the current payoff deeply satisfying.
    """
    if current_start < 8.0:
        return None # Too close to start of video for a callback

    current_words = set(re.findall(r"\b\w{4,}\b", current_text.lower()))
    if not current_words:
        return None

    best_match = None
    best_overlap = 0

    # Search in first 60% of video preceding current clip
    for seg in all_segments:
        seg_end = float(seg.get("end", 0))
        seg_start = float(seg.get("start", 0))
        if seg_end > (current_start - 4.0):
            break

        seg_text = seg.get("text", "").strip()
        if len(seg_text) < 15:
            continue

        seg_words = set(re.findall(r"\b\w{4,}\b", seg_text.lower()))
        overlap = len(current_words.intersection(seg_words))

        # Check for setup words
        is_setup = any(re.search(pat, seg_text, re.IGNORECASE) for pat in [
            r"\b(i think|my prediction|let'?s test|we are trying to|can we|the goal is)\b"
        ])
        if is_setup:
            overlap += 2

        if overlap > best_overlap and overlap >= 2:
            best_overlap = overlap
            best_match = {
                "start": max(0.0, seg_start),
                "end": min(seg_end, seg_start + 3.0), # keep flashback tight (max 3s)
                "text": seg_text,
                "duration": min(3.0, seg_end - seg_start)
            }

    return best_match

def build_story_timeline(
    candidate: Dict[str, Any],
    all_source_segments: List[Dict[str, Any]],
    target_duration: float = 20.0,
    personality: str = "retention",
    memes_enabled: bool = True
) -> StoryTimeline:
    """
    Converts a candidate highlight window into an expertly edited,
    multi-segment StoryTimeline tailored to the selected editing personality.
    """
    c_start = float(candidate["start"])
    c_end = float(candidate["end"])
    c_dur = c_end - c_start
    c_text = candidate.get("text", "")
    sub_segments = candidate.get("segments", [])

    # Identify narrative units within the candidate window
    # 1. Opening sentence
    # 2. Climax / peak payoff sentence
    # 3. Closing beat
    first_seg = sub_segments[0] if sub_segments else {"start": c_start, "end": c_start + 3.0, "text": ""}
    last_seg = sub_segments[-1] if sub_segments else {"start": max(c_start, c_end - 3.0), "end": c_end, "text": ""}

    # Look for climax unit
    climax_unit = None
    for s in reversed(sub_segments):
        txt = s.get("text", "")
        if any(re.search(pat, txt, re.IGNORECASE) for pat in CLIMAX_INDICATORS):
            climax_unit = s
            break
    if not climax_unit and sub_segments:
        # Default to penultimate or final segment as payoff
        climax_unit = sub_segments[-1]

    # Initialize timeline
    timeline = StoryTimeline(
        title=candidate.get("title", "Viral Short"),
        target_duration=target_duration,
        total_duration=0.0,
        personality=personality,
        hook_type=candidate.get("hook_type", "retention_hook"),
        transcript_text=c_text,
        score=float(candidate.get("score", 85.0))
    )

    # =========================================================================
    # Strategy 1: Natural (Clean cut, preserves original flow, minimal effects)
    # =========================================================================
    if personality == "natural":
        cut_duration = min(target_duration, c_dur)
        timeline.segments.append(
            TimelineSegment(
                segment_type="natural",
                source_start=c_start,
                source_end=c_start + cut_duration,
                duration=cut_duration,
                label="Original Flow"
            )
        )
        timeline.total_duration = cut_duration
        timeline.story_breakdown = {
            "structure": "Preserved Natural Flow",
            "hook": "Chronological Entry",
            "pacing": "Original Timing",
            "effects": "Clean cuts, zero intrusion"
        }
        return timeline

    # =========================================================================
    # Strategy 2: Funny / Meme-focused
    # =========================================================================
    elif personality == "funny":
        # Structure: Setup -> Build-up -> Comedic Payoff / Fail -> Freeze or SFX
        setup_dur = min(4.0, target_duration * 0.25)
        climax_dur = min(4.5, target_duration * 0.30)
        buildup_dur = max(6.0, target_duration - setup_dur - climax_dur)

        t_cur = c_start
        # 1. Setup
        timeline.segments.append(
            TimelineSegment(
                segment_type="setup",
                source_start=t_cur,
                source_end=t_cur + setup_dur,
                duration=setup_dur,
                label="Comedy Setup"
            )
        )
        t_cur += setup_dur

        # 2. Build-up / awkward progression
        timeline.segments.append(
            TimelineSegment(
                segment_type="buildup",
                source_start=t_cur,
                source_end=t_cur + buildup_dur,
                duration=buildup_dur,
                label="Anticipation & Setup",
                badge_label="WAIT FOR IT..."
            )
        )
        t_cur += buildup_dur

        # 3. Payoff
        payoff_start = max(t_cur, c_end - climax_dur)
        actual_payoff_dur = min(climax_dur, c_end - payoff_start)
        timeline.segments.append(
            TimelineSegment(
                segment_type="climax",
                source_start=payoff_start,
                source_end=payoff_start + actual_payoff_dur,
                duration=actual_payoff_dur,
                label="Punchline / Fail",
                zoom_effect=True
            )
        )

        timeline.total_duration = sum(s.duration for s in timeline.segments)

        # SFX cue at climax
        if memes_enabled:
            meme = detect_meme_opportunities(
                text=c_text,
                duration=timeline.total_duration,
                is_funny_fail=True,
                editing_personality=personality,
                memes_enabled=True
            )
            if meme and meme.get("asset"):
                cue_time = round(setup_dur + buildup_dur, 2)
                timeline.sfx_cues.append({
                    "time_offset": cue_time,
                    "sfx_path": meme["asset"]["file_path"],
                    "volume": meme["asset"].get("volume", 0.75),
                    "label": meme["label"]
                })

        timeline.story_breakdown = {
            "structure": "Setup -> Buildup -> Comedic Punchline",
            "hook": "Intriguing Comic Setup",
            "buildup": "Tension Build with 'WAIT FOR IT' cue",
            "payoff": "Climax Zoom & Reaction Impact",
            "meme_applied": bool(timeline.sfx_cues)
        }
        return timeline

    # =========================================================================
    # Strategy 3: Cinematic Storytelling (Narrative arc, callbacks, suspense)
    # =========================================================================
    elif personality == "storytelling":
        # Check if an earlier flashback/callback exists in source video
        flashback = find_earlier_context_callback(all_source_segments, c_start, c_text)
        
        fb_dur = flashback["duration"] if flashback else 0.0
        remaining_budget = target_duration - fb_dur
        setup_dur = min(5.0, remaining_budget * 0.3)
        climax_dur = min(5.5, remaining_budget * 0.35)
        build_dur = max(5.0, remaining_budget - setup_dur - climax_dur)

        # 1. Setup
        timeline.segments.append(
            TimelineSegment(
                segment_type="setup",
                source_start=c_start,
                source_end=c_start + setup_dur,
                duration=setup_dur,
                label="Narrative Setup"
            )
        )

        # 2. Flashback if available
        if flashback and fb_dur > 1.0:
            timeline.segments.append(
                TimelineSegment(
                    segment_type="flashback",
                    source_start=flashback["start"],
                    source_end=flashback["end"],
                    duration=fb_dur,
                    label="Smart Flashback",
                    badge_label="[ FLASHBACK ]"
                )
            )

        # 3. Rising Action
        mid_start = c_start + setup_dur
        timeline.segments.append(
            TimelineSegment(
                segment_type="buildup",
                source_start=mid_start,
                source_end=mid_start + build_dur,
                duration=build_dur,
                label="Rising Action"
            )
        )

        # 4. Climax & Resolution
        pay_start = max(mid_start + build_dur, c_end - climax_dur)
        pay_dur = min(climax_dur, c_end - pay_start)
        timeline.segments.append(
            TimelineSegment(
                segment_type="climax",
                source_start=pay_start,
                source_end=pay_start + pay_dur,
                duration=pay_dur,
                label="Narrative Resolution",
                zoom_effect=True
            )
        )

        timeline.total_duration = sum(s.duration for s in timeline.segments)

        # Cinematic SFX (whoosh transition into flashback or impact at climax)
        if memes_enabled:
            meme = detect_meme_opportunities(
                text=c_text,
                duration=timeline.total_duration,
                is_climax_shock=True,
                editing_personality=personality,
                memes_enabled=True
            )
            if meme and meme.get("asset"):
                timeline.sfx_cues.append({
                    "time_offset": round(setup_dur + fb_dur + build_dur, 2),
                    "sfx_path": meme["asset"]["file_path"],
                    "volume": 0.70,
                    "label": meme["label"]
                })

        timeline.story_breakdown = {
            "structure": "Setup -> " + ("[ FLASHBACK ] -> " if flashback else "") + "Rising Action -> Resolution",
            "hook": "Cinematic Scene Establisher",
            "flashback_used": bool(flashback),
            "payoff": "Climax Zoom & Emotional Resolution"
        }
        return timeline

    # =========================================================================
    # Strategy 4: Educational (Key thesis first, clear proof, key takeaway)
    # =========================================================================
    elif personality == "educational":
        thesis_dur = min(3.5, target_duration * 0.20)
        breakdown_dur = target_duration * 0.55
        takeaway_dur = target_duration - thesis_dur - breakdown_dur

        # 1. Thesis / Insight Hook
        timeline.segments.append(
            TimelineSegment(
                segment_type="hook_teaser",
                source_start=c_start,
                source_end=c_start + thesis_dur,
                duration=thesis_dur,
                label="Core Thesis Hook",
                badge_label="KEY LESSON"
            )
        )

        # 2. Breakdown / Demonstration
        t_mid = c_start + thesis_dur
        timeline.segments.append(
            TimelineSegment(
                segment_type="buildup",
                source_start=t_mid,
                source_end=t_mid + breakdown_dur,
                duration=breakdown_dur,
                label="Step-by-Step Breakdown"
            )
        )

        # 3. Takeaway Bell
        t_end = min(c_end, t_mid + breakdown_dur + takeaway_dur)
        actual_takeaway = max(1.5, t_end - (t_mid + breakdown_dur))
        timeline.segments.append(
            TimelineSegment(
                segment_type="payoff",
                source_start=t_mid + breakdown_dur,
                source_end=t_end,
                duration=actual_takeaway,
                label="Practical Takeaway",
                zoom_effect=True
            )
        )

        timeline.total_duration = sum(s.duration for s in timeline.segments)

        # Bell chime for takeaway
        if memes_enabled:
            meme = detect_meme_opportunities(
                text=c_text + " secret takeaway key rule",
                duration=timeline.total_duration,
                editing_personality=personality,
                memes_enabled=True
            )
            if meme and meme.get("asset"):
                timeline.sfx_cues.append({
                    "time_offset": round(thesis_dur + breakdown_dur, 2),
                    "sfx_path": meme["asset"]["file_path"],
                    "volume": 0.65,
                    "label": "Takeaway Chime"
                })

        timeline.story_breakdown = {
            "structure": "Thesis Hook -> Step-by-Step Proof -> Takeaway",
            "hook": "High-Value Insight Hook",
            "payoff": "Actionable Conclusion",
            "chime_sfx": bool(timeline.sfx_cues)
        }
        return timeline

    # =========================================================================
    # Strategy 5: Retention-focused (DEFAULT - Viral Shorts Editor)
    # Hook-first preview OR high-impact question -> Context -> Buildup -> Payoff
    # =========================================================================
    else: # "retention"
        cold_open = candidate.get("cold_open_snippet")
        
        # Decide if Cold Open is appropriate:
        # If a punchy climax snippet exists and video is >= 20s, tease 1.8s of the climax first!
        use_cold_open = False
        teaser_start = 0.0
        teaser_dur = 0.0

        if cold_open and cold_open.get("start") and (cold_open["start"] > c_start + 4.0):
            use_cold_open = True
            teaser_start = float(cold_open["start"])
            teaser_dur = min(1.8, float(cold_open.get("end", teaser_start + 1.8)) - teaser_start)

        remaining_budget = target_duration - teaser_dur
        setup_dur = min(4.5, remaining_budget * 0.25)
        climax_dur = min(4.5, remaining_budget * 0.28)
        buildup_dur = max(5.0, remaining_budget - setup_dur - climax_dur)

        # Act 1: Cold Open Teaser (if applicable)
        if use_cold_open:
            timeline.segments.append(
                TimelineSegment(
                    segment_type="hook_teaser",
                    source_start=teaser_start,
                    source_end=teaser_start + teaser_dur,
                    duration=teaser_dur,
                    label="🔥 Cold Open Teaser",
                    badge_label="WAIT FOR IT..."
                )
            )

        # Act 2: Context / Setup
        timeline.segments.append(
            TimelineSegment(
                segment_type="setup",
                source_start=c_start,
                source_end=c_start + setup_dur,
                duration=setup_dur,
                label="Context & Setup"
            )
        )

        # Act 3: Build-up / Rising Curiosity
        mid_start = c_start + setup_dur
        timeline.segments.append(
            TimelineSegment(
                segment_type="buildup",
                source_start=mid_start,
                source_end=mid_start + buildup_dur,
                duration=buildup_dur,
                label="Rising Tension"
            )
        )

        # Act 4: Climax & Payoff
        pay_start = max(mid_start + buildup_dur, c_end - climax_dur)
        pay_dur = min(climax_dur, c_end - pay_start)
        timeline.segments.append(
            TimelineSegment(
                segment_type="climax",
                source_start=pay_start,
                source_end=pay_start + pay_dur,
                duration=pay_dur,
                label="Climax & Reveal",
                zoom_effect=True
            )
        )

        timeline.total_duration = sum(s.duration for s in timeline.segments)

        # Impact sound effect on climax
        if memes_enabled:
            meme = detect_meme_opportunities(
                text=c_text,
                duration=timeline.total_duration,
                is_climax_shock=True,
                editing_personality="retention",
                memes_enabled=True
            )
            if meme and meme.get("asset"):
                cue_time = round(teaser_dur + setup_dur + buildup_dur, 2)
                timeline.sfx_cues.append({
                    "time_offset": cue_time,
                    "sfx_path": meme["asset"]["file_path"],
                    "volume": 0.80,
                    "label": meme["label"]
                })

        timeline.story_breakdown = {
            "structure": ("Cold-Open Teaser -> " if use_cold_open else "") + "Context -> Buildup -> Climax",
            "hook": "Payoff Teaser" if use_cold_open else candidate.get("hook_category", "Curiosity Gap"),
            "buildup": "Tighter cuts eliminating dead air",
            "payoff": "Climax Punch-in Zoom",
            "impact_sfx": bool(timeline.sfx_cues)
        }
        return timeline
