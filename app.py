import os
import gc
import re
import urllib.request
import struct
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from kokoro_onnx import Kokoro

MODEL_URL_PRIMARY = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v1.0.int8.onnx"
MODEL_URL_FALLBACK = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
VOICES_URL_PRIMARY = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices-v1.0.bin"
VOICES_URL_FALLBACK = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

global_state = {}

def download_file(primary_url, fallback_url, filename):
    if not os.path.exists(filename):
        print(f"Downloading {filename}...")
        req = urllib.request.Request(primary_url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as response, open(filename, 'wb') as out_file:
                out_file.write(response.read())
        except Exception as e:
            print(f"Primary URL failed: {e}. Trying fallback...")
            req = urllib.request.Request(fallback_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response, open(filename, 'wb') as out_file:
                out_file.write(response.read())
        print(f"Successfully downloaded {filename}.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application starting... Checking for Kokoro models.")
    # Download models if they don't exist
    download_file(MODEL_URL_PRIMARY, MODEL_URL_FALLBACK, "kokoro-v1.0.int8.onnx")
    download_file(VOICES_URL_PRIMARY, VOICES_URL_FALLBACK, "voices-v1.0.bin")

    print("Initializing Kokoro model as Singleton...")
    global_state["kokoro"] = Kokoro("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
    
    # Aggressively collect garbage after loading the model to free up initialization memory
    gc.collect()
    print("Kokoro model initialized and ready.")
    
    yield
    
    print("Cleaning up resources...")
    global_state.clear()
    gc.collect()

app = FastAPI(lifespan=lifespan)

class TTSRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    speed: float = 1.0

def split_sentences(text: str):
    # Regex to split by . ? ! followed by a space or end of string
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if s.strip()]

@app.post("/api/tts/stream")
async def tts_stream(req: TTSRequest):
    sentences = split_sentences(req.text)
    kokoro = global_state.get("kokoro")
    
    def generate_audio():
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            try:
                # create returns (samples, sample_rate)
                # lang="en-us" is standard for kokoro-onnx English voices
                samples, _ = kokoro.create(sentence, voice=req.voice, speed=req.speed, lang="en-us")
                pcm_bytes = samples.tobytes()
                
                # Custom binary format: 4 bytes Little-Endian length followed by raw PCM
                length_bytes = struct.pack('<I', len(pcm_bytes))
                chunk = length_bytes + pcm_bytes
                
                yield chunk
            except Exception as e:
                print(f"Error generating TTS for sentence '{sentence}': {e}")
            finally:
                # CRÍTICO PARA LA RAM: Delete local variables immediately and force GC
                if 'samples' in locals():
                    del samples
                if 'pcm_bytes' in locals():
                    del pcm_bytes
                if 'length_bytes' in locals():
                    del length_bytes
                if 'chunk' in locals():
                    del chunk
                
                gc.collect()

    return StreamingResponse(generate_audio(), media_type="application/octet-stream")

# Ensure public directory exists
os.makedirs("public", exist_ok=True)
app.mount("/", StaticFiles(directory="public", html=True), name="public")
