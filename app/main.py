from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import schemes, chat  # <-- Import chat here

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

@app.get("/")
def health_check():
    return {"status": "Online", "database": "Connected", "message": "Bharat Schemes API is live."}