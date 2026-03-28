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

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/voices")
async def list_voices():
    return {
        "voices": [
            {"id": k, **v} for k, v in VOICES.items()
        ]
    }

@app.post("/generate", response_model=TTSResponse)
async def generate_tts(request: TTSRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Текст не может быть пустым")
    
    if request.voice not in VOICES:
        raise HTTPException(status_code=400, detail=f"Неизвестный голос: {request.voice}")
    
    if request.emotion not in EMOTIONS:
        raise HTTPException(status_code=400, detail=f"Неизвестная эмоция: {request.emotion}")
    
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        voice_name = voice_config["name"].replace(" ", "_").replace("Pro", "Pro")
        output_filename = f"{voice_name}_{timestamp}.mp3"
        output_path = OUTPUT_DIR / output_filename
    
    voice_config = VOICES[request.voice]
    azure_voice = voice_config["azure_id"]
    emotion_style = EMOTIONS.get(request.emotion, "neutral")
    
    speed_str = f"+{int(request.speed)}%" if request.speed >= 0 else f"{int(request.speed)}%"
    
    try:
        communicate = edge_tts.Communicate(
            text=request.text,
            voice=azure_voice,
            rate=speed_str
        )
        
        await communicate.save(str(output_path))
        
        file_size = output_path.stat().st_size
        duration = max(1.0, file_size / 24000)
        
        result = {
            "id": generation_id,
            "audio_url": f"/audio/{output_filename}",
            "duration": round(duration, 2),
            "character_count": len(request.text),
            "created_at": datetime.now().isoformat(),
            "voice": voice_config["name"],
            "emotion": request.emotion,
            "text": request.text[:100] + ("..." if len(request.text) > 100 else "")
        }
        
        GENERATION_HISTORY.insert(0, result)
        if len(GENERATION_HISTORY) > 50:
            GENERATION_HISTORY.pop()
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@app.get("/history")
async def get_history():
    return {"history": GENERATION_HISTORY}

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    file_path = OUTPUT_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    return FileResponse(
        path=file_path,
        media_type="audio/mpeg",
        filename=filename
    )
