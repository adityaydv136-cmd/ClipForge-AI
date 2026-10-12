import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from .config import DB_PATH

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    conn = get_db_connection()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_url TEXT,
                source_type TEXT NOT NULL DEFAULT 'url',
                thumbnail_url TEXT,
                duration REAL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                stage TEXT NOT NULL DEFAULT 'checking_source',
                progress INTEGER NOT NULL DEFAULT 0,
                status_message TEXT DEFAULT '',
                duration_option TEXT NOT NULL DEFAULT '20',
                num_clips_option TEXT NOT NULL DEFAULT '3',
                subtitles_enabled INTEGER NOT NULL DEFAULT 1,
                subtitle_style TEXT NOT NULL DEFAULT 'hormozi_yellow',
                editing_personality TEXT NOT NULL DEFAULT 'retention',
                memes_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                zip_path TEXT
            )
        """)
        # Auto-migration if column doesn't exist
        cur = conn.execute("PRAGMA table_info(projects)")
        cols = [r["name"] for r in cur.fetchall()]
        if "subtitle_style" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN subtitle_style TEXT DEFAULT 'hormozi_yellow'")
        if "editing_personality" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN editing_personality TEXT DEFAULT 'retention'")
        if "memes_enabled" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN memes_enabled INTEGER DEFAULT 1")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS clips (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                duration REAL NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                summary TEXT DEFAULT '',
                file_path TEXT NOT NULL,
                thumbnail_path TEXT,
                aspect_ratio TEXT NOT NULL DEFAULT '9:16',
                hook_tag TEXT DEFAULT '🔥 Viral Hook',
                hook_category TEXT DEFAULT 'Curiosity Gap',
                retention_3s REAL DEFAULT 92.0,
                editing_personality TEXT DEFAULT 'retention',
                story_structure TEXT DEFAULT '{}',
                qc_passed INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )
        """)
        # Auto-migration for clips table columns
        clip_cur = conn.execute("PRAGMA table_info(clips)")
        clip_cols = [r["name"] for r in clip_cur.fetchall()]
        if "hook_tag" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN hook_tag TEXT DEFAULT '🔥 Viral Hook'")
        if "hook_category" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN hook_category TEXT DEFAULT 'Curiosity Gap'")
        if "retention_3s" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN retention_3s REAL DEFAULT 92.0")
        if "editing_personality" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN editing_personality TEXT DEFAULT 'retention'")
        if "story_structure" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN story_structure TEXT DEFAULT '{}'")
        if "qc_passed" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN qc_passed INTEGER DEFAULT 1")
    conn.close()

def save_project(project: Dict[str, Any]):
    conn = get_db_connection()
    now = datetime.utcnow().isoformat()
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO projects (
                id, title, source_url, source_type, thumbnail_url, duration,
                status, stage, progress, status_message, duration_option,
                num_clips_option, subtitles_enabled, subtitle_style,
                editing_personality, memes_enabled, created_at, updated_at, zip_path
            ) VALUES (
                :id, :title, :source_url, :source_type, :thumbnail_url, :duration,
                :status, :stage, :progress, :status_message, :duration_option,
                :num_clips_option, :subtitles_enabled, :subtitle_style,
                :editing_personality, :memes_enabled,
                COALESCE((SELECT created_at FROM projects WHERE id = :id), :created_at),
                :updated_at, :zip_path
            )
        """, {
            "id": project["id"],
            "title": project.get("title", "Untitled Project"),
            "source_url": project.get("source_url"),
            "source_type": project.get("source_type", "url"),
            "thumbnail_url": project.get("thumbnail_url"),
            "duration": project.get("duration", 0),
            "status": project.get("status", "pending"),
            "stage": project.get("stage", "checking_source"),
            "progress": project.get("progress", 0),
            "status_message": project.get("status_message", ""),
            "duration_option": project.get("duration_option", "20"),
            "num_clips_option": project.get("num_clips_option", "3"),
            "subtitles_enabled": 1 if project.get("subtitles_enabled", True) else 0,
            "subtitle_style": project.get("subtitle_style", "hormozi_yellow"),
            "editing_personality": project.get("editing_personality", "retention"),
            "memes_enabled": 1 if project.get("memes_enabled", True) else 0,
            "created_at": now,
            "updated_at": now,
            "zip_path": project.get("zip_path")
        })
    conn.close()

def update_project_status(project_id: str, status: str, stage: str, progress: int, message: str = "", zip_path: Optional[str] = None):
    conn = get_db_connection()
    now = datetime.utcnow().isoformat()
    with conn:
        if zip_path is not None:
            conn.execute("""
                UPDATE projects 
                SET status = ?, stage = ?, progress = ?, status_message = ?, updated_at = ?, zip_path = ?
                WHERE id = ?
            """, (status, stage, progress, message, now, zip_path, project_id))
        else:
            conn.execute("""
                UPDATE projects 
                SET status = ?, stage = ?, progress = ?, status_message = ?, updated_at = ?
                WHERE id = ?
            """, (status, stage, progress, message, now, project_id))
    conn.close()

def save_clip(clip: Dict[str, Any]):
    conn = get_db_connection()
    now = datetime.utcnow().isoformat()
    story_raw = clip.get("story_structure")
    if isinstance(story_raw, dict):
        story_str = json.dumps(story_raw)
    elif isinstance(story_raw, str):
        story_str = story_raw
    else:
        story_str = "{}"

    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO clips (
                id, project_id, title, start_time, end_time, duration,
                score, summary, file_path, thumbnail_path, aspect_ratio,
                hook_tag, hook_category, retention_3s,
                editing_personality, story_structure, qc_passed, created_at
            ) VALUES (
                :id, :project_id, :title, :start_time, :end_time, :duration,
                :score, :summary, :file_path, :thumbnail_path, :aspect_ratio,
                :hook_tag, :hook_category, :retention_3s,
                :editing_personality, :story_structure, :qc_passed, :created_at
            )
        """, {
            "id": clip["id"],
            "project_id": clip["project_id"],
            "title": clip["title"],
            "start_time": clip["start_time"],
            "end_time": clip["end_time"],
            "duration": clip["duration"],
            "score": clip.get("score", 0),
            "summary": clip.get("summary", ""),
            "file_path": clip["file_path"],
            "thumbnail_path": clip.get("thumbnail_path"),
            "aspect_ratio": clip.get("aspect_ratio", "9:16"),
            "hook_tag": clip.get("hook_tag", "🔥 Viral Hook"),
            "hook_category": clip.get("hook_category", "Curiosity Gap"),
            "retention_3s": float(clip.get("retention_3s", 92.0)),
            "editing_personality": clip.get("editing_personality", "retention"),
            "story_structure": story_str,
            "qc_passed": 1 if clip.get("qc_passed", True) else 0,
            "created_at": now
        })
    conn.close()

def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    project = dict(row)
    project["subtitles_enabled"] = bool(project["subtitles_enabled"])
    project["memes_enabled"] = bool(project.get("memes_enabled", 1))

    cursor.execute("SELECT * FROM clips WHERE project_id = ? ORDER BY start_time ASC", (project_id,))
    raw_clips = cursor.fetchall()
    clips = []
    for c in raw_clips:
        cd = dict(c)
        cd["qc_passed"] = bool(cd.get("qc_passed", 1))
        # Parse story_structure
        story_val = cd.get("story_structure")
        if isinstance(story_val, str) and story_val.strip():
            try:
                cd["story_structure"] = json.loads(story_val)
            except Exception:
                cd["story_structure"] = None
        else:
            cd["story_structure"] = None
        clips.append(cd)
    project["clips"] = clips
    conn.close()
    return project

def get_all_projects() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
    rows = cursor.fetchall()
    projects = []
    for row in rows:
        p = dict(row)
        p["subtitles_enabled"] = bool(p["subtitles_enabled"])
        p["memes_enabled"] = bool(p.get("memes_enabled", 1))
        cursor.execute("SELECT COUNT(*) as count FROM clips WHERE project_id = ?", (p["id"],))
        p["clip_count"] = cursor.fetchone()["count"]
        projects.append(p)
    conn.close()
    return projects

def delete_project(project_id: str):
    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.close()
