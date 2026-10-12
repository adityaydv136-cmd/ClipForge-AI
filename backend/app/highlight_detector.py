import re
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

# ==============================================================================
# 1. Linguistic & Semantic Trigger Dictionaries
# ==============================================================================

BORING_INTRO_PATTERNS = [
    r"\b(welcome back to (my|our|the) channel)\b",
    r"\b(in this video (today|we are|i am|we're))\b",
    r"\b(before we get started|before we jump in)\b",
    r"\b(don'?t forget to (like|subscribe|hit the bell))\b",
    r"\b(subscribe to (the|my) channel)\b",
    r"\b(smash that like button)\b",
    r"\b(let me know in the comments (down below)?)\b",
    r"\b(hey guys|what'?s up guys|hello everyone and welcome)\b",
    r"\b(make sure to leave a like)\b",
]

HOOK_PATTERNS = [
    r"\b(why (is it that|do so many|would anyone|does nobody))\b",
    r"\b(how (to actually|i managed to|did this even|do you get))\b",
    r"\b(what (if i told you|happens when|nobody realizes|is the real))\b",
    r"\b(did you know (that|about|how)?)\b",
    r"\b(have you ever (wondered|seen|tried|thought))\b",
    r"\b(the (single )?(biggest|worst|deadliest|costliest) mistake)\b",
    r"\b(the secret (to|behind|formula|weapon))\b",
    r"\b(the (real )?truth (about|behind|is))\b",
    r"\b(nobody (talks about|understands|realizes|knows this))\b",
    r"\b(here'?s why (you|most people|everything|this))\b",
    r"\b(stop doing this|never do this|whatever you do don'?t)\b",
    r"\b(this (changed everything|is insane|blew my mind|makes no sense))\b",
    r"\b(watch what happens (when|if|next))\b",
    r"\b(listen to this|pay close attention|check this out)\b",
    r"\b(rule number (one|1)|the number one thing)\b",
    r"\b(can you believe|i could not believe|this is crazy)\b",
    r"\b(one simple (hack|trick|technique|method|step))\b"
]

PAYOFF_PATTERNS = [
    r"\b(and (that'?s how|that is why|boom|it actually worked))\b",
    r"\b(turns out (that|it was|we were|he was))\b",
    r"\b(the (entire )?result was)\b",
    r"\b(at the end of the day)\b",
    r"\b(and that changed (everything|my life))\b",
    r"\b(so (the moral of the story|the takeaway is|remember))\b",
    r"\b(and (we|i|they) won|and (we|i|they) lost)\b",
    r"\b(finally (it happened|we got it|it worked))\b",
    r"\b(that is the (secret|answer|key))\b",
    r"\b(and that'?s the reason why)\b"
]

STORY_SETUP_PATTERNS = [
    r"\b(so (one day|years ago|recently|back when))\b",
    r"\b(i was (talking to|working on|walking into|sitting with))\b",
    r"\b(there was this (guy|time|moment|person|situation))\b",
    r"\b(imagine (you are|if you|walking into))\b",
    r"\b(we decided to|the challenge was to|the goal was)\b",
    r"\b(it all started when)\b"
]

AWKWARD_STARTS = [
    r"^(and\b|so then\b|but then\b|because\b|also\b|like I said\b|or so\b|which means\b)",
    r"^(you know what I mean\b|as I was saying\b|anyways\b|basically though\b)"
]

HIGH_ENERGY_WORDS = {
    "insane", "crazy", "unbelievable", "impossible", "genius", "masterpiece",
    "disaster", "shocked", "secret", "mistake", "danger", "deadly", "winning",
    "clutch", "epic", "brutal", "wild", "money", "huge", "millions", "billion",
    "destroyed", "crushed", "miracle", "legendary", "gamechanger", "bizarre"
}

# ==============================================================================
# 2. Sentence & Linguistic Unit Parser
# ==============================================================================

@dataclass
class SentenceUnit:
    id: int
    text: str
    start: float
    end: float
    duration: float
    words: List[Dict[str, Any]]
    is_question: bool
    is_hook: bool
    is_payoff: bool
    is_setup: bool
    is_boring_intro: bool
    energy_score: float

def parse_sentence_units(segments: List[Dict[str, Any]]) -> List[SentenceUnit]:
    """
    Transform raw Whisper segment chunks into grammatically unified sentence units
    anchored with precise word start/end timestamps.
    """
    all_words = []
    for s in segments:
        for w in s.get("words", []):
            cleaned_word = w.get("word", "").strip()
            if cleaned_word:
                all_words.append({
                    "word": cleaned_word,
                    "start": float(w.get("start", s.get("start", 0))),
                    "end": float(w.get("end", s.get("end", 0))),
                })

    if not all_words:
        # Fallback to segments directly if no word timestamps
        units = []
        for i, s in enumerate(segments):
            txt = s.get("text", "").strip()
            if not txt:
                continue
            dur = max(0.5, float(s.get("end", 0)) - float(s.get("start", 0)))
            units.append(
                _create_sentence_unit(
                    unit_id=i,
                    text=txt,
                    start=float(s.get("start", 0)),
                    end=float(s.get("end", 0)),
                    duration=dur,
                    words=[]
                )
            )
        return units

    # Group words into clean sentences using punctuation (. ! ?) or pauses > 0.65s
    sentence_groups: List[List[Dict[str, Any]]] = []
    current_group: List[Dict[str, Any]] = []

    for idx, w in enumerate(all_words):
        current_group.append(w)
        word_str = w["word"]
        
        # Check for sentence end punctuation
        has_terminator = bool(re.search(r"[.!?]$", word_str))
        
        # Check for natural silence pause
        has_pause = False
        if idx < len(all_words) - 1:
            pause_len = all_words[idx + 1]["start"] - w["end"]
            if pause_len >= 0.65 and len(current_group) >= 4:
                has_pause = True

        if has_terminator or has_pause or len(current_group) >= 28:
            sentence_groups.append(current_group)
            current_group = []

    if current_group:
        sentence_groups.append(current_group)

    units: List[SentenceUnit] = []
    for i, grp in enumerate(sentence_groups):
        txt = " ".join(w["word"] for w in grp).strip()
        if not txt:
            continue
        start_t = grp[0]["start"]
        end_t = grp[-1]["end"]
        dur = max(0.2, end_t - start_t)
        units.append(
            _create_sentence_unit(
                unit_id=i,
                text=txt,
                start=start_t,
                end=end_t,
                duration=dur,
                words=grp
            )
        )

    return units

def _create_sentence_unit(
    unit_id: int,
    text: str,
    start: float,
    end: float,
    duration: float,
    words: List[Dict[str, Any]]
) -> SentenceUnit:
    lower = text.lower()
    
    # Question check
    is_q = "?" in text or bool(re.match(r"^(why|how|what|did you|have you|can you|is it)\b", lower))
    
    # Hook pattern check
    is_hook = any(bool(re.search(p, lower)) for p in HOOK_PATTERNS)
    
    # Payoff pattern check
    is_payoff = any(bool(re.search(p, lower)) for p in PAYOFF_PATTERNS)
    
    # Story setup check
    is_setup = any(bool(re.search(p, lower)) for p in STORY_SETUP_PATTERNS)
    
    # Boring intro check
    is_boring = any(bool(re.search(p, lower)) for p in BORING_INTRO_PATTERNS)
    
    # Energy score from speech rate and high-energy vocabulary
    word_tokens = set(re.findall(r"\b\w+\b", lower))
    energy_hits = len(word_tokens.intersection(HIGH_ENERGY_WORDS))
    speech_rate = len(word_tokens) / max(0.5, duration) # words per sec
    
    rate_score = min(1.0, speech_rate / 3.2)
    energy_score = min(1.0, 0.4 * rate_score + 0.3 * (energy_hits * 0.35) + (0.3 if "!" in text else 0.0))

    return SentenceUnit(
        id=unit_id,
        text=text,
        start=start,
        end=end,
        duration=duration,
        words=words,
        is_question=is_q,
        is_hook=is_hook,
        is_payoff=is_payoff,
        is_setup=is_setup,
        is_boring_intro=is_boring,
        energy_score=energy_score
    )

# ==============================================================================
# 3. Video Category & Genre Detection
# ==============================================================================

CATEGORY_KEYWORDS = {
    "gaming": {"game", "level", "boss", "kill", "clutch", "died", "spawn", "respawn", "health", "loot", "player", "round", "minecraft", "fortnite", "roblox", "gta", "fps"},
    "podcast": {"podcast", "interview", "guest", "episode", "perspective", "agree", "disagree", "career", "advice", "conversation", "mindset", "experience"},
    "educational": {"step", "technique", "method", "formula", "tutorial", "guide", "concept", "mistake", "rule", "learn", "understand", "study", "scientific", "data"},
    "comedy": {"funny", "joke", "prank", "hilarious", "laugh", "laughing", "bro", "lmao", "lol", "reacting", "comedy", "punchline"},
    "storytelling": {"story", "years", "remember", "suddenly", "happened", "journey", "survived", "challenge", "escaped", "adventure", "secret"}
}

def detect_video_category(full_transcript: str) -> str:
    """Classify video content category to tailor highlight scoring heuristics."""
    tokens = set(re.findall(r"\b\w+\b", full_transcript.lower()))
    scores = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        overlap = len(tokens.intersection(kws))
        scores[cat] = overlap

    best_cat, best_score = max(scores.items(), key=lambda x: x[1])
    return best_cat if best_score >= 3 else "general"

# ==============================================================================
# 3.5. Dedicated 3-Second Viral Hook & Retention Engine
# ==============================================================================

def analyze_3second_hook(
    window_units: List[SentenceUnit],
    start_time: float,
) -> Dict[str, Any]:
    """
    Dedicated 3-Second Retention Hook Engine.
    Analyzes the opening 3-second window of the candidate clip to measure viewer capture rate:
    - Curiosity gap / high-stakes question / emotional intrigue
    - Spoken cadence and vocal velocity (ideal: 2.2 - 3.8 words/sec)
    - Absence of dead air silence / hesitation
    - High-energy vocabulary density
    Returns hook classification, 3s retention prediction (percentage), and score modifier.
    """
    first_3s_words = []
    first_word_time = None
    
    for u in window_units:
        for w in u.words:
            w_start = float(w.get("start", u.start))
            if first_word_time is None:
                first_word_time = w_start
            if w_start <= start_time + 3.2:
                first_3s_words.append(w.get("word", "").strip().lower())
    
    if not first_3s_words and window_units:
        # Fallback to first unit text
        first_3s_words = re.findall(r"\b\w+\b", window_units[0].text.lower())[:8]
        first_word_time = window_units[0].start

    opener_text = " ".join(first_3s_words)
    first_unit = window_units[0] if window_units else None
    
    # 1. Dead air analysis
    dead_air_silence = max(0.0, (first_word_time - start_time)) if first_word_time is not None else 0.0
    
    # 2. Hook pattern match
    has_curiosity = any(bool(re.search(p, opener_text)) for p in HOOK_PATTERNS)
    is_question = bool(first_unit and (first_unit.is_question or "?" in first_unit.text[:40]))
    has_high_energy = any(w in opener_text for w in HIGH_ENERGY_WORDS)
    has_story_setup = any(bool(re.search(p, opener_text)) for p in STORY_SETUP_PATTERNS)
    
    # 3. Velocity (words in 3s)
    word_count = len(first_3s_words)
    if 6 <= word_count <= 11:
        velocity_score = 1.0  # Perfect punchy pacing
    elif 4 <= word_count < 6:
        velocity_score = 0.7  # Slightly slow
    elif word_count > 11:
        velocity_score = 0.8  # Rapid fire
    else:
        velocity_score = 0.4  # Too few words / slow opening
        
    # Determine Hook Classification
    if is_question:
        hook_category = "Intrigue Question"
        hook_tag = "❓ Question Trap"
        base_retention = 95.0
    elif has_curiosity:
        hook_category = "Curiosity Gap"
        hook_tag = "🔥 Curiosity Gap"
        base_retention = 96.5
    elif any(w in opener_text for w in ["insane", "crazy", "shocked", "impossible", "disaster"]):
        hook_category = "Shock Value"
        hook_tag = "⚡ Shock Value"
        base_retention = 94.0
    elif any(w in opener_text for w in ["secret", "mistake", "truth", "never", "stop", "rule"]):
        hook_category = "High Stakes"
        hook_tag = "🎯 High Stakes"
        base_retention = 97.0
    elif has_story_setup:
        hook_category = "Story Teaser"
        hook_tag = "📖 Story Teaser"
        base_retention = 91.0
    else:
        hook_category = "Vocal Hook"
        hook_tag = "🚀 Vocal Energy"
        base_retention = 88.0

    # Adjust predicted retention percentage based on velocity and dead air
    retention_pct = base_retention * (0.85 + 0.15 * velocity_score)
    if dead_air_silence > 0.4:
        retention_pct -= 5.0
    if dead_air_silence <= 0.15:
        retention_pct += 2.0
    if has_high_energy:
        retention_pct += 2.0

    retention_pct = max(75.0, min(99.0, round(retention_pct, 1)))
    score_boost = (retention_pct - 85.0) * 0.6  # Up to +8.4 boost for top hooks

    return {
        "hook_tag": hook_tag,
        "hook_category": hook_category,
        "retention_3s_pct": retention_pct,
        "dead_air": round(dead_air_silence, 2),
        "score_boost": round(score_boost, 1),
        "opener_text": opener_text
    }

# ==============================================================================
# 4. Content-Based Multi-Signal Highlight Scoring
# ==============================================================================

def score_candidate_moment(
    sentences: List[SentenceUnit],
    start_time: float,
    end_time: float,
    category: str,
    editing_style: str = "balanced",
    motion_scores: Optional[List[Dict[str, float]]] = None
) -> Tuple[float, Dict[str, float], str]:
    """
    Score candidate according to the exact prompt specifications:
    - Interest and entertainment value: 25%
    - Strength of opening hook: 20%
    - Completeness and understandable context: 20%
    - Payoff, surprise, or emotional impact: 15%
    - Useful information or storytelling value: 10%
    - Visual and audio engagement: 10%
    With explicit deductions for boring intros, long silences, awkward cuts.
    """
    if not sentences:
        return 0.0, {}, "Empty candidate"

    first_s = sentences[0]
    last_s = sentences[-1]
    candidate_dur = end_time - start_time
    full_text = " ".join(s.text for s in sentences)
    lower_full = full_text.lower()
    first_lower = first_s.text.lower()

    # --------------------------------------------------------------------------
    # Signal 1: Interest and entertainment value (25%)
    # --------------------------------------------------------------------------
    avg_energy = sum(s.energy_score for s in sentences) / len(sentences)
    has_exclamation = any("!" in s.text for s in sentences)
    energy_words_count = sum(1 for s in sentences if any(w in s.text.lower() for w in HIGH_ENERGY_WORDS))
    
    interest_score = min(1.0, 0.4 * avg_energy + 0.3 * (energy_words_count * 0.25) + (0.2 if has_exclamation else 0.0) + 0.2)

    # --------------------------------------------------------------------------
    # Signal 2: Strength of opening hook (20%)
    # --------------------------------------------------------------------------
    hook_score = 0.2 # base
    if first_s.is_question:
        hook_score += 0.40
    if first_s.is_hook:
        hook_score += 0.45
    elif any(bool(re.search(p, first_lower)) for p in HOOK_PATTERNS):
        hook_score += 0.35

    if any(w in first_lower for w in ["secret", "mistake", "truth", "insane", "never", "why"]):
        hook_score += 0.20

    hook_score = min(1.0, hook_score)

    # --------------------------------------------------------------------------
    # Signal 3: Completeness and understandable context (20%)
    # --------------------------------------------------------------------------
    completeness_score = 0.5
    # Does it start cleanly?
    if re.match(r"^[A-Z0-9\"'(\[]", first_s.text.strip()):
        completeness_score += 0.20
    # Does it end cleanly with proper sentence terminator?
    if re.search(r"[.!?][\"')\]]?$", last_s.text.strip()):
        completeness_score += 0.30
    elif re.search(r"[,;...]$", last_s.text.strip()):
        completeness_score -= 0.35 # Penalize abrupt grammatical cutoff

    completeness_score = max(0.1, min(1.0, completeness_score))

    # --------------------------------------------------------------------------
    # Signal 4: Payoff, surprise, or emotional impact (15%)
    # --------------------------------------------------------------------------
    payoff_score = 0.2
    # Check if second half contains payoff, revelation, or conclusion
    second_half_sentences = sentences[len(sentences)//2:]
    has_payoff_unit = any(s.is_payoff for s in second_half_sentences)
    has_payoff_regex = any(bool(re.search(p, lower_full)) for p in PAYOFF_PATTERNS)
    
    if has_payoff_unit or has_payoff_regex:
        payoff_score += 0.55
    if any(s.energy_score > 0.6 for s in second_half_sentences):
        payoff_score += 0.25

    payoff_score = min(1.0, payoff_score)

    # --------------------------------------------------------------------------
    # Signal 5: Useful information or storytelling value (10%)
    # --------------------------------------------------------------------------
    value_score = 0.3
    if any(s.is_setup for s in sentences[:2]):
        value_score += 0.30
    if any(bool(re.search(r"\b(because|the reason|step|formula|tip|lesson|takeaway)\b", lower_full)) for p in [1]):
        value_score += 0.40

    value_score = min(1.0, value_score)

    # --------------------------------------------------------------------------
    # Signal 6: Visual & audio engagement (10%)
    # --------------------------------------------------------------------------
    visual_score = 0.3
    if motion_scores:
        relevant_motion = [m["motion"] for m in motion_scores if start_time <= m["time"] <= end_time]
        if relevant_motion:
            visual_score = sum(relevant_motion) / len(relevant_motion)
            visual_score = min(1.0, visual_score * 1.5)

    # Adapt weights based on user editing style
    if editing_style == "fast_paced":
        w_interest, w_hook, w_comp, w_payoff, w_val, w_vis = 0.30, 0.25, 0.15, 0.15, 0.05, 0.10
    elif editing_style == "storytelling":
        w_interest, w_hook, w_comp, w_payoff, w_val, w_vis = 0.20, 0.15, 0.25, 0.20, 0.15, 0.05
    elif editing_style == "funny_reaction":
        w_interest, w_hook, w_comp, w_payoff, w_val, w_vis = 0.35, 0.15, 0.15, 0.25, 0.05, 0.05
    elif editing_style == "educational":
        w_interest, w_hook, w_comp, w_payoff, w_val, w_vis = 0.15, 0.20, 0.20, 0.15, 0.25, 0.05
    else: # balanced (prompt baseline weights)
        w_interest, w_hook, w_comp, w_payoff, w_val, w_vis = 0.25, 0.20, 0.20, 0.15, 0.10, 0.10

    raw_composite = (
        (w_interest * interest_score) +
        (w_hook * hook_score) +
        (w_comp * completeness_score) +
        (w_payoff * payoff_score) +
        (w_val * value_score) +
        (w_vis * visual_score)
    ) * 100.0

    # --------------------------------------------------------------------------
    # Explicit Penalties
    # --------------------------------------------------------------------------
    penalty = 0.0
    reasons = []

    # Penalty 1: Boring intro (welcome back, don't forget to like, etc.)
    if first_s.is_boring_intro or any(bool(re.search(p, first_lower)) for p in BORING_INTRO_PATTERNS):
        penalty += 35.0
        reasons.append("Boring channel intro deduction (-35)")

    # Penalty 2: Awkward grammatical start
    if any(bool(re.search(p, first_lower)) for p in AWKWARD_STARTS):
        penalty += 20.0
        reasons.append("Awkward opening conjunction (-20)")

    # Penalty 3: Missing context / trailing sentence end
    if not re.search(r"[.!?][\"')\]]?$", last_s.text.strip()):
        penalty += 25.0
        reasons.append("Cutoff ending sentence (-25)")

    # Penalty 4: Repetitive filler word density
    words_list = re.findall(r"\b\w+\b", lower_full)
    if words_list:
        filler_count = sum(1 for w in words_list if w in ["like", "um", "uh", "you know", "basically", "so"])
        if filler_count / len(words_list) > 0.18:
            penalty += 15.0
            reasons.append("Excessive filler repetition (-15)")

    final_score = max(5.0, min(99.0, round(raw_composite - penalty, 1)))
    
    breakdown = {
        "interest": round(interest_score * 100, 1),
        "hook": round(hook_score * 100, 1),
        "completeness": round(completeness_score * 100, 1),
        "payoff": round(payoff_score * 100, 1),
        "value": round(value_score * 100, 1),
        "visual": round(visual_score * 100, 1),
        "penalty": round(penalty, 1)
    }

    explanation = "; ".join(reasons) if reasons else "High-retention story unit"
    return final_score, breakdown, explanation

# ==============================================================================
# 5. Narrative Title Generator
# ==============================================================================

def generate_clip_title(text: str, fallback_index: int) -> str:
    """Generate concise, punchy title summarizing the hook."""
    clean = re.sub(r"^(and\b|so\b|but\b|well\b|you know\b|um\b|uh\b)\s*", "", text, flags=re.IGNORECASE).strip()
    # Split at punctuation
    sentences = re.split(r"[.!?\n]", clean)
    primary = sentences[0].strip() if sentences else clean
    
    # Trim to short punchy length
    if len(primary) > 45:
        primary = primary[:42].strip() + "..."
    elif len(primary) < 5:
        primary = f"Viral Moment #{fallback_index}"

    return primary[0].upper() + primary[1:]

# ==============================================================================
# 6. Event-First Highlight Selection Engine
# ==============================================================================

def find_best_highlights(
    segments: List[Dict[str, Any]],
    total_duration: float,
    target_durations: List[float],
    max_clips: int = 3,
    editing_style: str = "balanced",
    hook_style: str = "best_moment_first",
    scene_cuts: Optional[List[float]] = None,
    motion_scores: Optional[List[Dict[str, float]]] = None
) -> List[Dict[str, Any]]:
    """
    Intelligent highlight selection engine:
    1. Parses transcript into grammatical SentenceUnits.
    2. Identifies anchor events (hooks, punchlines, Q&A, insights, action peaks).
    3. Resolves natural story boundaries with configurable tolerance (preferring a complete
       22s story over a truncated 20s fragment).
    4. Applies hook-first cold open editing when appropriate.
    5. Deduplicates candidates semantically and temporally.
    """
    scene_cuts = scene_cuts or []
    
    if not segments:
        return generate_visual_fallback_clips(total_duration, target_durations, max_clips, motion_scores)

    sentence_units = parse_sentence_units(segments)
    if not sentence_units:
        return generate_visual_fallback_clips(total_duration, target_durations, max_clips, motion_scores)

    full_transcript = " ".join(s.text for s in sentence_units)
    category = detect_video_category(full_transcript)

    candidates: List[Dict[str, Any]] = []

    # Iterate through target durations (e.g. 20.0s, 30.0s)
    for target_dur in target_durations:
        # Configurable tolerance: allow flexible boundary expansion to finish complete thought
        tolerance = 4.5
        min_dur = max(12.0, target_dur - tolerance)
        max_dur = min(total_duration, target_dur + tolerance)

        # Identify candidate start sentences
        for i, start_unit in enumerate(sentence_units):
            # Skip boring intros from ever becoming clip beginnings
            if start_unit.is_boring_intro:
                continue

            # Snap start to nearby scene cut if within 0.7 seconds
            start_time = start_unit.start
            for cut in scene_cuts:
                if abs(cut - start_time) <= 0.7:
                    start_time = cut
                    break

            # Snap start to eliminate opening silence so speech hits within 0.08s
            if start_unit.words:
                first_w_start = start_unit.words[0]["start"]
                if start_time < first_w_start - 0.12:
                    start_time = max(0.0, first_w_start - 0.06)

            # Search forward for a matching sentence ending that completes a story
            for j in range(i, len(sentence_units)):
                end_unit = sentence_units[j]
                candidate_dur = end_unit.end - start_time

                if candidate_dur < min_dur:
                    continue
                if candidate_dur > max_dur:
                    break

                window_units = sentence_units[i:j + 1]
                word_count = sum(len(u.text.split()) for u in window_units)

                # Minimum words requirement to prevent dead air clips
                if word_count < 18:
                    continue

                # Calculate multi-signal score
                score, breakdown, explanation = score_candidate_moment(
                    sentences=window_units,
                    start_time=start_time,
                    end_time=end_unit.end,
                    category=category,
                    editing_style=editing_style,
                    motion_scores=motion_scores
                )

                # Dedicated 3-Second Viral Hook & Retention Analysis
                hook_3s = analyze_3second_hook(window_units, start_time)
                score = min(99.0, round(score + hook_3s["score_boost"], 1))

                # Check for Hook-First (Cold Open) editing suitability
                cold_open_snippet = None
                clip_hook_type = hook_3s["hook_category"]

                if hook_style == "best_moment_first":
                    # Check if there is an explosive payoff/punchline sentence in the 2nd half
                    second_half = window_units[len(window_units)//2:]
                    peak_payoff = next((u for u in second_half if u.is_payoff or u.is_hook or u.energy_score > 0.7), None)
                    
                    if peak_payoff and peak_payoff.duration >= 1.2:
                        clip_hook_type = "Cold Open"
                        cold_open_snippet = {
                            "start": peak_payoff.start,
                            "end": min(peak_payoff.start + 2.2, peak_payoff.end),
                            "text": peak_payoff.text
                        }
                        # Cold open provides hook bonus
                        score = min(99.0, score + 4.0)
                    elif start_unit.is_hook or start_unit.is_question:
                        clip_hook_type = hook_3s["hook_category"]
                elif hook_style == "strongest_opening":
                    if start_unit.is_hook or start_unit.is_question:
                        score = min(99.0, score + 3.0)

                # Build segments mapping for subtitle generator
                raw_segments = []
                for u in window_units:
                    raw_segments.append({
                        "start": u.start,
                        "end": u.end,
                        "text": u.text,
                        "words": u.words
                    })

                title = generate_clip_title(window_units[0].text, len(candidates) + 1)

                candidates.append({
                    "start": round(start_time, 2),
                    "end": round(end_unit.end, 2),
                    "duration": round(candidate_dur, 2),
                    "target_duration": target_dur,
                    "score": score,
                    "breakdown": breakdown,
                    "explanation": explanation,
                    "text": " ".join(u.text for u in window_units),
                    "title": title,
                    "hook_type": clip_hook_type,
                    "hook_tag": hook_3s["hook_tag"],
                    "hook_category": hook_3s["hook_category"],
                    "retention_3s_pct": hook_3s["retention_3s_pct"],
                    "cold_open_snippet": cold_open_snippet,
                    "category": category,
                    "segments": raw_segments,
                    "word_tokens": set(re.findall(r"\b\w+\b", " ".join(u.text for u in window_units).lower()))
                })

    # Sort candidates by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # ==========================================================================
    # 7. Semantic and Temporal Non-Maximum Suppression (Deduplication)
    # ==========================================================================
    selected_clips: List[Dict[str, Any]] = []

    for cand in candidates:
        if len(selected_clips) >= max_clips:
            break

        is_duplicate = False
        for sel in selected_clips:
            # 1. Temporal overlap check
            overlap_start = max(cand["start"], sel["start"])
            overlap_end = min(cand["end"], sel["end"])
            overlap_len = max(0.0, overlap_end - overlap_start)
            
            if overlap_len > 3.5:
                is_duplicate = True
                break

            # 2. Semantic vocabulary Jaccard similarity check
            shared_words = cand["word_tokens"].intersection(sel["word_tokens"])
            union_words = cand["word_tokens"].union(sel["word_tokens"])
            if union_words:
                similarity = len(shared_words) / len(union_words)
                if similarity > 0.40:
                    is_duplicate = True
                    break

        if not is_duplicate:
            selected_clips.append(cand)

    # Sort final selected clips chronologically for intuitive playback
    selected_clips.sort(key=lambda x: x["start"])
    return selected_clips

# ==============================================================================
# 8. Visual Fallback Generator (Non-Speech Footage)
# ==============================================================================

def generate_visual_fallback_clips(
    total_duration: float,
    target_durations: List[float],
    max_clips: int,
    motion_scores: Optional[List[Dict[str, float]]] = None
) -> List[Dict[str, Any]]:
    """Produce distributed clips when video has no detectable speech."""
    clips = []
    dur = target_durations[0] if target_durations else 20.0
    usable_time = max(0.0, total_duration - dur)
    
    step = usable_time / max(1, max_clips)
    for i in range(max_clips):
        start = round(i * step, 2)
        end = min(total_duration, round(start + dur, 2))
        clips.append({
            "start": start,
            "end": end,
            "duration": round(end - start, 2),
            "target_duration": dur,
            "score": round(78.0 - (i * 2.5), 1),
            "breakdown": {"visual": 80.0},
            "explanation": "High visual motion highlight",
            "text": "Action and visual highlight sequence",
            "title": f"Action Highlight #{i+1}",
            "hook_type": "chronological",
            "cold_open_snippet": None,
            "category": "visual_action",
            "segments": []
        })
    return clips
