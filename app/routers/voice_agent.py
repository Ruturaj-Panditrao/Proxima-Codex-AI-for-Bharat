import re
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Scheme
from app.schemas import SchemeResponse
from app.services import generate_agent_response, get_query_embedding


router = APIRouter(prefix="/api/agent", tags=["Voice Agent"])


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


class AgentTurnResponse(BaseModel):
    session_id: str
    status: str
    reply_text: str
    should_ask_followup: bool
    followup_question: Optional[str] = None
    missing_fields: List[str] = []
    collected_slots: SlotState
    referenced_schemes: List[SchemeResponse] = []


class SessionState(BaseModel):
    slots: SlotState = SlotState()
    language_code: Optional[str] = None
    last_user_text: str = ""


# In-memory conversation state (replace with Redis/DB in production multi-instance setups)
SESSION_STORE: Dict[str, SessionState] = {}

INDIAN_STATES = {
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "delhi",
    "jammu and kashmir",
    "ladakh",
    "puducherry",
    "chandigarh",
    "andaman and nicobar islands",
    "dadra and nagar haveli and daman and diu",
    "lakshadweep",
}


def _extract_slots(text: str, current_slots: SlotState) -> SlotState:
    normalized = text.strip().lower()
    slots = current_slots.model_copy(deep=True)

    for st in INDIAN_STATES:
        if st in normalized:
            slots.state = st.title()
            break

    age_match = re.search(r"\b(?:age\s*is\s*|i am\s*|i'm\s*)(\d{1,2})\b", normalized)
    if age_match:
        slots.age = int(age_match.group(1))

    income_match = re.search(r"\b(?:income|salary|monthly income)\D{0,10}(\d{4,7})\b", normalized)
    if income_match:
        slots.income_monthly = int(income_match.group(1))

    if re.search(r"\b(male|man|boy)\b", normalized):
        slots.gender = "male"
    elif re.search(r"\b(female|woman|girl)\b", normalized):
        slots.gender = "female"
    elif re.search(r"\b(transgender)\b", normalized):
        slots.gender = "transgender"

    if re.search(r"\b(farmer|agri)\b", normalized):
        slots.occupation = "farmer"
    elif re.search(r"\b(student)\b", normalized):
        slots.occupation = "student"
    elif re.search(r"\b(worker|labour|labor)\b", normalized):
        slots.occupation = "worker"
    elif re.search(r"\b(women entrepreneur|entrepreneur|business)\b", normalized):
        slots.occupation = "entrepreneur"

    return slots


def _missing_fields(slots: SlotState) -> List[str]:
    required = ["state", "occupation"]
    missing: List[str] = []
    for field_name in required:
        if not getattr(slots, field_name):
            missing.append(field_name)
    return missing


def _followup_for_field(field_name: str) -> str:
    if field_name == "state":
        return "Which state do you live in?"
    if field_name == "occupation":
        return "Are you a student, farmer, worker, entrepreneur, or something else?"
    return "Could you share a bit more detail so I can suggest the best scheme?"


def _build_query_text(user_text: str, slots: SlotState) -> str:
    profile_parts = []
    if slots.state:
        profile_parts.append(f"State: {slots.state}")
    if slots.occupation:
        profile_parts.append(f"Occupation: {slots.occupation}")
    if slots.gender:
        profile_parts.append(f"Gender: {slots.gender}")
    if slots.age is not None:
        profile_parts.append(f"Age: {slots.age}")
    if slots.income_monthly is not None:
        profile_parts.append(f"Monthly income: {slots.income_monthly}")

    if not profile_parts:
        return user_text
    return f"{user_text}. User profile - " + ", ".join(profile_parts)


def _retrieve_recommendations(db: Session, query_text: str, state: Optional[str]) -> List[Scheme]:
    query_vector = get_query_embedding(query_text)

    base_query = db.query(Scheme)
    if state:
        base_query = base_query.filter(Scheme.beneficiaryState.any(state))

    if query_vector:
        return base_query.order_by(Scheme.embedding.l2_distance(query_vector)).limit(3).all()

    # Fallback if embedding service fails
    return base_query.filter(Scheme.schemeName.ilike("%yojana%")).limit(3).all()


@router.post("/voice-turn", response_model=AgentTurnResponse)
def agent_voice_turn(request: AgentTurnRequest, db: Session = Depends(get_db)):
    session_id = request.session_id or uuid4().hex
    session_state = SESSION_STORE.get(session_id, SessionState())

    session_state.language_code = request.detected_language_code or session_state.language_code
    session_state.last_user_text = request.user_text
    session_state.slots = _extract_slots(request.user_text, session_state.slots)

    missing = _missing_fields(session_state.slots)

    if missing:
        question = _followup_for_field(missing[0])
        SESSION_STORE[session_id] = session_state
        return AgentTurnResponse(
            session_id=session_id,
            status="need_more_info",
            reply_text=question,
            should_ask_followup=True,
            followup_question=question,
            missing_fields=missing,
            collected_slots=session_state.slots,
            referenced_schemes=[],
        )

    query_text = _build_query_text(request.user_text, session_state.slots)
    schemes = _retrieve_recommendations(db, query_text, session_state.slots.state)

    if not schemes:
        reply = "I could not find a strong scheme match yet. Please tell me your exact need, like scholarship, farming subsidy, or business loan."
        SESSION_STORE[session_id] = session_state
        return AgentTurnResponse(
            session_id=session_id,
            status="no_match",
            reply_text=reply,
            should_ask_followup=True,
            followup_question=reply,
            missing_fields=[],
            collected_slots=session_state.slots,
            referenced_schemes=[],
        )

    agent_prompt = (
        f"{request.user_text}\n"
        "Use this collected profile while answering:\n"
        f"- State: {session_state.slots.state}\n"
        f"- Occupation: {session_state.slots.occupation}\n"
        f"- Age: {session_state.slots.age}\n"
        f"- Gender: {session_state.slots.gender}\n"
        f"- Monthly income: {session_state.slots.income_monthly}\n"
        "Give concise recommendation and ask if user wants next best option."
    )
    answer = generate_agent_response(agent_prompt, schemes)
    SESSION_STORE[session_id] = session_state

    return AgentTurnResponse(
        session_id=session_id,
        status="complete",
        reply_text=answer,
        should_ask_followup=False,
        followup_question=None,
        missing_fields=[],
        collected_slots=session_state.slots,
        referenced_schemes=schemes,
    )


@router.delete("/session/{session_id}")
def clear_agent_session(session_id: str):
    SESSION_STORE.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}
