from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.database import engine
from app.models import AgentSession, AgentTurn
from app.routers import schemes, chat, voice, tts_router

app = FastAPI(title="Bharat Schemes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schemes.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(tts_router.router, tags=["TTS"])
logger = logging.getLogger(__name__)


@app.on_event("startup")
def ensure_agent_tables():
    try:
        AgentSession.__table__.create(bind=engine, checkfirst=True)
        AgentTurn.__table__.create(bind=engine, checkfirst=True)
    except Exception as exc:
        logger.warning("Agent history tables were not created at startup: %s", exc)

@app.get("/")
def health_check():
    return {"status": "Online", "database": "Connected", "message": "Bharat Schemes API is live."}
