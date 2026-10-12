# ClipForge — AI Video-To-Shorts Web Application

[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/adityaydv136-cmd/ClipForge-AI)
[![GitHub Repository](https://img.shields.io/badge/GitHub-ClipForge--AI-8b5cf6?logo=github)](https://github.com/adityaydv136-cmd/ClipForge-AI)

> **Turn Long Videos Into Viral Shorts.**  
> Find the best moments automatically. Hook viewers in the first 3 seconds. Generate vertical 9:16 shorts with subtitles. Preview, edit, and download instantly.  
> **100% Free & Open-Source — Zero Paid AI API Keys Required.**

---

## ⚡ Architecture Overview

ClipForge is architected into 4 clean, decoupled layers:

```
┌────────────────────────────────────────────────────────┐
│                   Next.js 16 Frontend                  │
│       (Dark charcoal UI, purple accents, SSE live)     │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP & Server-Sent Events
┌───────────────────────────▼────────────────────────────┐
│                  FastAPI Backend API                   │
│   (Project management, uploads, metadata, streaming)   │
└─────────────┬───────────────────────────┬──────────────┘
              │                           │
┌─────────────▼───────────────┐ ┌─────────▼──────────────┐
│    Video-Processing Worker   │ │      Local Storage     │
│ - yt-dlp (Authorized media) │ │ - SQLite DB            │
│ - FFmpeg (Cuts & 9:16 crop) │ │ - Audio / MP4 shorts   │
│ - faster-whisper (Speech)   │ │ - Project ZIP files    │
│ - OpenCV (Scene cuts)       │ └────────────────────────┘
└─────────────────────────────┘
```

---

## 🚀 Key Features

1. **Simple, Minimalist Interface**:
   - Clean dark charcoal background (`#090a0f`), subtle purple neon accents (`#8b5cf6`), rounded cards.
   - Header with ClipForge logo, "My Clips" drawer, and Settings modal.
   - Large input field with instant paste button.
   - Direct video file upload dropzone for creator-owned footage.
   - Selectors for **20 seconds**, **30 seconds**, or **Both**.
   - Clip count selection (**3**, **5**, **10**, or **Auto**).
   - "Add subtitles" toggle switch with viral preset styles.

2. **3-Second Viral Hook & Retention Engine**:
   - **First-3-Seconds Analysis**: Scans the crucial 3-second opening window for curiosity gaps, shock triggers, questions, and high vocal velocity.
   - **Opening Silence Elimination**: Snaps the clip start timestamp directly to the exact millisecond speech begins (within 0.06s), eliminating awkward silence and immediately hooking viewers before they scroll.
   - **Predicted 3s Retention Badges**: Displays hook classifications (`🔥 Curiosity Gap`, `⚡ Shock Value`, `❓ Question Trap`, `🎯 High Stakes`) and retention rate predictions (e.g. 96% 3s Hook).

3. **In-App Clip Editor & Refinement Suite**:
   - **Interactive Trimmer**: Adjust start and end times with instant -1s / +1s micro-buttons or precision sliders.
   - **Multi-Aspect Ratio Framing**: Export in **9:16 Vertical** (Shorts/Reels/TikTok), **1:1 Square** (Feed), or **16:9 Landscape** (Highlights).
   - **Audio Loudness & Vocal Clarity EQ**: Professional EBU R128 loudness normalization and volume booster via FFmpeg so mobile dialogue pops.
   - **Caption Customization**: Choose between Viral Gold (Hormozi), Cyber Lime, Electric Cyan, Sunset Flame, and Neon Pink with dynamic positioning (Bottom safe zone, Center hero focus, Top banner) and font sizing.
   - **Instant Re-rendering**: Re-render individual clips on the fly and immediately preview them in the browser.

4. **Automated Highlight Detection (Zero-Cost Local AI)**:
   - **Local Speech Transcription**: Uses `faster-whisper` (`base` model quantized to `int8`) for rapid, accurate CPU/GPU speech-to-text with word-level timestamps.
   - **Hook & Retention Scoring**: Analyzes opening sentences for hook triggers, intrigue, questions, emotional resonance, and thought completeness.
   - **Visual Scene Cuts**: Uses OpenCV color histogram correlation to identify scene cuts and avoid awkward transitions mid-cut.
   - **Thought Boundary Snapping**: Clips snap to full sentences, avoiding dangling conjunctions ("and so...", "but...").
   - **Non-Maximum Suppression (NMS)**: Eliminates duplicate or heavily overlapping clips.

3. **Real Shorts Rendering (FFmpeg)**:
   - Real **9:16 vertical MP4** (1080×1920) H.264 video with AAC audio.
   - Intelligent centered fill crop.
   - Burned-in, high-contrast, safe-margin subtitles generated dynamically from speech timestamps.
   - Real HTML5 preview player with streaming HTTP 206 Partial Content range requests.

4. **Live Real-Time Progress**:
   - Connected directly to backend via **Server-Sent Events (SSE)**.
   - Distinct real processing stages:
     1. `Checking source`
     2. `Extracting audio`
     3. `Transcribing speech`
     4. `Analyzing highlights`
     5. `Rendering shorts`
     6. `Preparing downloads`
   - Clips stream to the UI **immediately** as each short is finished rendering!

5. **Downloads & Persistence**:
   - Individual MP4 downloads on every clip card.
   - **Download All (ZIP)** archive containing all generated shorts.
   - Local SQLite database persists projects across page reloads.

---

## 🛠️ Environment Prerequisites

- **Python**: 3.10+ (tested and verified on Python 3.14 / 3.12 / 3.11).
- **FFmpeg & FFprobe**: Version 6.0+ (Installed via WinGet or in PATH).
- **Node.js**: v18+ or v20+.

---

## 💻 Local Quick Start

### 1. One-Click Launch (Windows)
Double-click `start_clipforge.bat` in the project root.

### 2. Manual Start

#### Backend:
```bash
cd backend
# Create virtual environment (if not already created)
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# Start FastAPI server
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Frontend:
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your web browser.

---

## 🧪 Automated End-to-End Verification

A comprehensive automated test suite is included in `backend/tests/test_end_to_end.py`. It runs 9 verification checks:
1. Environment & FFmpeg binary detection
2. Video stream probing
3. Audio extraction to 16kHz WAV
4. Speech transcription with `faster-whisper`
5. Visual scene cuts & motion analysis with OpenCV
6. AI highlight detection & multi-signal scoring
7. 9:16 vertical short rendering with subtitles
8. ZIP archive packaging and inspection
9. SQLite persistence and YouTube URL validator

To execute tests:
```bash
cd backend
.\.venv\Scripts\python tests/test_end_to_end.py
```

---

## 🌐 Production & Online Deployment Guide

### Deployment Topology
Do not attempt to run heavy video processing on lightweight serverless functions (e.g. AWS Lambda or Vercel serverless) because video encoding and speech models exceed function timeouts and memory limits.

| Component | Recommended Host | Minimum Resources | Notes |
| :--- | :--- | :--- | :--- |
| **Frontend** | Vercel, Netlify, or Cloudflare Pages | Standard (Free tier works) | Point `API_BASE` environment variable to backend domain |
| **Backend & Worker** | Railway, Render, DigitalOcean Droplet, AWS EC2 | 2 vCPU, 4GB RAM, 25GB SSD | Needs system FFmpeg package installed (`apt-get install -y ffmpeg`) |
| **Storage** | Local disk or AWS S3 / Cloudflare R2 | 10–50 GB | Automatic cleanup recommended for temp files older than 24 hours |

---

## 📜 Legal & Platform Terms Notice

ClipForge respects copyright laws and platform terms:
- For YouTube links, yt-dlp accesses publicly available streams without bypassing DRM, authentication walls, or membership controls.
- For private, age-restricted, or DRM-protected sources, ClipForge displays:
  *"This video cannot be processed directly. Upload a video file you own or have permission to use."*
- Always ensure you have the necessary distribution rights for any media processed.
