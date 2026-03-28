import os
import asyncio
import subprocess
import uuid
import tempfile
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional

import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Dragonsvitex TTS Studio API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
TEMP_DIR = Path(os.getenv("TEMP_DIR", "./temp"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

VOICES = {
    "dmitry": {"azure_id": "ru-RU-DmitryNeural", "name": "Дмитрий", "gender": "male"},
    "dmitry_advanced": {"azure_id": "ru-RU-DmitryNeural", "name": "Дмитрий Pro", "gender": "male"},
    "oleg": {"azure_id": "ru-RU-DmitryNeural", "name": "Олег", "gender": "male"},
    "filipp": {"azure_id": "ru-RU-DmitryNeural", "name": "Филипп", "gender": "male"},
    "svetlana": {"azure_id": "ru-RU-SvetlanaNeural", "name": "Светлана", "gender": "female"},
    "svetlana_advanced": {"azure_id": "ru-RU-SvetlanaNeural", "name": "Светлана Pro", "gender": "female"},
    "alena": {"azure_id": "ru-RU-SvetlanaNeural", "name": "Алёна", "gender": "female"},
}

EMOTIONS = {
    "neutral": "neutral",
    "cheerful": "cheerful",
    "sad": "sad",
    "angry": "angry",
    "scared": "fearful",
    "serious": "serious",
    "gentle": "gentle",
    "calm": "calm",
    "professional": "newscast",
}

GENERATION_HISTORY = []

class TTSRequest(BaseModel):
    text: str
    voice: str = "dmitry_advanced"
    emotion: str = "neutral"
    speed: float = 0

class TTSResponse(BaseModel):
    id: str
    audio_url: str
    duration: float
    character_count: int
    created_at: str
    voice: str
    emotion: str

BASE_DIR = Path(__file__).resolve().parent.parent

@app.get("/")
async def root():
    return {"message": "Dragonsvitex TTS Studio API", "docs": "/docs", "frontend": "/app"}

@app.get("/app", response_class=HTMLResponse)
async def frontend():
    html_path = BASE_DIR / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Frontend not found</h1><p>Visit <a href='/docs'>/docs</a> for API</p>")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
