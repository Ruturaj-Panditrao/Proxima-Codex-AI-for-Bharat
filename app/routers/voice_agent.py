import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AgentSession, AgentTurn, Scheme
from app.services import analyze_turn_for_followup, generate_agent_response, get_query_embedding


router = APIRouter(prefix="/api/agent", tags=["Voice Agent"])
AGENT_ENABLE_FOLLOW_UP = os.getenv("AGENT_ENABLE_FOLLOW_UP", "true").lower() == "true"


class AgentTurnRequest(BaseModel):
    session_id: Optional[str] = None
    user_text: str = Field(min_length=1)
    detected_language_code: Optional[str] = None


class SlotState(BaseModel):
    state: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    income_monthly: Optional[int] = None
    occupation: Optional[str] = None


class RecommendedScheme(BaseModel):
    slug: str
    schemeName: str
    briefDescription: Optional[str] = None
    beneficiaryState: Optional[List[str]] = None
    schemeCategory: Optional[List[str]] = None


class AgentTurnResponse(BaseModel):
    session_id: str
    status: str
    reply_text: str
    should_ask_followup: bool
    followup_question: Optional[str] = None
    missing_fields: List[str] = []
    collected_slots: SlotState
    referenced_schemes: List[RecommendedScheme] = []


class TurnHistoryItem(BaseModel):
    role: str
    message_text: str
    meta: Dict[str, Any] = {}
    created_at: Optional[str] = None


class SessionHistoryResponse(BaseModel):
    session_id: str
    language_code: Optional[str] = None
    slots: SlotState
    turns: List[TurnHistoryItem]


def _retrieve_recommendations(db: Session, query_text: str, state: Optional[str]) -> List[Scheme]:
    query_vector = get_query_embedding(query_text)

    base_query = db.query(Scheme)
    if state:
        base_query = base_query.filter(Scheme.beneficiaryState.any(state))

    if query_vector:
        return base_query.order_by(Scheme.embedding.l2_distance(query_vector)).limit(3).all()

    return base_query.filter(Scheme.schemeName.ilike("%yojana%")).limit(3).all()


def _load_slots_from_session(session_row: AgentSession) -> SlotState:
    slot_data = session_row.slots if isinstance(session_row.slots, dict) else {}
    return SlotState(**slot_data)


def _merge_slots(old_slots: SlotState, updates: dict) -> SlotState:
    data = old_slots.model_dump()
    for key in ["state", "age", "gender", "income_monthly", "occupation"]:
        value = updates.get(key)
        if value is not None and value != "":
            data[key] = value
    return SlotState(**data)


def _upsert_session(db: Session, session_id: Optional[str], detected_language_code: Optional[str]) -> tuple[str, AgentSession, SlotState]:
    sid = session_id or uuid4().hex
    session_row = db.query(AgentSession).filter(AgentSession.session_id == sid).first()

    if not session_row:
        session_row = AgentSession(
            session_id=sid,
            language_code=detected_language_code if detected_language_code and detected_language_code != "unknown" else None,
            slots={},
        )
        db.add(session_row)
        db.flush()

    if detected_language_code and detected_language_code != "unknown":
        session_row.language_code = detected_language_code

    return sid, session_row, _load_slots_from_session(session_row)


def _persist_turn(db: Session, session_id: str, role: str, message_text: str, meta: Optional[Dict[str, Any]] = None) -> None:
    db.add(
        AgentTurn(
            session_id=session_id,
            role=role,
            message_text=message_text,
            meta=meta or {},
        )
    )


def _serialize_scheme(scheme: Scheme) -> RecommendedScheme:
    return RecommendedScheme(
        slug=scheme.slug,
        schemeName=scheme.schemeName,
        briefDescription=scheme.briefDescription,
        beneficiaryState=scheme.beneficiaryState,
        schemeCategory=scheme.schemeCategory,
    )


@router.post("/voice-turn", response_model=AgentTurnResponse)
def agent_voice_turn(request: AgentTurnRequest, db: Session = Depends(get_db)):
    sid, session_row, current_slots = _upsert_session(db, request.session_id, request.detected_language_code)

    _persist_turn(
        db,
        sid,
        role="user",
        message_text=request.user_text,
        meta={"detected_language_code": request.detected_language_code or "unknown"},
    )

    recent_turns = (
        db.query(AgentTurn)
        .filter(AgentTurn.session_id == sid)
        .order_by(AgentTurn.id.desc())
        .limit(8)
        .all()
    )
    recent_turns.reverse()

    decision = analyze_turn_for_followup(
        user_text=request.user_text,
        history_turns=[{"role": t.role, "message_text": t.message_text} for t in recent_turns],
        detected_language_code=request.detected_language_code,
    )

    merged_slots = _merge_slots(current_slots, decision.get("slots", {}))
    session_row.slots = merged_slots.model_dump()

    should_follow = AGENT_ENABLE_FOLLOW_UP and bool(decision.get("should_follow_up", False))
    follow_up_question = (decision.get("follow_up_question") or "").strip()

    if should_follow and follow_up_question:
        _persist_turn(
            db,
            sid,
            role="agent",
            message_text=follow_up_question,
            meta={"status": "need_more_info", "source": "llm_decision"},
        )
        db.commit()
        return AgentTurnResponse(
            session_id=sid,
            status="need_more_info",
            reply_text=follow_up_question,
            should_ask_followup=True,
            followup_question=follow_up_question,
            missing_fields=[],
            collected_slots=merged_slots,
            referenced_schemes=[],
        )

    search_query = (decision.get("search_query") or request.user_text).strip()
    state_filter = decision.get("state_filter") or merged_slots.state

    schemes = _retrieve_recommendations(db, search_query, state_filter)
    scheme_cards = [_serialize_scheme(s) for s in schemes]

    if not scheme_cards:
        reply = "I could not find a strong scheme match yet. Please tell me your exact need, like scholarship, farming subsidy, or business loan."
        _persist_turn(
            db,
            sid,
            role="agent",
            message_text=reply,
            meta={"status": "no_match", "source": "retrieval"},
        )
        db.commit()
        return AgentTurnResponse(
            session_id=sid,
            status="no_match",
            reply_text=reply,
            should_ask_followup=True,
            followup_question=reply,
            missing_fields=[],
            collected_slots=merged_slots,
            referenced_schemes=[],
        )

    agent_prompt = (
        f"{request.user_text}\n"
        "Use this profile while answering:\n"
        f"- State: {merged_slots.state}\n"
        f"- Occupation: {merged_slots.occupation}\n"
        f"- Age: {merged_slots.age}\n"
        f"- Gender: {merged_slots.gender}\n"
        f"- Monthly income: {merged_slots.income_monthly}\n"
        "Be concise. If useful, ask one optional next question at the end."
    )
    answer = generate_agent_response(agent_prompt, schemes)

    _persist_turn(
        db,
        sid,
        role="agent",
        message_text=answer,
        meta={
            "status": "complete",
            "source": "retrieval+llm",
            "top_schemes": ", ".join([s.schemeName for s in scheme_cards]),
        },
    )
    db.commit()

    return AgentTurnResponse(
        session_id=sid,
        status="complete",
        reply_text=answer,
        should_ask_followup=False,
        followup_question=None,
        missing_fields=[],
        collected_slots=merged_slots,
        referenced_schemes=scheme_cards,
    )


@router.get("/session/{session_id}/history", response_model=SessionHistoryResponse)
def get_agent_session_history(
    session_id: str,
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    session_row = db.query(AgentSession).filter(AgentSession.session_id == session_id).first()
    if not session_row:
        return SessionHistoryResponse(session_id=session_id, slots=SlotState(), turns=[])

    turns = (
        db.query(AgentTurn)
        .filter(AgentTurn.session_id == session_id)
        .order_by(AgentTurn.id.desc())
        .limit(limit)
        .all()
    )
    turns.reverse()

    return SessionHistoryResponse(
        session_id=session_id,
        language_code=session_row.language_code,
        slots=_load_slots_from_session(session_row),
        turns=[
            TurnHistoryItem(
                role=t.role,
                message_text=t.message_text,
                meta=t.meta or {},
                created_at=t.created_at.isoformat() if t.created_at else None,
            )
            for t in turns
        ],
    )


@router.delete("/session/{session_id}")
def clear_agent_session(session_id: str, db: Session = Depends(get_db)):
    db.query(AgentTurn).filter(AgentTurn.session_id == session_id).delete()
    db.query(AgentSession).filter(AgentSession.session_id == session_id).delete()
    db.commit()
    return {"status": "cleared", "session_id": session_id}
