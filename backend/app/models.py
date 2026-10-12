from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Literal, Dict, Any

class ProjectCreateRequest(BaseModel):
    url: Optional[str] = None
    duration_option: Literal["20", "30", "both"] = "20"
    num_clips_option: Literal["3", "5", "10", "auto"] = "3"
    subtitles_enabled: bool = True
    subtitle_style: Literal["hormozi_yellow", "neon_green", "electric_cyan", "sunset_orange", "pink_fuchsia"] = "hormozi_yellow"
    editing_personality: Literal["retention", "funny", "storytelling", "educational", "natural"] = "retention"
    memes_enabled: bool = True

class MetadataRequest(BaseModel):
    url: str

class MetadataResponse(BaseModel):
    title: str
    duration: float
    thumbnail_url: Optional[str] = None
    author: Optional[str] = None
    is_valid: bool = True
    error: Optional[str] = None

class CookieStatusResponse(BaseModel):
    has_cookies: bool
    size_bytes: int = 0
    message: str

class ClipResponse(BaseModel):
    id: str
    project_id: str
    title: str
    start_time: float
    end_time: float
    duration: float
    score: float
    summary: str
    file_path: str
    thumbnail_path: Optional[str] = None
    aspect_ratio: str = "9:16"
    hook_tag: Optional[str] = "🔥 Viral Hook"
    hook_category: Optional[str] = "Curiosity Gap"
    retention_3s: Optional[float] = 92.0
    editing_personality: Optional[str] = "retention"
    story_structure: Optional[Dict[str, Any]] = None
    qc_passed: Optional[bool] = True
    created_at: str

class ClipEditRequest(BaseModel):
    start_time: float
    end_time: float
    aspect_ratio: Literal["9:16", "1:1", "16:9"] = "9:16"
    subtitles_enabled: bool = True
    subtitle_style: Literal["hormozi_yellow", "neon_green", "electric_cyan", "sunset_orange", "pink_fuchsia"] = "hormozi_yellow"
    subtitle_position: Literal["bottom", "center", "top"] = "bottom"
    subtitle_size: Literal["compact", "large", "huge"] = "large"
    audio_boost: bool = True

class ProjectResponse(BaseModel):
    id: str
    title: str
    source_url: Optional[str] = None
    source_type: str
    thumbnail_url: Optional[str] = None
    duration: float
    status: str
    stage: str
    progress: int
    status_message: str
    duration_option: str
    num_clips_option: str
    subtitles_enabled: bool
    subtitle_style: Optional[str] = "hormozi_yellow"
    editing_personality: Optional[str] = "retention"
    memes_enabled: Optional[bool] = True
    created_at: str
    updated_at: str
    zip_path: Optional[str] = None
    clips: List[ClipResponse] = []
