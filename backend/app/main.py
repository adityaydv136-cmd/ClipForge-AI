import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import PROJECTS_DIR, FFMPEG_PATH, FFPROBE_PATH
from .database import init_db
from .routes.projects import router as projects_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure SQLite tables and folders exist
    init_db()
    print("=" * 60)
    print(">> ClipForge Backend Engine Initialized")
    print(f"   FFmpeg Path : {FFMPEG_PATH or 'NOT FOUND'}")
    print(f"   FFprobe Path: {FFPROBE_PATH or 'NOT FOUND'}")
    print(f"   Storage Dir : {PROJECTS_DIR}")
    print("=" * 60)
    yield
    # Shutdown

app = FastAPI(
    title="ClipForge API",
    description="Local AI Video-to-Shorts Engine",
    version="1.0.0",
    lifespan=lifespan
)

# Allow requests from Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)

@app.get("/")
def root():
    return {
        "app": "ClipForge API",
        "status": "online",
        "docs": "/docs",
        "ffmpeg": bool(FFMPEG_PATH)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
