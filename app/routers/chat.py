from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from app.database import get_db
from app.models import Scheme
from app.schemas import SchemeResponse
from app.services import get_query_embedding, generate_agent_response

router = APIRouter(prefix="/api/chat", tags=["Agent"])

class ChatRequest(BaseModel):
    query: str  # The English text from your teammate's STT module

class ChatResponse(BaseModel):
    answer: str
    referenced_schemes: List[SchemeResponse]

@router.post("/", response_model=ChatResponse)
def chat_with_agent(request: ChatRequest, db: Session = Depends(get_db)):
    
    # 1. Vectorize the user's incoming question
    query_vector = get_query_embedding(request.query)
    
    # 2. Search PostgreSQL using pgvector (L2 Distance / Cosine Similarity)
    # The `<->` operator in pgvector means "find the closest mathematical distance"
    top_schemes = db.query(Scheme).order_by(Scheme.embedding.l2_distance(query_vector)).limit(3).all()
    
    # 3. Pass the question and the top 3 schemes to Claude 3 to generate the answer
    agent_answer = generate_agent_response(request.query, top_schemes)
    
    # 4. Return the conversational answer AND the scheme data (so the UI can display cards)
    return ChatResponse(
        answer=agent_answer,
        referenced_schemes=top_schemes
    )