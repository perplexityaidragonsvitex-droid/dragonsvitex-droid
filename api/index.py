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
from fastapi.responses import FileResponse, JSONResponse, Response
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

@app.get("/")
async def root():
    return {"message": "Dragonsvitex TTS Studio API", "docs": "/docs"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "tts", "timestamp": datetime.now().isoformat()}

@app.get("/voices")
async def get_voices():
    return {
        "voices": [
            {"id": k, "name": v["name"], "gender": v["gender"]} 
            for k, v in VOICES.items()
        ],
        "emotions": [
            {"id": k, "name": k} for k in EMOTIONS.keys()
        ],
        "engine": "edge-tts",
        "standard": "AI-22"
    }

@app.post("/generate", response_model=TTSResponse)
async def generate_tts(request: TTSRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Текст не может быть пустым")
    
    if request.voice not in VOICES:
        raise HTTPException(status_code=400, detail=f"Неизвестный голос: {request.voice}")
    
    voice_config = VOICES[request.voice]
    azure_voice = voice_config["azure_id"]
    
    rate = f"{request.speed:+.0f}%" if request.speed != 0 else "+0%"
    
    gen_id = str(uuid.uuid4())[:8]
    temp_wav = TEMP_DIR / f"{gen_id}.wav"
    output_mp3 = OUTPUT_DIR / f"tts_{gen_id}.mp3"
    
    try:
        communicate = edge_tts.Communicate(
            request.text,
            azure_voice,
            rate=rate,
        )
        
        await communicate.save(str(temp_wav))
        
        ffmpeg_available = os.system("ffmpeg -version > /dev/null 2>&1") == 0
        
        if ffmpeg_available and temp_wav.exists():
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", str(temp_wav),
                "-af", "loudnorm=I=-23:TP=-1:LRA=5",
                "-ar", "44100",
                "-ac", "1",
                "-b:a", "128k",
                "-c:a", "libmp3lame",
                "-q:a", "2",
                str(output_mp3)
            ]
            
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                output_mp3 = temp_wav
            else:
                if temp_wav.exists():
                    os.remove(temp_wav)
        else:
            output_mp3 = temp_wav
        
        duration = 0
        audio_path = output_mp3 if output_mp3.exists() else temp_wav
        if audio_path.exists():
            try:
                duration_cmd = [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrriters=1:nokey=1",
                    str(audio_path)
                ]
                dur_result = subprocess.run(duration_cmd, capture_output=True, text=True)
                if dur_result.returncode == 0:
                    duration = float(dur_result.stdout.strip())
            except:
                duration = len(request.text) * 0.05
        
        audio_url = f"/audio/tts_{gen_id}.mp3" if output_mp3.suffix == ".mp3" else f"/audio/{gen_id}.wav"
        
        history_entry = {
            "id": gen_id,
            "text": request.text[:100] + "..." if len(request.text) > 100 else request.text,
            "voice": voice_config["name"],
            "emotion": request.emotion,
            "audio_url": audio_url,
            "duration": duration,
            "character_count": len(request.text),
            "created_at": datetime.now().isoformat(),
        }
        GENERATION_HISTORY.insert(0, history_entry)
        if len(GENERATION_HISTORY) > 100:
            GENERATION_HISTORY.pop()
        
        return TTSResponse(
            id=gen_id,
            audio_url=audio_url,
            duration=duration,
            character_count=len(request.text),
            created_at=datetime.now().isoformat(),
            voice=voice_config["name"],
            emotion=request.emotion,
        )
        
    except Exception as e:
        if temp_wav.exists():
            os.remove(temp_wav)
        if output_mp3.exists():
            os.remove(output_mp3)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history")
async def get_history(limit: int = 20):
    return {"history": GENERATION_HISTORY[:limit], "total": len(GENERATION_HISTORY)}

@app.delete("/history/{gen_id}")
async def delete_history(gen_id: str):
    global GENERATION_HISTORY
    GENERATION_HISTORY = [h for h in GENERATION_HISTORY if h["id"] != gen_id]
    
    for ext in [".mp3", ".wav"]:
        audio_file = OUTPUT_DIR / f"tts_{gen_id}{ext}"
        if audio_file.exists():
            os.remove(audio_file)
    
    return {"deleted": True, "id": gen_id}

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    audio_path = OUTPUT_DIR / filename
    if not audio_path.exists():
        audio_path = TEMP_DIR / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Аудиофайл не найден")
    
    media_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    return FileResponse(audio_path, media_type=media_type, filename=filename)

app.mount("/static", StaticFiles(directory="static"), name="static")
