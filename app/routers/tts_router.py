from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel
from app.services import synthesize_speech

router = APIRouter(prefix="/api", tags=["TTS"])

class TTSRequest(BaseModel):
    text: str
    language_code: str | None = None   # "hi-IN" | "en-US" | None → defaults to en-US

@router.post("/tts")
def text_to_speech(request: TTSRequest):
    """
    Returns MP3 audio bytes directly.
    Frontend creates a Blob URL and plays it.
    """
    audio_bytes = synthesize_speech(request.text, request.language_code)

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=response.mp3",
            "Cache-Control": "no-cache",
        },
    )
