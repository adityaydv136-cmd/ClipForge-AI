"use client";

import React, { useState, useEffect, useRef } from "react";

const API_BASE = "http://127.0.0.1:8000";

interface VideoMeta {
  title: string;
  duration: number;
  thumbnail_url?: string;
  author?: string;
}

interface Clip {
  id: string;
  project_id: string;
  title: string;
  start_time: number;
  end_time: number;
  duration: number;
  score: number;
  summary: string;
  file_path: string;
  thumbnail_path?: string;
  aspect_ratio: string;
  hook_tag?: string;
  hook_category?: string;
  retention_3s?: number;
  created_at: string;
}

interface Project {
  id: string;
  title: string;
  source_url?: string;
  source_type: string;
  thumbnail_url?: string;
  duration: number;
  status: string;
  stage: string;
  progress: number;
  status_message: string;
  duration_option: string;
  num_clips_option: string;
  subtitles_enabled: boolean;
  subtitle_style?: string;
  zip_path?: string;
  clips?: Clip[];
  created_at: string;
}

const SUBTITLE_PRESETS = [
  {
    id: "hormozi_yellow",
    name: "Viral Gold",
    creator: "Hormozi / MrBeast",
    color: "#FFE81F",
    sample: "SECRET",
  },
  {
    id: "neon_green",
    name: "Cyber Lime",
    creator: "High Energy",
    color: "#22C55E",
    sample: "ENERGY",
  },
  {
    id: "electric_cyan",
    name: "Electric Cyan",
    creator: "Tech & Modern",
    color: "#00E5FF",
    sample: "MODERN",
  },
  {
    id: "sunset_orange",
    name: "Sunset Flame",
    creator: "Storytelling",
    color: "#FF6D00",
    sample: "BOLD",
  },
  {
    id: "pink_fuchsia",
    name: "Neon Pink",
    creator: "Pop & Lifestyle",
    color: "#EA00FF",
    sample: "PUNCHY",
  },
];

const STAGE_LABELS: Record<string, string> = {
  checking_source: "Checking source",
  extracting_audio: "Extracting audio",
  transcribing_speech: "Transcribing speech",
  analyzing_highlights: "Analyzing highlights",
  rendering_shorts: "Rendering shorts",
  preparing_downloads: "Preparing downloads",
  completed: "Ready",
  failed: "Failed",
  cancelled: "Cancelled",
};

const STAGES_ORDER = [
  "checking_source",
  "extracting_audio",
  "transcribing_speech",
  "analyzing_highlights",
  "rendering_shorts",
  "preparing_downloads",
];

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export default function ClipForgeApp() {
  // Input state
  const [activeTab, setActiveTab] = useState<"url" | "upload">("url");
  const [inputUrl, setInputUrl] = useState("");
  const [videoMeta, setVideoMeta] = useState<VideoMeta | null>(null);
  const [isResolvingMeta, setIsResolvingMeta] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);

  // Configuration options
  const [durationOption, setDurationOption] = useState<"20" | "30" | "both">("20");
  const [numClipsOption, setNumClipsOption] = useState<"3" | "5" | "10" | "auto">("3");
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(true);
  const [subtitleStyle, setSubtitleStyle] = useState<string>("hormozi_yellow");

  // Execution & Project state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [activeStage, setActiveStage] = useState<string>("checking_source");
  const [progressPct, setProgressPct] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRestrictedError, setIsRestrictedError] = useState(false);

  // YouTube Cookies State
  interface CookieStatus {
    has_cookies: boolean;
    size_bytes: number;
    message: string;
  }
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null);
  const [cookieTextInput, setCookieTextInput] = useState("");
  const [isCookieSaving, setIsCookieSaving] = useState(false);
  const cookieFileInputRef = useRef<HTMLInputElement>(null);

  // Drawers & Modals
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [projectsList, setProjectsList] = useState<Project[]>([]);

  // Clip Editor & Re-render Modal state
  const [editingClip, setEditingClip] = useState<Clip | null>(null);
  const [editStartTime, setEditStartTime] = useState<number>(0);
  const [editEndTime, setEditEndTime] = useState<number>(20);
  const [editAspectRatio, setEditAspectRatio] = useState<"9:16" | "1:1" | "16:9">("9:16");
  const [editSubtitlesEnabled, setEditSubtitlesEnabled] = useState<boolean>(true);
  const [editSubtitleStyle, setEditSubtitleStyle] = useState<string>("hormozi_yellow");
  const [editSubtitlePosition, setEditSubtitlePosition] = useState<"bottom" | "center" | "top">("bottom");
  const [editSubtitleSize, setEditSubtitleSize] = useState<"compact" | "large" | "huge">("large");
  const [editAudioBoost, setEditAudioBoost] = useState<boolean>(true);
  const [isRerendering, setIsRerendering] = useState<boolean>(false);
  const [cacheBuster, setCacheBuster] = useState<number>(0);
  const [editSuccessMsg, setEditSuccessMsg] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const openEditModal = (clip: Clip) => {
    setEditingClip(clip);
    setEditStartTime(Math.round(clip.start_time * 10) / 10);
    setEditEndTime(Math.round(clip.end_time * 10) / 10);
    setEditAspectRatio((clip.aspect_ratio as "9:16" | "1:1" | "16:9") || "9:16");
    setEditSubtitlesEnabled(true);
    setEditSubtitleStyle(currentProject?.subtitle_style || "hormozi_yellow");
    setEditSubtitlePosition("bottom");
    setEditSubtitleSize("large");
    setEditAudioBoost(true);
    setEditSuccessMsg(null);
  };

  const handleRerenderClip = async () => {
    if (!editingClip || !currentProject) return;
    setIsRerendering(true);
    setEditSuccessMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/projects/${currentProject.id}/clips/${editingClip.id}/rerender`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_time: editStartTime,
          end_time: editEndTime,
          aspect_ratio: editAspectRatio,
          subtitles_enabled: editSubtitlesEnabled,
          subtitle_style: editSubtitleStyle,
          subtitle_position: editSubtitlePosition,
          subtitle_size: editSubtitleSize,
          audio_boost: editAudioBoost
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Re-rendering clip failed");
      }

      const updatedClip: Clip = await res.json();
      setClips((prev) => prev.map((c) => (c.id === updatedClip.id ? updatedClip : c)));
      setEditingClip(updatedClip);
      setCacheBuster(Date.now());
      setEditSuccessMsg("Short re-rendered successfully with custom enhancements!");
      setTimeout(() => {
        setEditingClip(null);
        setEditSuccessMsg(null);
      }, 1500);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error re-rendering clip";
      alert(msg);
    } finally {
      setIsRerendering(false);
    }
  };

  // Restore previous session on initial mount
  useEffect(() => {
    const savedProjectId = localStorage.getItem("clipforge_last_project");
    if (savedProjectId) {
      loadProject(savedProjectId);
    }
    fetchProjectsHistory();
    fetchCookieStatus();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const fetchCookieStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/cookies/status`);
      if (res.ok) {
        const data = await res.json();
        setCookieStatus(data);
      }
    } catch {
      // ignore
    }
  };

  const handleUploadCookieFile = async (file: File) => {
    setIsCookieSaving(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/api/cookies/upload`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        await fetchCookieStatus();
        setErrorMessage(null);
      }
    } catch (e) {
      console.error("Cookie upload failed:", e);
    } finally {
      setIsCookieSaving(false);
    }
  };

  const handleSaveCookieText = async () => {
    if (!cookieTextInput.trim()) return;
    setIsCookieSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/cookies/text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: cookieTextInput }),
      });
      if (res.ok) {
        await fetchCookieStatus();
        setCookieTextInput("");
        setErrorMessage(null);
      }
    } catch (e) {
      console.error("Cookie text save failed:", e);
    } finally {
      setIsCookieSaving(false);
    }
  };

  const handleRemoveCookies = async () => {
    setIsCookieSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/cookies`, {
        method: "DELETE",
      });
      if (res.ok) {
        await fetchCookieStatus();
      }
    } catch (e) {
      console.error("Cookie removal failed:", e);
    } finally {
      setIsCookieSaving(false);
    }
  };

  // Fetch past projects list
  const fetchProjectsHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects`);
      if (res.ok) {
        const data = await res.json();
        setProjectsList(data);
      }
    } catch {
      // Backend not yet reachable or starting
    }
  };

  // Load a project by ID
  const loadProject = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/projects/${id}`);
      if (res.ok) {
        const proj: Project = await res.json();
        setCurrentProject(proj);
        setClips(proj.clips || []);
        setActiveStage(proj.stage);
        setProgressPct(proj.progress);
        setStatusMessage(proj.status_message);

        if (proj.status === "processing") {
          setIsSubmitting(true);
          connectSSE(id);
        } else {
          setIsSubmitting(false);
          if (proj.status === "failed") {
            setErrorMessage(proj.status_message);
            const isRestr =
              proj.status_message?.toLowerCase().includes("restricted") ||
              proj.status_message?.toLowerCase().includes("upload a video file");
            setIsRestrictedError(Boolean(isRestr));
          } else {
            setErrorMessage(null);
            setIsRestrictedError(false);
          }
        }
      }
    } catch (err) {
      console.error("Failed to load project:", err);
    }
  };

  // Connect Server-Sent Events (SSE) for real-time progress
  const connectSSE = (projectId: string) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource(`${API_BASE}/api/projects/${projectId}/events`);
    eventSourceRef.current = es;

    es.addEventListener("status", (event: MessageEvent) => {
      try {
        let raw = event.data;
        if (typeof raw === "string") {
          try { raw = JSON.parse(raw); } catch { /* Ignore */ }
        }
        if (typeof raw === "string") {
          try { raw = JSON.parse(raw); } catch { /* Ignore */ }
        }
        const data = (typeof raw === "object" && raw !== null) ? raw : {};
        if (data.type === "progress" || data.type === "initial") {
          if (data.stage) setActiveStage(data.stage);
          if (typeof data.progress === "number") setProgressPct(data.progress);
          if (data.message) setStatusMessage(data.message);
          if (data.clips && data.clips.length > 0) {
            setClips(data.clips);
          }
        } else if (data.type === "clip_ready") {
          // New clip is ready immediately
          setClips((prev) => {
            const exists = prev.some((c) => c.id === data.clip.id);
            if (!exists) return [...prev, data.clip];
            return prev;
          });
        } else if (data.type === "completed") {
          setIsSubmitting(false);
          setActiveStage("completed");
          setProgressPct(100);
          setStatusMessage(data.message || "All shorts ready!");
          fetchProjectsHistory();
          es.close();
        } else if (data.type === "error") {
          setIsSubmitting(false);
          setActiveStage("failed");
          setErrorMessage(data.message);
          setIsRestrictedError(data.error_type === "permission_or_restricted");
          es.close();
        } else if (data.type === "cancelled") {
          setIsSubmitting(false);
          setActiveStage("cancelled");
          setStatusMessage("Processing was cancelled.");
          es.close();
        }
      } catch (e) {
        console.error("SSE parse error", e);
      }
    });

    es.onerror = () => {
      // Re-poll status if SSE drops
      fetch(`${API_BASE}/api/projects/${projectId}`)
        .then((res) => res.json())
        .then((proj) => {
          if (proj.status === "completed" || proj.status === "failed") {
            es.close();
            setIsSubmitting(false);
            setCurrentProject(proj);
            setClips(proj.clips || []);
          }
        })
        .catch(() => {});
    };
  };

  // Resolve metadata when URL changes or user pastes
  const handleResolveUrl = async (url: string) => {
    const cleanUrl = url.trim();
    setInputUrl(cleanUrl);
    setErrorMessage(null);
    setIsRestrictedError(false);

    if (!cleanUrl || cleanUrl.length < 10) {
      setVideoMeta(null);
      return;
    }

    setIsResolvingMeta(true);
    try {
      const res = await fetch(`${API_BASE}/api/metadata`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: cleanUrl }),
      });
      const data = await res.json();
      if (data.is_valid) {
        setVideoMeta({
          title: data.title,
          duration: data.duration,
          thumbnail_url: data.thumbnail_url,
          author: data.author,
        });
      } else {
        setVideoMeta(null);
        if (data.error) {
          setErrorMessage(data.error);
          if (data.error.includes("Upload a video file")) {
            setIsRestrictedError(true);
          }
        }
      }
    } catch {
      setVideoMeta(null);
    } finally {
      setIsResolvingMeta(false);
    }
  };

  // Paste from clipboard
  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        handleResolveUrl(text);
      }
    } catch {
      setErrorMessage("Unable to access clipboard. Please paste directly.");
    }
  };

  // Submit URL or Upload to generate shorts
  const handleGenerateShorts = async () => {
    setErrorMessage(null);
    setIsRestrictedError(false);
    setIsSubmitting(true);
    setClips([]);
    setProgressPct(5);
    setActiveStage("checking_source");
    setStatusMessage("Starting processing...");

    try {
      let res;
      if (activeTab === "url") {
        if (!inputUrl) {
          throw new Error("Please paste a YouTube video link.");
        }
        res = await fetch(`${API_BASE}/api/projects`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: inputUrl,
            duration_option: durationOption,
            num_clips_option: numClipsOption,
            subtitles_enabled: subtitlesEnabled,
            subtitle_style: subtitleStyle,
          }),
        });
      } else {
        if (!uploadedFile) {
          throw new Error("Please select a video file to upload.");
        }
        const formData = new FormData();
        formData.append("file", uploadedFile);
        formData.append("duration_option", durationOption);
        formData.append("num_clips_option", numClipsOption);
        formData.append("subtitles_enabled", String(subtitlesEnabled));
        formData.append("subtitle_style", subtitleStyle);

        res = await fetch(`${API_BASE}/api/upload`, {
          method: "POST",
          body: formData,
        });
      }

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const detail = errorData.detail || "Failed to start generation.";
        setIsRestrictedError(detail.includes("Upload a video file"));
        throw new Error(detail);
      }

      const proj: Project = await res.json();
      setCurrentProject(proj);
      localStorage.setItem("clipforge_last_project", proj.id);
      fetchProjectsHistory();
      connectSSE(proj.id);
    } catch (err: unknown) {
      setIsSubmitting(false);
      const msg = err instanceof Error ? err.message : "An unexpected error occurred.";
      setErrorMessage(msg);
    }
  };

  // Cancel processing
  const handleCancelProcessing = async () => {
    if (!currentProject) return;
    try {
      await fetch(`${API_BASE}/api/projects/${currentProject.id}/cancel`, {
        method: "POST",
      });
      setIsSubmitting(false);
      setStatusMessage("Cancelling pipeline...");
    } catch (e) {
      console.error(e);
    }
  };

  // Retry processing
  const handleRetry = async () => {
    setErrorMessage(null);
    setIsRestrictedError(false);
    setIsSubmitting(true);
    if (!currentProject) {
      if (inputUrl || uploadedFile) {
        handleGenerateShorts();
      } else {
        setIsSubmitting(false);
      }
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/projects/${currentProject.id}/retry`, {
        method: "POST",
      });
      if (res.ok) {
        const proj = await res.json();
        setCurrentProject(proj);
        connectSSE(proj.id);
      } else {
        handleGenerateShorts();
      }
    } catch (e) {
      console.error(e);
      handleGenerateShorts();
    }
  };

  // Switch to Upload workflow from restricted error
  const switchToUpload = () => {
    setActiveTab("upload");
    setErrorMessage(null);
    setIsRestrictedError(false);
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div
          className="logo-group"
          onClick={() => {
            setCurrentProject(null);
            setClips([]);
            setInputUrl("");
            setVideoMeta(null);
          }}
        >
          <div className="logo-icon-box">
            <svg className="logo-icon" viewBox="0 0 24 24" fill="none">
              <path
                d="M4 8H20M4 16H20M9 3L7 21M17 3L15 21"
                stroke="white"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <span className="logo-text">ClipForge</span>
        </div>

        <div className="header-actions">
          <button
            className="nav-btn cookie-pill-btn"
            onClick={() => setIsSettingsOpen(true)}
            title="YouTube Session Cookies Authentication"
          >
            <span className={`status-dot ${cookieStatus?.has_cookies ? "active" : "idle"}`} />
            Cookies: {cookieStatus?.has_cookies ? "Active" : "Setup"}
          </button>
          <button className="nav-btn" onClick={() => setIsDrawerOpen(true)}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="2" width="20" height="20" rx="5" />
              <path d="M10 9l5 3-5 3V9z" fill="currentColor" />
            </svg>
            My Clips
          </button>
          <button className="icon-btn" onClick={() => setIsSettingsOpen(true)} title="Settings">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
      </header>

      {/* Hero Section */}
      <section className="hero-section">
        <div className="hero-badge">
          <span className="hero-badge-dot" />
          AI Video To Shorts Engine
        </div>
        <h1 className="hero-title">Turn Long Videos Into Shorts.</h1>
        <p className="hero-subtitle">
          Find the best moments. Generate shorts. Download instantly.
        </p>
      </section>

      {/* Main Generator Card */}
      <div className="main-card">
        {/* Source Switch Tabs */}
        <div className="input-tabs">
          <button
            className={`tab-btn ${activeTab === "url" ? "active" : ""}`}
            onClick={() => setActiveTab("url")}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
            YouTube Link
          </button>
          <button
            className={`tab-btn ${activeTab === "upload" ? "active" : ""}`}
            onClick={() => setActiveTab("upload")}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            Upload Video File
          </button>
        </div>

        {/* Tab 1: URL Input */}
        {activeTab === "url" && (
          <div className="input-group">
            <input
              type="text"
              className="url-input"
              placeholder="Paste your YouTube video link here"
              value={inputUrl}
              onChange={(e) => handleResolveUrl(e.target.value)}
              disabled={isSubmitting}
            />
            <button className="paste-btn" onClick={handlePaste} disabled={isSubmitting}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              Paste
            </button>
          </div>
        )}

        {/* Tab 2: Upload Dropzone */}
        {activeTab === "upload" && (
          <div>
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: "none" }}
              accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setUploadedFile(e.target.files[0]);
                }
              }}
            />
            <div
              className="dropzone"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  setUploadedFile(e.dataTransfer.files[0]);
                }
              }}
            >
              <svg className="dropzone-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <div className="dropzone-title">
                {uploadedFile ? uploadedFile.name : "Click or drag video file here"}
              </div>
              <div className="dropzone-hint">
                Supports MP4, MOV, WebM (up to 1080p). Zero file upload restrictions.
              </div>
            </div>
          </div>
        )}

        {/* Video Preview Card */}
        {isResolvingMeta && (
          <div className="video-preview-card">
            <div className="spinner" />
            <span style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
              Resolving YouTube video metadata...
            </span>
          </div>
        )}

        {videoMeta && !isResolvingMeta && (
          <div className="video-preview-card">
            <div className="preview-thumb-box">
              {videoMeta.thumbnail_url ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={videoMeta.thumbnail_url}
                  alt={videoMeta.title}
                  className="preview-thumb-img"
                />
              ) : (
                <div style={{ width: "100%", height: "100%", background: "#1a1d26" }} />
              )}
            </div>
            <div className="preview-info">
              <div className="preview-title" title={videoMeta.title}>
                {videoMeta.title}
              </div>
              <div className="preview-meta">
                <span className="preview-meta-pill">
                  {formatTime(videoMeta.duration)}
                </span>
                <span>{videoMeta.author || "Creator"}</span>
              </div>
            </div>
          </div>
        )}

        {/* Options Grid */}
        <div className="config-grid">
          {/* Duration Selector */}
          <div className="config-item">
            <label className="config-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              Duration
            </label>
            <div className="segmented-group">
              <button
                className={`segment-btn ${durationOption === "20" ? "active" : ""}`}
                onClick={() => setDurationOption("20")}
                disabled={isSubmitting}
              >
                20 seconds
              </button>
              <button
                className={`segment-btn ${durationOption === "30" ? "active" : ""}`}
                onClick={() => setDurationOption("30")}
                disabled={isSubmitting}
              >
                30 seconds
              </button>
              <button
                className={`segment-btn ${durationOption === "both" ? "active" : ""}`}
                onClick={() => setDurationOption("both")}
                disabled={isSubmitting}
              >
                Both
              </button>
            </div>
          </div>

          {/* Number of Clips Selector */}
          <div className="config-item">
            <label className="config-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="2" y="2" width="20" height="8" rx="2" />
                <rect x="2" y="14" width="20" height="8" rx="2" />
              </svg>
              Number of Clips
            </label>
            <div className="segmented-group">
              <button
                className={`segment-btn ${numClipsOption === "3" ? "active" : ""}`}
                onClick={() => setNumClipsOption("3")}
                disabled={isSubmitting}
              >
                3
              </button>
              <button
                className={`segment-btn ${numClipsOption === "5" ? "active" : ""}`}
                onClick={() => setNumClipsOption("5")}
                disabled={isSubmitting}
              >
                5
              </button>
              <button
                className={`segment-btn ${numClipsOption === "10" ? "active" : ""}`}
                onClick={() => setNumClipsOption("10")}
                disabled={isSubmitting}
              >
                10
              </button>
              <button
                className={`segment-btn ${numClipsOption === "auto" ? "active" : ""}`}
                onClick={() => setNumClipsOption("auto")}
                disabled={isSubmitting}
              >
                Auto
              </button>
            </div>
          </div>
        </div>

        {/* Subtitles Row */}
        <div
          className="subtitle-row"
          style={subtitlesEnabled ? { marginBottom: 0, borderRadius: "var(--radius-lg) var(--radius-lg) 0 0" } : {}}
          onClick={() => !isSubmitting && setSubtitlesEnabled(!subtitlesEnabled)}
        >
          <div className="subtitle-info">
            <svg className="subtitle-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="4" width="20" height="16" rx="3" />
              <path d="M7 15h4M13 15h4M7 11h10" />
            </svg>
            <div>
              <div className="subtitle-title">Viral Creator Subtitles</div>
              <div className="subtitle-desc">
                High-contrast animated captions with active spoken-word glow
              </div>
            </div>
          </div>
          <label className="switch" onClick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              checked={subtitlesEnabled}
              onChange={(e) => setSubtitlesEnabled(e.target.checked)}
              disabled={isSubmitting}
            />
            <span className="slider" />
          </label>
        </div>

        {/* Viral Subtitle Preset Customizer */}
        {subtitlesEnabled && (
          <div className="subtitle-panel">
            <div className="subtitle-panel-header">
              <span className="subtitle-panel-label">Caption Style Preset</span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Active word pop animation
              </span>
            </div>

            <div className="subtitle-themes-grid">
              {SUBTITLE_PRESETS.map((preset) => {
                const isActive = subtitleStyle === preset.id;
                return (
                  <button
                    key={preset.id}
                    type="button"
                    className={`subtitle-theme-card ${isActive ? "active" : ""}`}
                    style={{ "--theme-accent": preset.color } as React.CSSProperties}
                    onClick={() => !isSubmitting && setSubtitleStyle(preset.id)}
                    disabled={isSubmitting}
                  >
                    <div className="subtitle-theme-top">
                      <span
                        className="subtitle-theme-dot"
                        style={{
                          backgroundColor: preset.color,
                          boxShadow: isActive ? `0 0 8px ${preset.color}` : "none",
                        }}
                      />
                      <span className="subtitle-theme-name">{preset.name}</span>
                    </div>
                    <span className="subtitle-theme-desc">{preset.creator}</span>
                  </button>
                );
              })}
            </div>

            {/* Live Interactive Preview Box */}
            <div className="subtitle-preview-box">
              <div className="subtitle-preview-text">
                THE{" "}
                <span
                  className="subtitle-preview-highlight"
                  style={{
                    color: SUBTITLE_PRESETS.find((p) => p.id === subtitleStyle)?.color || "#FFE81F",
                  }}
                >
                  {SUBTITLE_PRESETS.find((p) => p.id === subtitleStyle)?.sample || "SECRET"}
                </span>{" "}
                FORMULA
              </div>
              <div className="subtitle-preview-meta">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                Arial Black · 1080x1920 safe zone
              </div>
            </div>
          </div>
        )}

        {/* Primary Generate Button */}
        <button
          className="generate-btn"
          onClick={handleGenerateShorts}
          disabled={isSubmitting || (activeTab === "url" && !inputUrl) || (activeTab === "upload" && !uploadedFile)}
        >
          {isSubmitting ? (
            <>
              <div className="spinner" />
              Generating Shorts...
            </>
          ) : (
            <>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" />
              </svg>
              Generate Shorts
            </>
          )}
        </button>
      </div>

      {/* Error Banner with Comprehensive Recovery Actions */}
      {errorMessage && (() => {
        const isLockError = errorMessage.includes("WinError") || errorMessage.includes("used by another process");
        const isBotChallenge =
          errorMessage.toLowerCase().includes("bot") ||
          errorMessage.toLowerCase().includes("verification") ||
          errorMessage.toLowerCase().includes("cookie") ||
          errorMessage.toLowerCase().includes("sign in");

        return (
          <div className="error-banner">
            <svg className="error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div className="error-content">
              <div className="error-title">
                {isBotChallenge
                  ? "YouTube Bot Verification Required"
                  : isLockError
                  ? "Temporary File Access Notice"
                  : "Processing Notice"}
              </div>
              <div className="error-text">
                {isLockError
                  ? "A temporary file lock occurred on Windows OneDrive/sync. Click 'Retry Generation' to resume."
                  : errorMessage}
              </div>
              <div className="error-actions-row">
                {isBotChallenge && (
                  <button
                    className="error-action-btn primary"
                    onClick={() => setIsSettingsOpen(true)}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                    Import YouTube Cookies (.txt)
                  </button>
                )}
                <button className="error-action-btn secondary" onClick={switchToUpload}>
                  Upload Video File Directly
                </button>
                <button className="error-action-btn tertiary" onClick={handleRetry}>
                  Retry Generation
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Live Processing Status Card */}
      {isSubmitting && (
        <div className="status-card">
          <div className="status-header">
            <div className="status-stage-badge">
              <span className="pulse-indicator" />
              Stage: {STAGE_LABELS[activeStage] || activeStage}
            </div>
            <button className="cancel-btn" onClick={handleCancelProcessing}>
              Cancel Job
            </button>
          </div>

          {/* Stepper showing all 6 stages */}
          <div className="stages-stepper">
            {STAGES_ORDER.map((stageKey) => {
              const currIdx = STAGES_ORDER.indexOf(activeStage);
              const stepIdx = STAGES_ORDER.indexOf(stageKey);
              const isDone = currIdx > stepIdx;
              const isActive = currIdx === stepIdx;

              return (
                <div
                  key={stageKey}
                  className={`stage-step ${isDone ? "done" : ""} ${isActive ? "active" : ""}`}
                >
                  {STAGE_LABELS[stageKey]}
                </div>
              );
            })}
          </div>

          <div className="progress-container">
            <div className="progress-bar-fill" style={{ width: `${progressPct}%` }} />
          </div>

          <div className="status-message">
            <span>{statusMessage || "Processing video streams..."}</span>
            <span className="progress-pct">{progressPct}%</span>
          </div>
        </div>
      )}

      {/* Results Section */}
      {clips.length > 0 && (
        <section className="results-section">
          <div className="results-header">
            <div className="results-title-group">
              <h2 className="results-heading">Generated Clips</h2>
              <span className="results-count-pill">{clips.length} Shorts</span>
            </div>

            {currentProject && (
              <a
                href={`${API_BASE}/api/projects/${currentProject.id}/download-all`}
                className="download-all-btn"
                download
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Download All (ZIP)
              </a>
            )}
          </div>

          <div className="clips-grid">
            {clips.map((clip, index) => {
              const streamUrl = `${API_BASE}/api/projects/${clip.project_id}/clips/${clip.id}/stream`;
              const downloadUrl = `${API_BASE}/api/projects/${clip.project_id}/clips/${clip.id}/download`;

              return (
                <div key={clip.id} className="clip-card">
                  {/* Vertical 9:16 Video Player */}
                  <div className="video-player-container">
                    <video
                      controls
                      playsInline
                      preload="metadata"
                      className="video-player"
                      src={`${streamUrl}?t=${cacheBuster}`}
                    />
                  </div>

                  <div className="clip-card-body">
                    <div className="clip-badges-row" style={{ flexWrap: "wrap", gap: "6px" }}>
                      <span className="badge-3s-hook" title="Predicted viewer retention for first 3 seconds">
                        {clip.hook_tag || "🔥 Curiosity Gap"} ({Math.round(clip.retention_3s || 92)}% 3s Hook)
                      </span>
                      <span className="badge-ratio">{clip.aspect_ratio || "9:16"}</span>
                      <span className="badge-dur">{Math.round(clip.duration)}s</span>
                      <span className="badge-time">
                        {formatTime(clip.start_time)} - {formatTime(clip.end_time)}
                      </span>
                      <span className="badge-score">
                        {Math.round(clip.score)}% Score
                      </span>
                    </div>

                    <h3 className="clip-title" title={clip.title}>
                      {clip.title}
                    </h3>
                    <p className="clip-summary">
                      {clip.summary || `Extracted highlight #${index + 1}`}
                    </p>

                    <div className="clip-actions-row">
                      <button className="edit-clip-btn" onClick={() => openEditModal(clip)}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M12 20h9" />
                          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                        </svg>
                        Edit & Refine
                      </button>
                      <a href={downloadUrl} className="download-clip-btn" download>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                        Download
                      </a>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* "My Clips" Drawer */}
      {isDrawerOpen && (
        <div className="modal-overlay" onClick={() => setIsDrawerOpen(false)}>
          <div className="drawer-content" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <h3 className="drawer-title">My Clips</h3>
              <button className="close-btn" onClick={() => setIsDrawerOpen(false)}>
                ✕
              </button>
            </div>

            {projectsList.length === 0 ? (
              <div style={{ color: "var(--text-muted)", fontSize: "14px", textAlign: "center", padding: "40px 0" }}>
                No past generated clips yet.
              </div>
            ) : (
              projectsList.map((p) => (
                <div
                  key={p.id}
                  className="project-item"
                  onClick={() => {
                    loadProject(p.id);
                    setIsDrawerOpen(false);
                  }}
                >
                  <div>
                    <div className="project-item-title">{p.title}</div>
                    <div className="project-item-meta">
                      {new Date(p.created_at).toLocaleDateString()} • {p.status}
                    </div>
                  </div>
                  <span className="results-count-pill">
                    {p.status === "completed" ? "Ready" : p.status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {isSettingsOpen && (
        <div className="modal-overlay" onClick={() => setIsSettingsOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <h3 className="drawer-title">Processing Settings</h3>
              <button className="close-btn" onClick={() => setIsSettingsOpen(false)}>
                ✕
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
              {/* YouTube Cookies Authentication */}
              <div className="cookie-card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <label className="config-label" style={{ margin: 0 }}>
                    YouTube Session Authentication
                  </label>
                  <span className={`cookie-status-badge ${cookieStatus?.has_cookies ? "active" : "idle"}`}>
                    <span className={`status-dot ${cookieStatus?.has_cookies ? "active" : "idle"}`} />
                    {cookieStatus?.has_cookies
                      ? `Active (${Math.round((cookieStatus.size_bytes || 0) / 1024)} KB)`
                      : "Anonymous Mode"}
                  </span>
                </div>

                <div style={{ fontSize: "12px", color: "var(--text-muted)", lineHeight: "1.4" }}>
                  Bypasses YouTube&apos;s &quot;Sign in to confirm you&apos;re not a bot&quot; verification for all video streams.
                </div>

                <input
                  type="file"
                  ref={cookieFileInputRef}
                  style={{ display: "none" }}
                  accept=".txt"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleUploadCookieFile(e.target.files[0]);
                    }
                  }}
                />

                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  <button
                    className="error-action-btn primary"
                    onClick={() => cookieFileInputRef.current?.click()}
                    disabled={isCookieSaving}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    Upload cookies.txt File
                  </button>

                  {cookieStatus?.has_cookies && (
                    <button
                      className="error-action-btn tertiary"
                      onClick={handleRemoveCookies}
                      disabled={isCookieSaving}
                    >
                      Remove Cookies
                    </button>
                  )}
                </div>

                <div style={{ marginTop: "4px" }}>
                  <textarea
                    className="cookie-input-area"
                    placeholder="Or paste Netscape format cookies here (# Netscape HTTP Cookie File...)"
                    value={cookieTextInput}
                    onChange={(e) => setCookieTextInput(e.target.value)}
                  />
                  {cookieTextInput.trim() && (
                    <button
                      className="error-action-btn primary"
                      style={{ marginTop: "6px" }}
                      onClick={handleSaveCookieText}
                      disabled={isCookieSaving}
                    >
                      Save Pasted Cookies
                    </button>
                  )}
                </div>
              </div>

              <div>
                <label className="config-label" style={{ marginBottom: "6px" }}>
                  Speech Transcription Model
                </label>
                <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "8px" }}>
                  Runs 100% locally on CPU/GPU without external API keys.
                </div>
                <div className="segmented-group">
                  <button className="segment-btn active">base (Recommended)</button>
                  <button className="segment-btn">tiny (Ultra fast)</button>
                  <button className="segment-btn">small (Accurate)</button>
                </div>
              </div>

              <div>
                <label className="config-label" style={{ marginBottom: "6px" }}>
                  Framing & Crop Mode
                </label>
                <div className="segmented-group">
                  <button className="segment-btn active">Smart Fill Crop (9:16)</button>
                  <button className="segment-btn">Safe Centered</button>
                </div>
              </div>

              <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "14px", fontSize: "12px", color: "var(--text-muted)" }}>
                <div>• FFmpeg: Essentials Build 9.0.1 (Local)</div>
                <div>• Speech Engine: faster-whisper (Local)</div>
                <div>• Visuals: OpenCV scene detection</div>
                <div>• Zero paid API key dependencies</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Clip Editor Modal */}
      {editingClip && (
        <div className="modal-overlay" onClick={() => !isRerendering && setEditingClip(null)}>
          <div className="editor-modal" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span className="badge-3s-hook">
                  {editingClip.hook_tag || "🔥 Curiosity Gap"}
                </span>
                <h3 className="drawer-title" style={{ margin: 0 }}>
                  Edit & Refine Short
                </h3>
              </div>
              <button
                className="close-btn"
                onClick={() => !isRerendering && setEditingClip(null)}
                disabled={isRerendering}
              >
                ✕
              </button>
            </div>

            {/* Video Preview */}
            <div className="editor-preview-container">
              <video
                controls
                playsInline
                className="editor-preview-video"
                src={`${API_BASE}/api/projects/${editingClip.project_id}/clips/${editingClip.id}/stream?t=${cacheBuster}`}
              />
            </div>

            {editSuccessMsg && (
              <div style={{ padding: "10px 14px", background: "rgba(16, 185, 129, 0.15)", color: "#34d399", borderRadius: "var(--radius-md)", border: "1px solid rgba(16, 185, 129, 0.3)", marginBottom: "16px", fontSize: "13px", fontWeight: "600" }}>
                ✓ {editSuccessMsg}
              </div>
            )}

            {/* Trim Timers Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px", marginBottom: "16px" }}>
              <div className="editor-field-group">
                <label className="config-label">Start Time (seconds)</label>
                <div className="time-adjuster-row">
                  <button
                    type="button"
                    className="time-btn"
                    onClick={() => setEditStartTime((t) => Math.max(0, Math.round((t - 1) * 10) / 10))}
                    disabled={isRerendering}
                  >
                    -1s
                  </button>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    className="time-input"
                    value={editStartTime}
                    onChange={(e) => setEditStartTime(parseFloat(e.target.value) || 0)}
                    disabled={isRerendering}
                  />
                  <button
                    type="button"
                    className="time-btn"
                    onClick={() => setEditStartTime((t) => Math.round((t + 1) * 10) / 10)}
                    disabled={isRerendering}
                  >
                    +1s
                  </button>
                </div>
              </div>

              <div className="editor-field-group">
                <label className="config-label">End Time (seconds)</label>
                <div className="time-adjuster-row">
                  <button
                    type="button"
                    className="time-btn"
                    onClick={() => setEditEndTime((t) => Math.max(editStartTime + 3, Math.round((t - 1) * 10) / 10))}
                    disabled={isRerendering}
                  >
                    -1s
                  </button>
                  <input
                    type="number"
                    step="0.1"
                    min="3"
                    className="time-input"
                    value={editEndTime}
                    onChange={(e) => setEditEndTime(parseFloat(e.target.value) || 0)}
                    disabled={isRerendering}
                  />
                  <button
                    type="button"
                    className="time-btn"
                    onClick={() => setEditEndTime((t) => Math.round((t + 1) * 10) / 10)}
                    disabled={isRerendering}
                  >
                    +1s
                  </button>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", padding: "8px 12px", background: "var(--bg-card-subtle)", borderRadius: "var(--radius-md)" }}>
              <span style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
                Selected Short Duration:
              </span>
              <span style={{ fontSize: "14px", fontWeight: "700", color: "#c4b5fd" }}>
                {Math.max(0, Math.round((editEndTime - editStartTime) * 10) / 10)} seconds
              </span>
            </div>

            {/* Aspect Ratio Selector */}
            <div className="editor-field-group">
              <label className="config-label">Framing & Aspect Ratio</label>
              <div className="segmented-group">
                <button
                  type="button"
                  className={`segment-btn ${editAspectRatio === "9:16" ? "active" : ""}`}
                  onClick={() => setEditAspectRatio("9:16")}
                  disabled={isRerendering}
                >
                  9:16 Vertical (Shorts/Reels)
                </button>
                <button
                  type="button"
                  className={`segment-btn ${editAspectRatio === "1:1" ? "active" : ""}`}
                  onClick={() => setEditAspectRatio("1:1")}
                  disabled={isRerendering}
                >
                  1:1 Square (Feed)
                </button>
                <button
                  type="button"
                  className={`segment-btn ${editAspectRatio === "16:9" ? "active" : ""}`}
                  onClick={() => setEditAspectRatio("16:9")}
                  disabled={isRerendering}
                >
                  16:9 Landscape (Highlight)
                </button>
              </div>
            </div>

            {/* Subtitle Positioning & Style */}
            <div className="editor-field-group">
              <label className="config-label">Subtitle Position</label>
              <div className="segmented-group">
                <button
                  type="button"
                  className={`segment-btn ${editSubtitlePosition === "bottom" ? "active" : ""}`}
                  onClick={() => setEditSubtitlePosition("bottom")}
                  disabled={isRerendering}
                >
                  Bottom (Safe Zone)
                </button>
                <button
                  type="button"
                  className={`segment-btn ${editSubtitlePosition === "center" ? "active" : ""}`}
                  onClick={() => setEditSubtitlePosition("center")}
                  disabled={isRerendering}
                >
                  Center (Hero Focus)
                </button>
                <button
                  type="button"
                  className={`segment-btn ${editSubtitlePosition === "top" ? "active" : ""}`}
                  onClick={() => setEditSubtitlePosition("top")}
                  disabled={isRerendering}
                >
                  Top (Header)
                </button>
              </div>
            </div>

            <div className="editor-field-group">
              <label className="config-label">Subtitle Caption Theme</label>
              <div className="segmented-group">
                {SUBTITLE_PRESETS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className={`segment-btn ${editSubtitleStyle === p.id ? "active" : ""}`}
                    onClick={() => setEditSubtitleStyle(p.id)}
                    disabled={isRerendering}
                  >
                    <span style={{ color: p.color, fontWeight: "700" }}>●</span> {p.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Audio Loudness Booster */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 14px", background: "var(--bg-card-subtle)", borderRadius: "var(--radius-md)", marginTop: "10px" }}>
              <div>
                <div style={{ fontSize: "14px", fontWeight: "600", color: "var(--text-primary)" }}>
                  Audio Loudness & Vocal Clarity EQ
                </div>
                <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                  Applies EBU R128 loudness normalization for punchy mobile audio
                </div>
              </div>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={editAudioBoost}
                  onChange={(e) => setEditAudioBoost(e.target.checked)}
                  disabled={isRerendering}
                />
                <span className="slider" />
              </label>
            </div>

            {/* Modal Actions */}
            <div className="editor-footer">
              <button
                type="button"
                className="error-action-btn tertiary"
                onClick={() => setEditingClip(null)}
                disabled={isRerendering}
              >
                Cancel
              </button>
              <button
                type="button"
                className="error-action-btn primary"
                onClick={handleRerenderClip}
                disabled={isRerendering}
              >
                {isRerendering ? (
                  <>
                    <div className="spinner" />
                    Re-rendering Short...
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" />
                    </svg>
                    Apply & Re-render Short
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
